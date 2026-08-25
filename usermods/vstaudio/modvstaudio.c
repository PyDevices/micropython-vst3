// The engine runs on Windows and on Unix. Only three things differ: opening the
// shared mapping the host created, reading a monotonic clock, and yielding.
#if defined(_WIN32)
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#else
#include <errno.h>
#include <fcntl.h>
#include <sched.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>
#endif

#include "mpvst/protocol.h"

#include "audiocore/__init__.h"
#include "synthio/Synthesizer.h"
#include "py/mperrno.h"
#include "py/mphal.h"
#include "py/obj.h"
#include "py/runtime.h"

#include <math.h>
#include <stdint.h>
#include <string.h>

MP_REGISTER_ROOT_POINTER(mp_obj_t vstaudio_output);
MP_REGISTER_ROOT_POINTER(mp_obj_t vstaudio_event_callback);

#if defined(_WIN32)
static HANDLE vstaudio_mapping_handle;
#endif
static void *vstaudio_mapping;
static uint64_t vstaudio_mapping_bytes;
static mpvst_shared_header *vstaudio_header;
static mpvst_status *vstaudio_status;
static mpvst_command *vstaudio_commands;
static mpvst_event *vstaudio_events;
static mpvst_work_slot *vstaudio_work;
static uint8_t *vstaudio_outputs;
static uint8_t *vstaudio_inputs;
static const int16_t *vstaudio_source_samples;
static uint32_t vstaudio_source_frames;
static uint32_t vstaudio_source_offset;

// Host input audio, effect instances only. The run loop converts each work
// slot's float32 block to interleaved int16 into this ring, and the script
// reads it through the audiosample object vstaudio.input() returns, so the
// whole audioif effect library can chain from the host bus. When a chain's
// internal buffering pulls ahead of what the host has delivered, the source
// hands out silence instead - self-priming to exactly the chain's depth.
#define VSTAUDIO_INPUT_FIFO_FRAMES 8192u
#define VSTAUDIO_INPUT_CHUNK_FRAMES 256u
static int16_t vstaudio_input_fifo[VSTAUDIO_INPUT_FIFO_FRAMES * 2u];
static int16_t vstaudio_input_silence[VSTAUDIO_INPUT_CHUNK_FRAMES * 2u];
static uint32_t vstaudio_input_read;
static uint32_t vstaudio_input_write;
static uint64_t vstaudio_input_underflows;

typedef struct vstaudio_input_obj {
    audiosample_base_t base;
} vstaudio_input_obj_t;

#if defined(_WIN32)

static uint64_t atomic_load_u64(const uint64_t *value) {
    return (uint64_t)InterlockedCompareExchange64(
        (volatile LONG64 *)(uintptr_t)value, 0, 0);
}

static void atomic_store_u64(uint64_t *value, uint64_t desired) {
    (void)InterlockedExchange64((volatile LONG64 *)(uintptr_t)value, (LONG64)desired);
}

static void atomic_increment_u64(uint64_t *value) {
    (void)InterlockedIncrement64((volatile LONG64 *)(uintptr_t)value);
}

static uint32_t atomic_load_u32(const uint32_t *value) {
    return (uint32_t)InterlockedCompareExchange(
        (volatile LONG *)(uintptr_t)value, 0, 0);
}

static void atomic_store_u32(uint32_t *value, uint32_t desired) {
    (void)InterlockedExchange((volatile LONG *)(uintptr_t)value, (LONG)desired);
}

#else

// GCC and Clang provide the same sequentially consistent operations the
// Interlocked family gives on Windows, which is what the ring protocol's
// publish and acquire steps rely on.
static uint64_t atomic_load_u64(const uint64_t *value) {
    return __atomic_load_n(value, __ATOMIC_SEQ_CST);
}

static void atomic_store_u64(uint64_t *value, uint64_t desired) {
    __atomic_store_n(value, desired, __ATOMIC_SEQ_CST);
}

static void atomic_increment_u64(uint64_t *value) {
    (void)__atomic_add_fetch(value, 1u, __ATOMIC_SEQ_CST);
}

static uint32_t atomic_load_u32(const uint32_t *value) {
    return __atomic_load_n(value, __ATOMIC_SEQ_CST);
}

static void atomic_store_u32(uint32_t *value, uint32_t desired) {
    __atomic_store_n(value, desired, __ATOMIC_SEQ_CST);
}

#endif

static void close_mapping(void) {
#if defined(_WIN32)
    if (vstaudio_mapping != NULL) {
        UnmapViewOfFile(vstaudio_mapping);
    }
    if (vstaudio_mapping_handle != NULL) {
        CloseHandle(vstaudio_mapping_handle);
    }
    vstaudio_mapping_handle = NULL;
#else
    if (vstaudio_mapping != NULL) {
        (void)munmap(vstaudio_mapping, (size_t)vstaudio_mapping_bytes);
    }
#endif
    vstaudio_mapping = NULL;
    vstaudio_mapping_bytes = 0;
    vstaudio_header = NULL;
    vstaudio_status = NULL;
    vstaudio_commands = NULL;
    vstaudio_events = NULL;
    vstaudio_work = NULL;
    vstaudio_outputs = NULL;
    vstaudio_inputs = NULL;
    vstaudio_input_read = 0u;
    vstaudio_input_write = 0u;
}

static uint64_t output_stride(void) {
    uint64_t bytes = sizeof(mpvst_output_slot) +
        (uint64_t)vstaudio_header->max_frames * vstaudio_header->channel_count * sizeof(float);
    return (bytes + MPVST_CACHE_LINE_BYTES - 1u) & ~(uint64_t)(MPVST_CACHE_LINE_BYTES - 1u);
}

static mpvst_output_slot *output_at(uint64_t position) {
    return (mpvst_output_slot *)(vstaudio_outputs +
        (position % vstaudio_header->output_slot_count) * output_stride());
}

static float *output_channel(mpvst_output_slot *slot, uint32_t channel) {
    float *samples = (float *)((uint8_t *)slot + sizeof(mpvst_output_slot));
    return samples + (uint64_t)vstaudio_header->max_frames * channel;
}

static uint64_t input_stride(void) {
    uint64_t bytes = (uint64_t)vstaudio_header->max_frames *
        vstaudio_header->channel_count * sizeof(float);
    return (bytes + MPVST_CACHE_LINE_BYTES - 1u) & ~(uint64_t)(MPVST_CACHE_LINE_BYTES - 1u);
}

static const float *input_channel(uint32_t slot_index, uint32_t channel) {
    const uint8_t *block = vstaudio_inputs +
        (uint64_t)(slot_index % vstaudio_header->work_slot_count) * input_stride();
    return (const float *)block + (uint64_t)vstaudio_header->max_frames * channel;
}

static void deposit_input(const mpvst_work_slot *work, uint64_t work_position) {
    if (vstaudio_inputs == NULL) {
        return;
    }
    const uint32_t slot_index =
        (uint32_t)(work_position % vstaudio_header->work_slot_count);
    const float *left = input_channel(slot_index, 0u);
    const float *right = input_channel(slot_index, 1u);
    for (uint32_t frame = 0; frame < work->frame_count; ++frame) {
        if (vstaudio_input_write - vstaudio_input_read >=
            VSTAUDIO_INPUT_FIFO_FRAMES) {
            ++vstaudio_input_read;  // drop the oldest; the script is not reading
        }
        const uint32_t at = (vstaudio_input_write % VSTAUDIO_INPUT_FIFO_FRAMES) * 2u;
        // Symmetric conversion so int16-sourced audio round-trips exactly:
        // the output path divides by 32768, so scaling by 32768 here makes a
        // pass-through effect bit-transparent.
        float l = left[frame] * 32768.0f;
        float r = right[frame] * 32768.0f;
        if (l > 32767.0f) { l = 32767.0f; } else if (l < -32768.0f) { l = -32768.0f; }
        if (r > 32767.0f) { r = 32767.0f; } else if (r < -32768.0f) { r = -32768.0f; }
        vstaudio_input_fifo[at] = (int16_t)lrintf(l);
        vstaudio_input_fifo[at + 1u] = (int16_t)lrintf(r);
        ++vstaudio_input_write;
    }
}

// Monotonic nanoseconds for per-block render timing. The division is split so
// that a long-running counter cannot overflow before it is scaled.
static uint64_t monotonic_ns(void) {
#if defined(_WIN32)
    static LARGE_INTEGER frequency;
    if (frequency.QuadPart == 0) {
        QueryPerformanceFrequency(&frequency);
    }
    LARGE_INTEGER counter;
    QueryPerformanceCounter(&counter);
    const uint64_t ticks = (uint64_t)counter.QuadPart;
    const uint64_t freq = (uint64_t)frequency.QuadPart;
    if (freq == 0u) {
        return 0u;
    }
    return (ticks / freq) * 1000000000ull + ((ticks % freq) * 1000000000ull) / freq;
#else
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC, &now) != 0) {
        return 0u;
    }
    return (uint64_t)now.tv_sec * 1000000000ull + (uint64_t)now.tv_nsec;
#endif
}

// Wait a moment without burning the core. The engine only ever waits for the
// host to hand it work, so a millisecond of latency here costs nothing.
static void engine_idle(void) {
#if defined(_WIN32)
    Sleep(1);
#else
    const struct timespec delay = {0, 1000000L};
    (void)nanosleep(&delay, NULL);
#endif
}

// Give up the rest of this scheduling slice while spinning for a slot.
static void engine_yield(void) {
#if defined(_WIN32)
    Sleep(0);
#else
    (void)sched_yield();
#endif
}

static void set_error_text(const char *text, size_t length, uint32_t error_code) {
    if (vstaudio_status == NULL) {
        return;
    }
    if (length >= MPVST_DIAGNOSTIC_BYTES) {
        length = MPVST_DIAGNOSTIC_BYTES - 1u;
        vstaudio_status->diagnostic_flags = 1u;
    } else {
        vstaudio_status->diagnostic_flags = 0u;
    }
    memcpy(vstaudio_status->diagnostic, text, length);
    vstaudio_status->diagnostic[length] = '\0';
    vstaudio_status->diagnostic_size = (uint32_t)length;
    vstaudio_status->error_code = error_code;
}

static mp_obj_t vstaudio_configure(mp_obj_t name_obj, mp_obj_t bytes_obj) {
    close_mapping();
    const char *name = mp_obj_str_get_str(name_obj);
    uint64_t bytes = (uint64_t)mp_obj_get_int(bytes_obj);
#if defined(_WIN32)
    HANDLE handle = OpenFileMappingA(FILE_MAP_ALL_ACCESS, FALSE, name);
    if (handle == NULL) {
        mp_raise_OSError(GetLastError());
    }
    void *mapping = MapViewOfFile(handle, FILE_MAP_ALL_ACCESS, 0, 0, (SIZE_T)bytes);
    if (mapping == NULL) {
        DWORD error = GetLastError();
        CloseHandle(handle);
        mp_raise_OSError(error);
    }
#else
    const int descriptor = shm_open(name, O_RDWR, 0600);
    if (descriptor < 0) {
        mp_raise_OSError(errno);
    }
    void *mapping = mmap(NULL, (size_t)bytes, PROT_READ | PROT_WRITE, MAP_SHARED,
                         descriptor, 0);
    const int map_error = errno;
    (void)close(descriptor);
    if (mapping == MAP_FAILED) {
        mp_raise_OSError(map_error);
    }
#endif

    mpvst_shared_header *header = (mpvst_shared_header *)mapping;
    if (bytes < sizeof(*header) || header->magic != MPVST_PROTOCOL_MAGIC ||
        header->protocol_major != MPVST_PROTOCOL_MAJOR ||
        header->header_bytes != sizeof(*header) ||
        header->endian_marker != MPVST_ENDIAN_MARKER ||
        header->mapping_bytes != bytes || header->channel_count != 2u ||
        header->max_frames == 0u || header->sample_rate_millihz == 0u) {
#if defined(_WIN32)
        UnmapViewOfFile(mapping);
        CloseHandle(handle);
#else
        (void)munmap(mapping, (size_t)bytes);
#endif
        mp_raise_ValueError(MP_ERROR_TEXT("invalid MPVST mapping"));
    }
    const uint64_t expected_input_bytes = (uint64_t)header->work_slot_count *
        (((uint64_t)header->max_frames * header->channel_count * sizeof(float) +
          MPVST_CACHE_LINE_BYTES - 1u) & ~(uint64_t)(MPVST_CACHE_LINE_BYTES - 1u));
    if (header->optional_bytes != 0u &&
        header->optional_bytes != expected_input_bytes) {
#if defined(_WIN32)
        UnmapViewOfFile(mapping);
        CloseHandle(handle);
#else
        (void)munmap(mapping, (size_t)bytes);
#endif
        mp_raise_ValueError(MP_ERROR_TEXT("invalid MPVST input region"));
    }

#if defined(_WIN32)
    vstaudio_mapping_handle = handle;
#endif
    vstaudio_mapping = mapping;
    vstaudio_mapping_bytes = bytes;
    vstaudio_header = header;
    vstaudio_status = (mpvst_status *)((uint8_t *)mapping + header->status_offset);
    vstaudio_commands = (mpvst_command *)((uint8_t *)mapping + header->commands_offset);
    vstaudio_events = (mpvst_event *)((uint8_t *)mapping + header->events_offset);
    vstaudio_work = (mpvst_work_slot *)((uint8_t *)mapping + header->work_offset);
    vstaudio_outputs = (uint8_t *)mapping + header->outputs_offset;
    vstaudio_inputs = header->optional_bytes != 0u
        ? (uint8_t *)mapping + header->optional_offset : NULL;
    vstaudio_input_read = 0u;
    vstaudio_input_write = 0u;
    vstaudio_input_underflows = 0u;
    MP_STATE_VM(vstaudio_output) = MP_OBJ_NULL;
    MP_STATE_VM(vstaudio_event_callback) = MP_OBJ_NULL;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(vstaudio_configure_obj, vstaudio_configure);

static mp_obj_t vstaudio_sample_rate(void) {
    if (vstaudio_header == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("vstaudio is not configured"));
    }
    return mp_obj_new_int_from_ull(vstaudio_header->sample_rate_millihz / 1000u);
}
static MP_DEFINE_CONST_FUN_OBJ_0(vstaudio_sample_rate_obj, vstaudio_sample_rate);

static mp_obj_t vstaudio_output(mp_obj_t sample_obj) {
    audiosample_base_t *sample = audiosample_check(sample_obj);
    if (sample->bits_per_sample != 16u || !sample->samples_signed ||
        (sample->channel_count != 1u && sample->channel_count != 2u)) {
        mp_raise_ValueError(MP_ERROR_TEXT("output must be signed 16-bit mono or stereo"));
    }
    MP_STATE_VM(vstaudio_output) = sample_obj;
    vstaudio_source_samples = NULL;
    vstaudio_source_frames = 0u;
    vstaudio_source_offset = 0u;
    // Deliberately no audiosample_reset_buffer here: audiomixer's reset stops
    // every voice, so resetting on registration would silence the idiomatic
    // "start voices, then output(mixer)" script. A reload builds a fresh
    // interpreter, so there is no stale playback state to clear anyway.
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(vstaudio_output_obj, vstaudio_output);

static mp_obj_t vstaudio_clear_output(void) {
    MP_STATE_VM(vstaudio_output) = MP_OBJ_NULL;
    MP_STATE_VM(vstaudio_event_callback) = MP_OBJ_NULL;
    vstaudio_source_samples = NULL;
    vstaudio_source_frames = 0u;
    vstaudio_source_offset = 0u;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(vstaudio_clear_output_obj, vstaudio_clear_output);

static void vstaudio_input_reset_buffer(mp_obj_t self_in,
    bool single_channel_output, uint8_t audio_channel) {
    (void)self_in;
    (void)single_channel_output;
    (void)audio_channel;
    vstaudio_input_read = vstaudio_input_write;
}

static audioio_get_buffer_result_t vstaudio_input_get_buffer(mp_obj_t self_in,
    bool single_channel_output, uint8_t channel, uint8_t **buffer,
    uint32_t *buffer_length) {
    (void)self_in;
    (void)single_channel_output;
    (void)channel;
    const uint32_t available = vstaudio_input_write - vstaudio_input_read;
    if (available == 0u) {
        // The chain wants audio the host has not delivered yet. Handing out a
        // silent chunk instead of blocking lets an effect's internal buffering
        // prime itself with exactly as much lead as it needs, once.
        ++vstaudio_input_underflows;
        *buffer = (uint8_t *)vstaudio_input_silence;
        *buffer_length = (uint32_t)sizeof(vstaudio_input_silence);
        return GET_BUFFER_MORE_DATA;
    }
    const uint32_t start = vstaudio_input_read % VSTAUDIO_INPUT_FIFO_FRAMES;
    uint32_t run = VSTAUDIO_INPUT_FIFO_FRAMES - start;
    if (run > available) {
        run = available;
    }
    if (run > VSTAUDIO_INPUT_CHUNK_FRAMES) {
        run = VSTAUDIO_INPUT_CHUNK_FRAMES;
    }
    *buffer = (uint8_t *)&vstaudio_input_fifo[start * 2u];
    *buffer_length = run * 2u * (uint32_t)sizeof(int16_t);
    vstaudio_input_read += run;
    return GET_BUFFER_MORE_DATA;
}

static const audiosample_p_t vstaudio_input_proto = {
    MP_PROTO_IMPLEMENT(MP_QSTR_protocol_audiosample)
    .reset_buffer = vstaudio_input_reset_buffer,
    .get_buffer = vstaudio_input_get_buffer,
};

MP_DEFINE_CONST_OBJ_TYPE(
    vstaudio_input_type,
    MP_QSTR_InputStream,
    MP_TYPE_FLAG_NONE,
    protocol, &vstaudio_input_proto
    );

static vstaudio_input_obj_t vstaudio_input_singleton;

static mp_obj_t vstaudio_input(void) {
    if (vstaudio_header == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("vstaudio is not configured"));
    }
    vstaudio_input_singleton.base.self.type = &vstaudio_input_type;
    vstaudio_input_singleton.base.sample_rate =
        (uint32_t)(vstaudio_header->sample_rate_millihz / 1000u);
    vstaudio_input_singleton.base.max_buffer_length =
        VSTAUDIO_INPUT_CHUNK_FRAMES * 2u * (uint32_t)sizeof(int16_t);
    vstaudio_input_singleton.base.bits_per_sample = 16u;
    vstaudio_input_singleton.base.channel_count = 2u;
    vstaudio_input_singleton.base.samples_signed = 1u;
    vstaudio_input_singleton.base.single_buffer = false;
    return MP_OBJ_FROM_PTR(&vstaudio_input_singleton);
}
static MP_DEFINE_CONST_FUN_OBJ_0(vstaudio_input_obj_fun, vstaudio_input);

// (frames_written, frames_read, underflow_chunks, region_present) - how the
// input stream is flowing, for effect scripts that want to report on it.
static mp_obj_t vstaudio_input_stats(void) {
    mp_obj_t items[4] = {
        mp_obj_new_int_from_ull(vstaudio_input_write),
        mp_obj_new_int_from_ull(vstaudio_input_read),
        mp_obj_new_int_from_ull(vstaudio_input_underflows),
        vstaudio_inputs != NULL ? mp_const_true : mp_const_false,
    };
    return mp_obj_new_tuple(4, items);
}
static MP_DEFINE_CONST_FUN_OBJ_0(vstaudio_input_stats_obj, vstaudio_input_stats);

// The work slot being rendered right now, so a script can ask where the host
// transport is without the engine having to copy the fields out every block.
static const mpvst_work_slot *vstaudio_current_work;

static mp_obj_t vstaudio_transport(void) {
    const mpvst_work_slot *work = vstaudio_current_work;
    mp_obj_t items[5];
    if (work == NULL) {
        items[0] = mp_const_false;
        items[1] = mp_obj_new_float(0.0f);
        items[2] = mp_obj_new_float(120.0f);
        items[3] = MP_OBJ_NEW_SMALL_INT(4);
        items[4] = MP_OBJ_NEW_SMALL_INT(4);
        return mp_obj_new_tuple(5, items);
    }
    const uint64_t rate = work->sample_rate_millihz / 1000u;
    items[0] = (work->flags & MPVST_WORK_FLAG_PLAYING) != 0u
        ? mp_const_true : mp_const_false;
    items[1] = mp_obj_new_float(rate != 0u
        ? (mp_float_t)work->transport_sample / (mp_float_t)rate
        : (mp_float_t)0.0);
    items[2] = mp_obj_new_float((mp_float_t)work->tempo_micro_bpm / (mp_float_t)1000000.0);
    items[3] = MP_OBJ_NEW_SMALL_INT(work->time_signature_numerator);
    items[4] = MP_OBJ_NEW_SMALL_INT(work->time_signature_denominator);
    return mp_obj_new_tuple(5, items);
}
static MP_DEFINE_CONST_FUN_OBJ_0(vstaudio_transport_obj, vstaudio_transport);

static mp_obj_t vstaudio_on_event(mp_obj_t callback) {
    if (callback != mp_const_none && !mp_obj_is_callable(callback)) {
        mp_raise_TypeError(MP_ERROR_TEXT("event callback must be callable or None"));
    }
    MP_STATE_VM(vstaudio_event_callback) = callback == mp_const_none
        ? MP_OBJ_NULL : callback;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(vstaudio_on_event_obj, vstaudio_on_event);

static void dispatch_event(const mpvst_event *event) {
    mp_obj_t callback = MP_STATE_VM(vstaudio_event_callback);
    if (callback == MP_OBJ_NULL) {
        return;
    }
    mp_obj_t args[7] = {
        mp_obj_new_int_from_uint(event->type),
        mp_obj_new_int_from_uint(event->channel),
        mp_obj_new_int(event->note_id),
        mp_obj_new_int(event->data0),
        mp_obj_new_float(event->value0),
        mp_obj_new_float(event->value1),
        mp_obj_new_int_from_ll(event->sample_position),
    };
    mp_call_function_n_kw(callback, 7, 0, args);
}

static mp_obj_t vstaudio_error(mp_obj_t message_obj) {
    size_t length = 0;
    const char *text = mp_obj_str_get_data(message_obj, &length);
    set_error_text(text, length, length == 0u ? 0u : 1u);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(vstaudio_error_obj, vstaudio_error);

static bool pull_source_frame(float *left, float *right,
    uint32_t requested_frames, bool event_bounded) {
    mp_obj_t source = MP_STATE_VM(vstaudio_output);
    if (source == MP_OBJ_NULL) {
        return false;
    }
    audiosample_base_t *base = MP_OBJ_TO_PTR(source);
    while (vstaudio_source_offset >= vstaudio_source_frames) {
        uint8_t *buffer = NULL;
        uint32_t buffer_bytes = 0u;
        audioio_get_buffer_result_t result;
        if (event_bounded && requested_frames != 0u &&
            mp_obj_is_type(source, &synthio_synthesizer_type)) {
            synthio_synthesizer_obj_t *synth = MP_OBJ_TO_PTR(source);
            synth->synth.span.dur = requested_frames < SYNTHIO_MAX_DUR
                ? (uint16_t)requested_frames : SYNTHIO_MAX_DUR;
            synthio_synth_synthesize(&synth->synth, &buffer, &buffer_bytes, 0u);
            result = GET_BUFFER_MORE_DATA;
        } else {
            result = audiosample_get_buffer(
                source, false, 0, &buffer, &buffer_bytes);
        }
        if (result == GET_BUFFER_ERROR || buffer == NULL) {
            return false;
        }
        if (result == GET_BUFFER_DONE && buffer_bytes == 0u) {
            audiosample_reset_buffer(source, false, 0);
            continue;
        }
        vstaudio_source_samples = (const int16_t *)buffer;
        vstaudio_source_frames = buffer_bytes /
            ((uint32_t)sizeof(int16_t) * base->channel_count);
        vstaudio_source_offset = 0u;
        if (vstaudio_source_frames == 0u) {
            return false;
        }
    }

    const uint32_t index = vstaudio_source_offset * base->channel_count;
    *left = (float)vstaudio_source_samples[index] / 32768.0f;
    *right = base->channel_count == 2u
        ? (float)vstaudio_source_samples[index + 1u] / 32768.0f
        : *left;
    ++vstaudio_source_offset;
    return true;
}

static void process_commands(uint64_t *command_position, mp_obj_t reload_callback) {
    for (;;) {
        mpvst_command *command = &vstaudio_commands[
            *command_position % vstaudio_header->command_capacity];
        if (atomic_load_u64(&command->sequence) != *command_position + 1u) {
            return;
        }
        if (command->generation == atomic_load_u32(&vstaudio_header->generation) &&
            command->type == MPVST_COMMAND_RELOAD) {
            nlr_buf_t nlr;
            if (nlr_push(&nlr) == 0) {
                mp_call_function_0(reload_callback);
                nlr_pop();
            } else {
                const char *message = "uncaught Python exception while reloading";
                vstaudio_clear_output();
                set_error_text(message, strlen(message), 3u);
            }
        }
        atomic_store_u64(&command->sequence,
            *command_position + vstaudio_header->command_capacity);
        ++*command_position;
    }
}

static mp_obj_t vstaudio_run(mp_obj_t reload_callback) {
    if (vstaudio_header == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("vstaudio is not configured"));
    }
    if (!mp_obj_is_callable(reload_callback)) {
        mp_raise_TypeError(MP_ERROR_TEXT("reload callback must be callable"));
    }

    uint64_t command_position = 0u;
    uint64_t work_position = 0u;
    uint64_t output_position = 0u;
    atomic_store_u32(&vstaudio_header->lifecycle, MPVST_LIFECYCLE_ENGINE_READY);
    for (;;) {
        uint32_t lifecycle = atomic_load_u32(&vstaudio_header->lifecycle);
        if (lifecycle == MPVST_LIFECYCLE_STOPPING) {
            break;
        }
        if (lifecycle != MPVST_LIFECYCLE_RUNNING) {
            engine_idle();
            continue;
        }

        process_commands(&command_position, reload_callback);

        mpvst_work_slot *work = &vstaudio_work[work_position % vstaudio_header->work_slot_count];
        mpvst_output_slot *output = output_at(output_position);
        if (atomic_load_u64(&work->sequence) != work_position + 1u ||
            atomic_load_u64(&output->sequence) != output_position) {
            engine_yield();
            continue;
        }

        output->generation = work->generation;
        output->frame_count = work->frame_count;
        output->start_sample = work->start_sample;
        output->channel_count = 2u;
        output->flags = MPVST_OUTPUT_FLAG_SILENT;
        const uint64_t render_started_ns = monotonic_ns();
        deposit_input(work, work_position);
        vstaudio_current_work = work;
        bool rendered = false;
        nlr_buf_t nlr;
        if (nlr_push(&nlr) == 0) {
            uint32_t event_index = 0u;
            for (uint32_t frame = 0; frame < work->frame_count; ++frame) {
                const int64_t sample_position = work->start_sample + frame;
                while (event_index < work->event_count) {
                    const mpvst_event *event = &vstaudio_events[
                        (work->event_first + event_index) % vstaudio_header->event_capacity];
                    if (event->sample_position > sample_position) {
                        break;
                    }
                    dispatch_event(event);
                    ++event_index;
                }
                uint32_t segment_frames = work->frame_count - frame;
                if (event_index < work->event_count) {
                    const mpvst_event *next_event = &vstaudio_events[
                        (work->event_first + event_index) % vstaudio_header->event_capacity];
                    const int64_t until_event = next_event->sample_position - sample_position;
                    if (until_event > 0 && (uint64_t)until_event < segment_frames) {
                        segment_frames = (uint32_t)until_event;
                    }
                }
                float left = 0.0f;
                float right = 0.0f;
                if (pull_source_frame(&left, &right, segment_frames,
                    work->event_count != 0u)) {
                    rendered = rendered || left != 0.0f || right != 0.0f;
                }
                output_channel(output, 0u)[frame] = left;
                output_channel(output, 1u)[frame] = right;
            }
            nlr_pop();
        } else {
            const char *message = "Python exception while rendering";
            set_error_text(message, strlen(message), 2u);
            for (uint32_t frame = 0; frame < work->frame_count; ++frame) {
                output_channel(output, 0u)[frame] = 0.0f;
                output_channel(output, 1u)[frame] = 0.0f;
            }
        }
        if (rendered) {
            output->flags = 0u;
        }

        atomic_store_u64(&vstaudio_status->events_consumed,
            atomic_load_u64(&vstaudio_status->events_consumed) + work->event_count);
        atomic_store_u64(&work->sequence, work_position + vstaudio_header->work_slot_count);
        vstaudio_current_work = NULL;
        output->render_time_ns = monotonic_ns() - render_started_ns;
        atomic_store_u64(&output->sequence, output_position + 1u);
        ++work_position;
        ++output_position;
        atomic_increment_u64(&vstaudio_status->engine_heartbeat);
        atomic_increment_u64(&vstaudio_status->blocks_rendered);
        mp_handle_pending(true);
    }

    atomic_store_u32(&vstaudio_header->lifecycle, MPVST_LIFECYCLE_STOPPED);
    close_mapping();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(vstaudio_run_obj, vstaudio_run);

extern const mp_obj_type_t vstaudio_dynamics_type;
extern const mp_obj_type_t vstaudio_splitter_type;

static const mp_rom_map_elem_t vstaudio_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_vstaudio) },
    { MP_ROM_QSTR(MP_QSTR_Dynamics), MP_ROM_PTR(&vstaudio_dynamics_type) },
    { MP_ROM_QSTR(MP_QSTR_Splitter), MP_ROM_PTR(&vstaudio_splitter_type) },
    { MP_ROM_QSTR(MP_QSTR_DYN_COMPRESS), MP_ROM_INT(0) },
    { MP_ROM_QSTR(MP_QSTR_DYN_LIMIT), MP_ROM_INT(1) },
    { MP_ROM_QSTR(MP_QSTR_DYN_EXPAND), MP_ROM_INT(2) },
    { MP_ROM_QSTR(MP_QSTR_DYN_GATE), MP_ROM_INT(3) },
    { MP_ROM_QSTR(MP_QSTR_DYN_TRANSIENT), MP_ROM_INT(4) },
    { MP_ROM_QSTR(MP_QSTR_configure), MP_ROM_PTR(&vstaudio_configure_obj) },
    { MP_ROM_QSTR(MP_QSTR_sample_rate), MP_ROM_PTR(&vstaudio_sample_rate_obj) },
    { MP_ROM_QSTR(MP_QSTR_output), MP_ROM_PTR(&vstaudio_output_obj) },
    { MP_ROM_QSTR(MP_QSTR_input), MP_ROM_PTR(&vstaudio_input_obj_fun) },
    { MP_ROM_QSTR(MP_QSTR_input_stats), MP_ROM_PTR(&vstaudio_input_stats_obj) },
    { MP_ROM_QSTR(MP_QSTR_clear_output), MP_ROM_PTR(&vstaudio_clear_output_obj) },
    { MP_ROM_QSTR(MP_QSTR_on_event), MP_ROM_PTR(&vstaudio_on_event_obj) },
    { MP_ROM_QSTR(MP_QSTR_error), MP_ROM_PTR(&vstaudio_error_obj) },
    { MP_ROM_QSTR(MP_QSTR_run), MP_ROM_PTR(&vstaudio_run_obj) },
    { MP_ROM_QSTR(MP_QSTR_EVENT_NOTE_ON), MP_ROM_INT(MPVST_EVENT_NOTE_ON) },
    { MP_ROM_QSTR(MP_QSTR_EVENT_NOTE_OFF), MP_ROM_INT(MPVST_EVENT_NOTE_OFF) },
    { MP_ROM_QSTR(MP_QSTR_EVENT_POLY_PRESSURE), MP_ROM_INT(MPVST_EVENT_POLY_PRESSURE) },
    { MP_ROM_QSTR(MP_QSTR_EVENT_PITCH_BEND), MP_ROM_INT(MPVST_EVENT_PITCH_BEND) },
    { MP_ROM_QSTR(MP_QSTR_EVENT_CONTROL_CHANGE), MP_ROM_INT(MPVST_EVENT_CONTROL_CHANGE) },
    { MP_ROM_QSTR(MP_QSTR_EVENT_PARAMETER), MP_ROM_INT(MPVST_EVENT_PARAMETER) },
    { MP_ROM_QSTR(MP_QSTR_EVENT_CHANNEL_PRESSURE), MP_ROM_INT(MPVST_EVENT_CHANNEL_PRESSURE) },
    { MP_ROM_QSTR(MP_QSTR_EVENT_TRANSPORT), MP_ROM_INT(MPVST_EVENT_TRANSPORT) },
    { MP_ROM_QSTR(MP_QSTR_EVENT_PROGRAM_CHANGE), MP_ROM_INT(MPVST_EVENT_PROGRAM_CHANGE) },
    { MP_ROM_QSTR(MP_QSTR_transport), MP_ROM_PTR(&vstaudio_transport_obj) },
};
static MP_DEFINE_CONST_DICT(vstaudio_module_globals, vstaudio_module_globals_table);

const mp_obj_module_t vstaudio_module = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&vstaudio_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_vstaudio, vstaudio_module);
