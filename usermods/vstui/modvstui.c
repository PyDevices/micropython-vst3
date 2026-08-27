// The editor's half of the board contract, in C.
//
// `vstaudio` binds the engine to the host's audio mapping; this binds it to
// the sibling UI mapping ui.h describes. Everything above it is stock
// PyDevices: lib/vst_board_config.py wraps these calls in a displaydev
// DisplayDriver plus a host-event source, and display_driver.py wires LVGL to
// that exactly as it does on hardware.
//
// Nothing here knows what a slider is, and nothing here paints. The engine
// produces pixels, dirty rectangles and parameter edits; it consumes input.
// Neither side ever waits: a full ring degrades in a bounded, counted way.
#if defined(_WIN32)
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#else
#include <errno.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>
#endif

#include "mpvst/ui.h"

#include "py/binary.h"
#include "py/obj.h"
#include "py/objarray.h"
#include "py/runtime.h"

#include <stdint.h>
#include <string.h>

#if defined(_WIN32)
static HANDLE vstui_mapping_handle;
#endif
static void *vstui_mapping;
static mpvst_ui_state *vstui_state;
static mpvst_ui_rect *vstui_rects;
static mpvst_ui_input *vstui_inputs;
static mpvst_ui_edit *vstui_edits;
static uint8_t *vstui_pixels;
// Counted degradation, readable from Python so a panel can report on itself.
static uint64_t vstui_rect_coalesces;
static uint64_t vstui_edit_drops;

#if defined(_WIN32)

static uint64_t atomic_load_u64(const uint64_t *value) {
    return (uint64_t)InterlockedCompareExchange64(
        (volatile LONG64 *)(uintptr_t)value, 0, 0);
}

static void atomic_store_u64(uint64_t *value, uint64_t desired) {
    (void)InterlockedExchange64((volatile LONG64 *)(uintptr_t)value, (LONG64)desired);
}

static uint32_t atomic_load_u32(const uint32_t *value) {
    return (uint32_t)InterlockedCompareExchange(
        (volatile LONG *)(uintptr_t)value, 0, 0);
}

static void atomic_store_u32(uint32_t *value, uint32_t desired) {
    (void)InterlockedExchange((volatile LONG *)(uintptr_t)value, (LONG)desired);
}

#else

static uint64_t atomic_load_u64(const uint64_t *value) {
    return __atomic_load_n(value, __ATOMIC_SEQ_CST);
}

static void atomic_store_u64(uint64_t *value, uint64_t desired) {
    __atomic_store_n(value, desired, __ATOMIC_SEQ_CST);
}

static uint32_t atomic_load_u32(const uint32_t *value) {
    return __atomic_load_n(value, __ATOMIC_SEQ_CST);
}

static void atomic_store_u32(uint32_t *value, uint32_t desired) {
    __atomic_store_n(value, desired, __ATOMIC_SEQ_CST);
}

#endif

static void vstui_close(void) {
#if defined(_WIN32)
    if (vstui_mapping != NULL) {
        UnmapViewOfFile(vstui_mapping);
    }
    if (vstui_mapping_handle != NULL) {
        CloseHandle(vstui_mapping_handle);
    }
    vstui_mapping_handle = NULL;
#else
    if (vstui_mapping != NULL) {
        (void)munmap(vstui_mapping, (size_t)mpvst_ui_mapping_bytes());
    }
#endif
    vstui_mapping = NULL;
    vstui_state = NULL;
    vstui_rects = NULL;
    vstui_inputs = NULL;
    vstui_edits = NULL;
    vstui_pixels = NULL;
}

static void require_open(void) {
    if (vstui_state == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("vstui is not open"));
    }
}

// Open the mapping the plug-in created. Returns False rather than raising when
// the name does not resolve: an engine started by a plug-in that predates the
// editor gets no name at all, and one started under a host that could not
// create the region should still render audio.
static mp_obj_t vstui_open(mp_obj_t name_obj) {
    vstui_close();
    const char *name = mp_obj_str_get_str(name_obj);
    const uint64_t bytes = mpvst_ui_mapping_bytes();
#if defined(_WIN32)
    HANDLE handle = OpenFileMappingA(FILE_MAP_ALL_ACCESS, FALSE, name);
    if (handle == NULL) {
        return mp_const_false;
    }
    void *mapping = MapViewOfFile(handle, FILE_MAP_ALL_ACCESS, 0, 0, (SIZE_T)bytes);
    if (mapping == NULL) {
        CloseHandle(handle);
        return mp_const_false;
    }
#else
    const int descriptor = shm_open(name, O_RDWR, 0600);
    if (descriptor < 0) {
        return mp_const_false;
    }
    void *mapping = mmap(NULL, (size_t)bytes, PROT_READ | PROT_WRITE, MAP_SHARED,
                         descriptor, 0);
    (void)close(descriptor);
    if (mapping == MAP_FAILED) {
        return mp_const_false;
    }
#endif
    if (!mpvst_ui_validate(mapping, bytes)) {
#if defined(_WIN32)
        UnmapViewOfFile(mapping);
        CloseHandle(handle);
#else
        (void)munmap(mapping, (size_t)bytes);
#endif
        return mp_const_false;
    }

#if defined(_WIN32)
    vstui_mapping_handle = handle;
#endif
    vstui_mapping = mapping;
    vstui_state = (mpvst_ui_state *)mapping;
    vstui_rects = mpvst_ui_rects(mapping);
    vstui_inputs = mpvst_ui_inputs(mapping);
    vstui_edits = mpvst_ui_edits(mapping);
    vstui_pixels = mpvst_ui_framebuffer(mapping);
    vstui_rect_coalesces = 0u;
    vstui_edit_drops = 0u;
    return mp_const_true;
}
static MP_DEFINE_CONST_FUN_OBJ_1(vstui_open_obj, vstui_open);

static mp_obj_t vstui_available(void) {
    return vstui_state != NULL ? mp_const_true : mp_const_false;
}
static MP_DEFINE_CONST_FUN_OBJ_0(vstui_available_obj, vstui_available);

// Declare the logical size, once, at startup. The framebuffer is always the
// compiled maximum; this only says how much of it the panel uses, so the view
// can size itself and nothing ever re-allocates.
static mp_obj_t vstui_configure(mp_obj_t width_obj, mp_obj_t height_obj) {
    require_open();
    const mp_int_t width = mp_obj_get_int(width_obj);
    const mp_int_t height = mp_obj_get_int(height_obj);
    if (width <= 0 || height <= 0 || (uint32_t)width > MPVST_UI_MAX_WIDTH ||
        (uint32_t)height > MPVST_UI_MAX_HEIGHT) {
        mp_raise_ValueError(MP_ERROR_TEXT("size exceeds the compiled maximum"));
    }
    atomic_store_u32(&vstui_state->width, (uint32_t)width);
    atomic_store_u32(&vstui_state->height, (uint32_t)height);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(vstui_configure_obj, vstui_configure);

static mp_obj_t vstui_size(void) {
    require_open();
    mp_obj_t items[2] = {
        mp_obj_new_int_from_uint(atomic_load_u32(&vstui_state->width)),
        mp_obj_new_int_from_uint(atomic_load_u32(&vstui_state->height)),
    };
    return mp_obj_new_tuple(2, items);
}
static MP_DEFINE_CONST_FUN_OBJ_0(vstui_size_obj, vstui_size);

static mp_obj_t vstui_stride(void) {
    return mp_obj_new_int_from_ull(mpvst_ui_stride_bytes());
}
static MP_DEFINE_CONST_FUN_OBJ_0(vstui_stride_obj, vstui_stride);

// A writable view of the whole framebuffer. Exposed for diagnostics and for a
// caller that wants to compose its own pixels and then publish(); the board
// config uses blit() instead, which brackets the copy in the seqlock rather
// than leaving a window where a view can read half-written pixels.
static mp_obj_t vstui_framebuffer(void) {
    require_open();
    return mp_obj_new_memoryview('B' | MP_OBJ_ARRAY_TYPECODE_FLAG_RW,
                                 (size_t)mpvst_ui_framebuffer_bytes(),
                                 vstui_pixels);
}
static MP_DEFINE_CONST_FUN_OBJ_0(vstui_framebuffer_obj, vstui_framebuffer);

// Queue one dirty rectangle for the frame currently being written. A full ring
// collapses to a single full-frame rectangle rather than dropping updates: the
// view then repaints everything, which is slower but never wrong.
static void queue_rect(uint64_t sequence, uint32_t x, uint32_t y, uint32_t w,
    uint32_t h) {
    const uint64_t head = atomic_load_u64(&vstui_state->rect_head);
    const uint64_t tail = atomic_load_u64(&vstui_state->rect_tail);
    if (head - tail >= MPVST_UI_RECT_CAPACITY) {
        mpvst_ui_rect *whole = &vstui_rects[tail % MPVST_UI_RECT_CAPACITY];
        whole->frame_sequence = sequence;
        whole->x = 0u;
        whole->y = 0u;
        whole->width = (uint16_t)atomic_load_u32(&vstui_state->width);
        whole->height = (uint16_t)atomic_load_u32(&vstui_state->height);
        atomic_store_u64(&vstui_state->rect_head, tail + 1u);
        ++vstui_rect_coalesces;
        return;
    }
    mpvst_ui_rect *rect = &vstui_rects[head % MPVST_UI_RECT_CAPACITY];
    rect->frame_sequence = sequence;
    rect->x = (uint16_t)x;
    rect->y = (uint16_t)y;
    rect->width = (uint16_t)w;
    rect->height = (uint16_t)h;
    atomic_store_u64(&vstui_state->rect_head, head + 1u);
}

static bool rect_in_bounds(mp_int_t x, mp_int_t y, mp_int_t w, mp_int_t h) {
    const uint32_t width = atomic_load_u32(&vstui_state->width);
    const uint32_t height = atomic_load_u32(&vstui_state->height);
    return x >= 0 && y >= 0 && w > 0 && h > 0 &&
        (uint64_t)x + (uint64_t)w <= width && (uint64_t)y + (uint64_t)h <= height;
}

// Copy a rectangle of RGB565 pixels into the framebuffer and publish it. The
// seqlock is taken around the copy, not after it: an unbracketed write is
// exactly the torn frame the sequence exists to let the view detect.
static mp_obj_t vstui_blit(size_t n_args, const mp_obj_t *args) {
    (void)n_args;
    require_open();
    mp_buffer_info_t source;
    mp_get_buffer_raise(args[0], &source, MP_BUFFER_READ);
    const mp_int_t x = mp_obj_get_int(args[1]);
    const mp_int_t y = mp_obj_get_int(args[2]);
    const mp_int_t w = mp_obj_get_int(args[3]);
    const mp_int_t h = mp_obj_get_int(args[4]);
    if (!rect_in_bounds(x, y, w, h)) {
        mp_raise_ValueError(MP_ERROR_TEXT("blit rectangle is out of range"));
    }
    const size_t row_bytes = (size_t)w * MPVST_UI_PIXEL_BYTES;
    if (source.len < row_bytes * (size_t)h) {
        mp_raise_ValueError(MP_ERROR_TEXT("source buffer is too small"));
    }

    const uint64_t sequence = atomic_load_u64(&vstui_state->frame_sequence) + 1u;
    atomic_store_u64(&vstui_state->frame_sequence, sequence);
    const uint64_t stride = mpvst_ui_stride_bytes();
    const uint8_t *from = (const uint8_t *)source.buf;
    uint8_t *to = vstui_pixels + (uint64_t)y * stride +
        (uint64_t)x * MPVST_UI_PIXEL_BYTES;
    for (mp_int_t row = 0; row < h; ++row) {
        memcpy(to, from, row_bytes);
        from += row_bytes;
        to += stride;
    }
    queue_rect(sequence, (uint32_t)x, (uint32_t)y, (uint32_t)w, (uint32_t)h);
    atomic_store_u64(&vstui_state->frame_sequence, sequence + 1u);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(vstui_blit_obj, 5, 5, vstui_blit);

// Publish a rectangle whose pixels were written through framebuffer() already.
// The seqlock still has to be taken so the view can tell a settled frame from
// one in progress; the writer is responsible for having finished.
static mp_obj_t vstui_publish(size_t n_args, const mp_obj_t *args) {
    (void)n_args;
    require_open();
    const mp_int_t x = mp_obj_get_int(args[0]);
    const mp_int_t y = mp_obj_get_int(args[1]);
    const mp_int_t w = mp_obj_get_int(args[2]);
    const mp_int_t h = mp_obj_get_int(args[3]);
    if (!rect_in_bounds(x, y, w, h)) {
        mp_raise_ValueError(MP_ERROR_TEXT("publish rectangle is out of range"));
    }
    const uint64_t sequence = atomic_load_u64(&vstui_state->frame_sequence) + 1u;
    atomic_store_u64(&vstui_state->frame_sequence, sequence);
    queue_rect(sequence, (uint32_t)x, (uint32_t)y, (uint32_t)w, (uint32_t)h);
    atomic_store_u64(&vstui_state->frame_sequence, sequence + 1u);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(vstui_publish_obj, 4, 4, vstui_publish);

static mp_obj_t vstui_editor_open(void) {
    if (vstui_state == NULL) {
        return mp_const_false;
    }
    return atomic_load_u32(&vstui_state->editor_open) != 0u
        ? mp_const_true : mp_const_false;
}
static MP_DEFINE_CONST_FUN_OBJ_0(vstui_editor_open_obj, vstui_editor_open);

// Drain the input ring. Each record becomes
// (type, buttons, x, y, wheel_vertical, wheel_horizontal); the board config
// turns those into the ordinary PyDevices event objects LVGL already reads.
// The heartbeat advances here because this is the one call the engine makes
// every UI tick whether or not anything was painted.
static mp_obj_t vstui_poll(void) {
    require_open();
    mp_obj_t list = mp_obj_new_list(0, NULL);
    if (vstui_state == NULL) {
        return list;
    }
    atomic_store_u64(&vstui_state->ui_heartbeat,
        atomic_load_u64(&vstui_state->ui_heartbeat) + 1u);
    const uint64_t head = atomic_load_u64(&vstui_state->input_head);
    uint64_t tail = atomic_load_u64(&vstui_state->input_tail);
    // A view that ran far ahead of a stalled engine leaves a gap; start at the
    // oldest record still present rather than reading recycled slots.
    if (head - tail > MPVST_UI_INPUT_CAPACITY) {
        tail = head - MPVST_UI_INPUT_CAPACITY;
    }
    while (tail != head) {
        const mpvst_ui_input *record = &vstui_inputs[tail % MPVST_UI_INPUT_CAPACITY];
        mp_obj_t items[6] = {
            mp_obj_new_int_from_uint(record->type),
            mp_obj_new_int_from_uint(record->buttons),
            mp_obj_new_int(record->x),
            mp_obj_new_int(record->y),
            mp_obj_new_int(record->wheel_vertical),
            mp_obj_new_int(record->wheel_horizontal),
        };
        mp_obj_list_append(list, mp_obj_new_tuple(6, items));
        ++tail;
    }
    atomic_store_u64(&vstui_state->input_tail, tail);
    return list;
}
static MP_DEFINE_CONST_FUN_OBJ_0(vstui_poll_obj, vstui_poll);

// Publish one parameter edit for the view to replay into the controller. A
// full ring drops `perform` records and never a `begin` or an `end`, so a
// gesture is always closed and the host never sees an edit left open.
static mp_obj_t vstui_edit(mp_obj_t kind_obj, mp_obj_t id_obj, mp_obj_t value_obj) {
    require_open();
    const uint32_t kind = (uint32_t)mp_obj_get_int(kind_obj);
    const uint32_t parameter = (uint32_t)mp_obj_get_int(id_obj);
    const float value = (float)mp_obj_get_float(value_obj);
    uint64_t head = atomic_load_u64(&vstui_state->edit_head);
    const uint64_t tail = atomic_load_u64(&vstui_state->edit_tail);
    if (head - tail >= MPVST_UI_EDIT_CAPACITY) {
        if (kind == MPVST_UI_EDIT_PERFORM) {
            ++vstui_edit_drops;
            return mp_const_false;
        }
        atomic_store_u64(&vstui_state->edit_tail, tail + 1u);
        ++vstui_edit_drops;
    }
    mpvst_ui_edit *record = &vstui_edits[head % MPVST_UI_EDIT_CAPACITY];
    record->kind = kind;
    record->parameter_id = parameter;
    record->value = value;
    record->reserved0 = 0u;
    record->reserved1 = 0u;
    record->sequence = head + 1u;
    atomic_store_u64(&vstui_state->edit_head, head + 1u);
    return mp_const_true;
}
static MP_DEFINE_CONST_FUN_OBJ_3(vstui_edit_obj, vstui_edit);

// Report a panel failure. The view renders its own native "editor
// unavailable" text whenever this is non-zero, so a broken panel is visible
// rather than frozen. Audio is unaffected either way.
static mp_obj_t vstui_error(mp_obj_t code_obj) {
    require_open();
    atomic_store_u32(&vstui_state->ui_error, (uint32_t)mp_obj_get_int(code_obj));
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(vstui_error_obj, vstui_error);

// (rect_coalesces, edit_drops, frame_sequence, generation) - how the surface
// is coping, for a panel or a test that wants to report on it.
static mp_obj_t vstui_stats(void) {
    require_open();
    mp_obj_t items[4] = {
        mp_obj_new_int_from_ull(vstui_rect_coalesces),
        mp_obj_new_int_from_ull(vstui_edit_drops),
        mp_obj_new_int_from_ull(atomic_load_u64(&vstui_state->frame_sequence)),
        mp_obj_new_int_from_uint(atomic_load_u32(&vstui_state->generation)),
    };
    return mp_obj_new_tuple(4, items);
}
static MP_DEFINE_CONST_FUN_OBJ_0(vstui_stats_obj, vstui_stats);

static const mp_rom_map_elem_t vstui_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_vstui) },
    { MP_ROM_QSTR(MP_QSTR_open), MP_ROM_PTR(&vstui_open_obj) },
    { MP_ROM_QSTR(MP_QSTR_available), MP_ROM_PTR(&vstui_available_obj) },
    { MP_ROM_QSTR(MP_QSTR_configure), MP_ROM_PTR(&vstui_configure_obj) },
    { MP_ROM_QSTR(MP_QSTR_size), MP_ROM_PTR(&vstui_size_obj) },
    { MP_ROM_QSTR(MP_QSTR_stride), MP_ROM_PTR(&vstui_stride_obj) },
    { MP_ROM_QSTR(MP_QSTR_framebuffer), MP_ROM_PTR(&vstui_framebuffer_obj) },
    { MP_ROM_QSTR(MP_QSTR_blit), MP_ROM_PTR(&vstui_blit_obj) },
    { MP_ROM_QSTR(MP_QSTR_publish), MP_ROM_PTR(&vstui_publish_obj) },
    { MP_ROM_QSTR(MP_QSTR_editor_open), MP_ROM_PTR(&vstui_editor_open_obj) },
    { MP_ROM_QSTR(MP_QSTR_poll), MP_ROM_PTR(&vstui_poll_obj) },
    { MP_ROM_QSTR(MP_QSTR_edit), MP_ROM_PTR(&vstui_edit_obj) },
    { MP_ROM_QSTR(MP_QSTR_error), MP_ROM_PTR(&vstui_error_obj) },
    { MP_ROM_QSTR(MP_QSTR_stats), MP_ROM_PTR(&vstui_stats_obj) },
    { MP_ROM_QSTR(MP_QSTR_MAX_WIDTH), MP_ROM_INT(MPVST_UI_MAX_WIDTH) },
    { MP_ROM_QSTR(MP_QSTR_MAX_HEIGHT), MP_ROM_INT(MPVST_UI_MAX_HEIGHT) },
    { MP_ROM_QSTR(MP_QSTR_DEFAULT_WIDTH), MP_ROM_INT(MPVST_UI_DEFAULT_WIDTH) },
    { MP_ROM_QSTR(MP_QSTR_DEFAULT_HEIGHT), MP_ROM_INT(MPVST_UI_DEFAULT_HEIGHT) },
    { MP_ROM_QSTR(MP_QSTR_WHEEL_NOTCH), MP_ROM_INT(MPVST_UI_WHEEL_NOTCH) },
    { MP_ROM_QSTR(MP_QSTR_INPUT_POINTER_MOVE), MP_ROM_INT(MPVST_UI_INPUT_POINTER_MOVE) },
    { MP_ROM_QSTR(MP_QSTR_INPUT_POINTER_DOWN), MP_ROM_INT(MPVST_UI_INPUT_POINTER_DOWN) },
    { MP_ROM_QSTR(MP_QSTR_INPUT_POINTER_UP), MP_ROM_INT(MPVST_UI_INPUT_POINTER_UP) },
    { MP_ROM_QSTR(MP_QSTR_INPUT_WHEEL), MP_ROM_INT(MPVST_UI_INPUT_WHEEL) },
    { MP_ROM_QSTR(MP_QSTR_EDIT_BEGIN), MP_ROM_INT(MPVST_UI_EDIT_BEGIN) },
    { MP_ROM_QSTR(MP_QSTR_EDIT_PERFORM), MP_ROM_INT(MPVST_UI_EDIT_PERFORM) },
    { MP_ROM_QSTR(MP_QSTR_EDIT_END), MP_ROM_INT(MPVST_UI_EDIT_END) },
    { MP_ROM_QSTR(MP_QSTR_ERROR_NONE), MP_ROM_INT(MPVST_UI_ERROR_NONE) },
    { MP_ROM_QSTR(MP_QSTR_ERROR_PANEL_FAILED), MP_ROM_INT(MPVST_UI_ERROR_PANEL_FAILED) },
    { MP_ROM_QSTR(MP_QSTR_ERROR_UNSUPPORTED), MP_ROM_INT(MPVST_UI_ERROR_UNSUPPORTED) },
};
static MP_DEFINE_CONST_DICT(vstui_module_globals, vstui_module_globals_table);

const mp_obj_module_t vstui_module = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&vstui_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_vstui, vstui_module);
