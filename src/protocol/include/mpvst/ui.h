#pragma once

/* The editor's shared-memory surface: one framebuffer, one dirty-rectangle
   ring, one input ring, one parameter-edit ring. ui-v1.md is the design; the
   exact sizes and offsets are here, and tests/protocol_tests.cpp pins them.

   This is a *sibling* mapping, created next to the audio mapping rather than
   inside it. ui-v1.md described it as a new optional region of the existing
   mapping, and that turned out not to be buildable without breaking the thing
   the same paragraph promised: mpvst_shared_header is exactly 128 bytes with
   no reserved field left, so carrying a ui_offset/ui_bytes pair means growing
   the header, and both the shipped engine and mpvst_validate_mapping reject a
   header whose header_bytes is not sizeof(mpvst_shared_header). An old engine
   under a new plug-in would then fail to start at all instead of "simply
   having no editor". Extending the existing optional region has the same
   problem one layer down: its size is validated to be exactly one input-audio
   block per work slot.

   A separate mapping keeps the audio protocol byte-identical, so old and new
   halves still pair up, and the degradation is the documented one: the engine
   is handed the UI mapping's name as an extra argument, and an engine that
   does not understand the argument ignores it and runs without an editor. It
   also makes ui-v1.md's "the view maps only the UI region" literally true.

   Ownership: the engine is the producer of pixels, rectangles and edits and
   the consumer of input; the view is the reverse. Neither side ever waits. */

#include <stddef.h>
#include <stdint.h>

#if defined(__cplusplus)
#define MPVST_UI_ALIGNAS(value) alignas(value)
#define MPVST_UI_STATIC_ASSERT(condition, message) static_assert(condition, message)
#elif defined(_MSC_VER)
#define MPVST_UI_ALIGNAS(value) __declspec(align(value))
#define MPVST_UI_STATIC_ASSERT(condition, message) static_assert(condition, message)
#else
#define MPVST_UI_ALIGNAS(value) __attribute__((aligned(value)))
#define MPVST_UI_STATIC_ASSERT(condition, message) _Static_assert(condition, message)
#endif

/* "MPU3", the editor sibling of the audio mapping's "MPV3". */
#define MPVST_UI_MAGIC UINT32_C(0x3355504d)
#define MPVST_UI_MAJOR UINT16_C(1)
#define MPVST_UI_MINOR UINT16_C(0)
#define MPVST_UI_ENDIAN_MARKER UINT32_C(0x01020304)
#define MPVST_UI_CACHE_LINE_BYTES UINT32_C(64)

/* The compile-time maximum ui-v1.md fixes. The framebuffer is always this
   size; the logical size the panel declares indexes into the same stride, so
   changing the logical size never re-allocates anything. */
#define MPVST_UI_MAX_WIDTH UINT32_C(1024)
#define MPVST_UI_MAX_HEIGHT UINT32_C(600)
#define MPVST_UI_DEFAULT_WIDTH UINT32_C(800)
#define MPVST_UI_DEFAULT_HEIGHT UINT32_C(480)

#define MPVST_UI_RECT_CAPACITY UINT32_C(64)
#define MPVST_UI_INPUT_CAPACITY UINT32_C(256)
#define MPVST_UI_EDIT_CAPACITY UINT32_C(64)

/* RGB565 little-endian, the only format v1 defines. */
#define MPVST_UI_PIXEL_RGB565 UINT32_C(1)
#define MPVST_UI_PIXEL_BYTES UINT32_C(2)

/* Content scale is carried as parts per million so the wire stays integral. */
#define MPVST_UI_SCALE_UNITY UINT32_C(1000000)

/* One notch of a mouse wheel, matching Win32's WHEEL_DELTA so a Windows
   message's own value passes through unscaled. Fractional/high-resolution
   wheels deliver proportionally smaller values. */
#define MPVST_UI_WHEEL_NOTCH 120

typedef enum mpvst_ui_input_type
{
    MPVST_UI_INPUT_NONE = 0,
    MPVST_UI_INPUT_POINTER_MOVE = 1,
    MPVST_UI_INPUT_POINTER_DOWN = 2,
    MPVST_UI_INPUT_POINTER_UP = 3,
    MPVST_UI_INPUT_WHEEL = 4
} mpvst_ui_input_type;

typedef enum mpvst_ui_edit_kind
{
    MPVST_UI_EDIT_NONE = 0,
    MPVST_UI_EDIT_BEGIN = 1,
    MPVST_UI_EDIT_PERFORM = 2,
    MPVST_UI_EDIT_END = 3
} mpvst_ui_edit_kind;

/* Panel-side failures, reported to the view so a broken editor is visible
   rather than frozen. Zero means healthy. */
typedef enum mpvst_ui_error
{
    MPVST_UI_ERROR_NONE = 0,
    MPVST_UI_ERROR_PANEL_FAILED = 1,
    MPVST_UI_ERROR_UNSUPPORTED = 2
} mpvst_ui_error;

/* The state block, which doubles as the mapping's header. Every cursor is a
   free-running 64-bit count, never a wrapped index: a producer's head and a
   consumer's tail are compared by difference, so a reset that zeroes both is
   coherent and a wrap is not representable in any run this will ever see. */
typedef struct MPVST_UI_ALIGNAS(8) mpvst_ui_state
{
    uint32_t magic;
    uint16_t ui_major;
    uint16_t ui_minor;
    uint32_t state_bytes;
    uint32_t endian_marker;
    uint64_t mapping_bytes;
    uint32_t max_width;
    uint32_t max_height;
    /* Logical size, declared once by the panel through vstui.configure(). */
    MPVST_UI_ALIGNAS(4) uint32_t width;
    MPVST_UI_ALIGNAS(4) uint32_t height;
    uint32_t pixel_format;
    /* Written by the view from IPlugViewContentScaleSupport; the engine never
       reads it, so nothing in the panel has to know about DPI. */
    MPVST_UI_ALIGNAS(4) uint32_t content_scale_ppm;
    /* Seqlock over the framebuffer and the rectangle ring: odd while the
       engine is writing, even when a frame is consistent. */
    MPVST_UI_ALIGNAS(8) uint64_t frame_sequence;
    MPVST_UI_ALIGNAS(8) uint64_t rect_head;
    MPVST_UI_ALIGNAS(8) uint64_t rect_tail;
    MPVST_UI_ALIGNAS(8) uint64_t input_head;
    MPVST_UI_ALIGNAS(8) uint64_t input_tail;
    MPVST_UI_ALIGNAS(8) uint64_t edit_head;
    MPVST_UI_ALIGNAS(8) uint64_t edit_tail;
    /* Advanced by the engine on every UI tick, so the view can tell a panel
       that is idle from one that has stopped. */
    MPVST_UI_ALIGNAS(8) uint64_t ui_heartbeat;
    /* The view's attach/detach flag; the engine does no UI work when it is
       zero. */
    MPVST_UI_ALIGNAS(4) uint32_t editor_open;
    MPVST_UI_ALIGNAS(4) uint32_t ui_error;
    /* Bumped by the plug-in each time it (re)initializes the region, so a
       view holding a stale mapping notices an engine restart. */
    MPVST_UI_ALIGNAS(4) uint32_t generation;
    uint32_t reserved0;
} mpvst_ui_state;

typedef struct MPVST_UI_ALIGNAS(8) mpvst_ui_rect
{
    /* The frame sequence this rectangle belongs to, so a view that observes a
       torn frame can discard exactly the rectangles that came from it. */
    MPVST_UI_ALIGNAS(8) uint64_t frame_sequence;
    uint16_t x;
    uint16_t y;
    uint16_t width;
    uint16_t height;
} mpvst_ui_rect;

typedef struct MPVST_UI_ALIGNAS(8) mpvst_ui_input
{
    MPVST_UI_ALIGNAS(8) uint64_t sequence;
    uint32_t type;
    /* Bit 0 is the primary button. v1's panel only reads bit 0. */
    uint32_t buttons;
    /* Logical pixels: the view divides by the content scale on the way in. */
    int32_t x;
    int32_t y;
    /* Two signed wheel deltas in MPVST_UI_WHEEL_NOTCH units. Both axes ship
       in v1: the axis parallel to a control adjusts it, the perpendicular one
       moves focus. */
    int32_t wheel_vertical;
    int32_t wheel_horizontal;
} mpvst_ui_input;

typedef struct MPVST_UI_ALIGNAS(8) mpvst_ui_edit
{
    MPVST_UI_ALIGNAS(8) uint64_t sequence;
    uint32_t kind;
    uint32_t parameter_id;
    float value;
    uint32_t reserved0;
    uint64_t reserved1;
} mpvst_ui_edit;

MPVST_UI_STATIC_ASSERT(sizeof(mpvst_ui_state) == 128, "ui state ABI");
MPVST_UI_STATIC_ASSERT(sizeof(mpvst_ui_rect) == 16, "ui rect ABI");
MPVST_UI_STATIC_ASSERT(sizeof(mpvst_ui_input) == 32, "ui input ABI");
MPVST_UI_STATIC_ASSERT(sizeof(mpvst_ui_edit) == 32, "ui edit ABI");
MPVST_UI_STATIC_ASSERT(offsetof(mpvst_ui_state, frame_sequence) == 48,
                       "ui frame sequence offset ABI");
MPVST_UI_STATIC_ASSERT(offsetof(mpvst_ui_state, editor_open) == 112,
                       "ui editor_open offset ABI");
MPVST_UI_STATIC_ASSERT(offsetof(mpvst_ui_input, wheel_vertical) == 24,
                       "ui wheel offset ABI");

/* The layout is arithmetic on compile-time constants, so it lives in the
   header as inline functions rather than in a library. Both consumers need
   it, and only one of them can link C++: the engine reaches this file from
   the `vstui` usermod, which is C compiled into the MicroPython binary and
   never sees mpvst_protocol. One definition, no second copy to drift. */

#include <string.h>

#if defined(__cplusplus)
#define MPVST_UI_INLINE inline
#else
#define MPVST_UI_INLINE static inline
#endif

/* Every region is 64-byte aligned and derived, never stored: a reader
   recomputes the offsets and compares, so a mapping can never hand out an
   attacker-chosen pointer. */
MPVST_UI_INLINE uint64_t mpvst_ui_align_up(uint64_t value)
{
    const uint64_t alignment = MPVST_UI_CACHE_LINE_BYTES;
    return (value + alignment - 1u) & ~(alignment - 1u);
}

MPVST_UI_INLINE uint64_t mpvst_ui_rects_offset(void)
{
    return mpvst_ui_align_up(sizeof(mpvst_ui_state));
}

MPVST_UI_INLINE uint64_t mpvst_ui_inputs_offset(void)
{
    return mpvst_ui_align_up(mpvst_ui_rects_offset() +
                             (uint64_t)MPVST_UI_RECT_CAPACITY * sizeof(mpvst_ui_rect));
}

MPVST_UI_INLINE uint64_t mpvst_ui_edits_offset(void)
{
    return mpvst_ui_align_up(mpvst_ui_inputs_offset() +
                             (uint64_t)MPVST_UI_INPUT_CAPACITY * sizeof(mpvst_ui_input));
}

MPVST_UI_INLINE uint64_t mpvst_ui_framebuffer_offset(void)
{
    return mpvst_ui_align_up(mpvst_ui_edits_offset() +
                             (uint64_t)MPVST_UI_EDIT_CAPACITY * sizeof(mpvst_ui_edit));
}

/* Bytes per framebuffer row at the maximum width. The logical size indexes
   into this stride, so it never changes. */
MPVST_UI_INLINE uint64_t mpvst_ui_stride_bytes(void)
{
    return (uint64_t)MPVST_UI_MAX_WIDTH * MPVST_UI_PIXEL_BYTES;
}

MPVST_UI_INLINE uint64_t mpvst_ui_framebuffer_bytes(void)
{
    return mpvst_ui_stride_bytes() * MPVST_UI_MAX_HEIGHT;
}

MPVST_UI_INLINE uint64_t mpvst_ui_mapping_bytes(void)
{
    return mpvst_ui_align_up(mpvst_ui_framebuffer_offset() +
                             mpvst_ui_framebuffer_bytes());
}

MPVST_UI_INLINE mpvst_ui_rect* mpvst_ui_rects(void* mapping)
{
    return (mpvst_ui_rect*)((uint8_t*)mapping + mpvst_ui_rects_offset());
}

MPVST_UI_INLINE mpvst_ui_input* mpvst_ui_inputs(void* mapping)
{
    return (mpvst_ui_input*)((uint8_t*)mapping + mpvst_ui_inputs_offset());
}

MPVST_UI_INLINE mpvst_ui_edit* mpvst_ui_edits(void* mapping)
{
    return (mpvst_ui_edit*)((uint8_t*)mapping + mpvst_ui_edits_offset());
}

MPVST_UI_INLINE uint8_t* mpvst_ui_framebuffer(void* mapping)
{
    return (uint8_t*)mapping + mpvst_ui_framebuffer_offset();
}

/* Zero the mapping and write a valid state block. Returns 0 when the mapping
   is null or the wrong size. `generation` is the plug-in's own restart
   counter, so a view holding a stale mapping notices the change. */
MPVST_UI_INLINE int mpvst_ui_initialize(void* mapping, uint64_t mapping_bytes,
                                        uint32_t generation)
{
    mpvst_ui_state* state;
    if (mapping == NULL || mapping_bytes != mpvst_ui_mapping_bytes())
        return 0;
    memset(mapping, 0, (size_t)mapping_bytes);
    state = (mpvst_ui_state*)mapping;
    state->magic = MPVST_UI_MAGIC;
    state->ui_major = MPVST_UI_MAJOR;
    state->ui_minor = MPVST_UI_MINOR;
    state->state_bytes = (uint32_t)sizeof(mpvst_ui_state);
    state->endian_marker = MPVST_UI_ENDIAN_MARKER;
    state->mapping_bytes = mapping_bytes;
    state->max_width = MPVST_UI_MAX_WIDTH;
    state->max_height = MPVST_UI_MAX_HEIGHT;
    state->width = MPVST_UI_DEFAULT_WIDTH;
    state->height = MPVST_UI_DEFAULT_HEIGHT;
    state->pixel_format = MPVST_UI_PIXEL_RGB565;
    state->content_scale_ppm = MPVST_UI_SCALE_UNITY;
    state->generation = generation;
    return 1;
}

/* True when the mapping carries a state block this build understands. */
MPVST_UI_INLINE int mpvst_ui_validate(const void* mapping, uint64_t mapping_bytes)
{
    const mpvst_ui_state* state;
    if (mapping == NULL || mapping_bytes != mpvst_ui_mapping_bytes())
        return 0;
    state = (const mpvst_ui_state*)mapping;
    return state->magic == MPVST_UI_MAGIC && state->ui_major == MPVST_UI_MAJOR &&
           state->state_bytes == (uint32_t)sizeof(mpvst_ui_state) &&
           state->endian_marker == MPVST_UI_ENDIAN_MARKER &&
           state->mapping_bytes == mapping_bytes &&
           state->max_width == MPVST_UI_MAX_WIDTH &&
           state->max_height == MPVST_UI_MAX_HEIGHT &&
           state->pixel_format == MPVST_UI_PIXEL_RGB565 &&
           state->width != 0u && state->width <= MPVST_UI_MAX_WIDTH &&
           state->height != 0u && state->height <= MPVST_UI_MAX_HEIGHT;
}

#undef MPVST_UI_ALIGNAS
#undef MPVST_UI_STATIC_ASSERT
#undef MPVST_UI_INLINE
