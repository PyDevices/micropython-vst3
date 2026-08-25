#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>

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

static HANDLE vstaudio_mapping_handle;
static void *vstaudio_mapping;
static uint64_t vstaudio_mapping_bytes;
static mpvst_shared_header *vstaudio_header;
static mpvst_status *vstaudio_status;
static mpvst_command *vstaudio_commands;
static mpvst_event *vstaudio_events;
static mpvst_work_slot *vstaudio_work;
static uint8_t *vstaudio_outputs;
static const int16_t *vstaudio_source_samples;
static uint32_t vstaudio_source_frames;
static uint32_t vstaudio_source_offset;

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

static void close_mapping(void) {
    if (vstaudio_mapping != NULL) {
        UnmapViewOfFile(vstaudio_mapping);
    }
    if (vstaudio_mapping_handle != NULL) {
        CloseHandle(vstaudio_mapping_handle);
    }
    vstaudio_mapping_handle = NULL;
    vstaudio_mapping = NULL;
    vstaudio_mapping_bytes = 0;
    vstaudio_header = NULL;
    vstaudio_status = NULL;
    vstaudio_commands = NULL;
    vstaudio_events = NULL;
    vstaudio_work = NULL;
    vstaudio_outputs = NULL;
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

// Monotonic nanoseconds for per-block render timing. The division is split so
// that a long-running counter cannot overflow before it is scaled.
static uint64_t monotonic_ns(void) {
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

    mpvst_shared_header *header = (mpvst_shared_header *)mapping;
    if (bytes < sizeof(*header) || header->magic != MPVST_PROTOCOL_MAGIC ||
        header->protocol_major != MPVST_PROTOCOL_MAJOR ||
        header->header_bytes != sizeof(*header) ||
        header->endian_marker != MPVST_ENDIAN_MARKER ||
        header->mapping_bytes != bytes || header->channel_count != 2u ||
        header->max_frames == 0u || header->sample_rate_millihz == 0u) {
        UnmapViewOfFile(mapping);
        CloseHandle(handle);
        mp_raise_ValueError(MP_ERROR_TEXT("invalid MPVST mapping"));
    }

    vstaudio_mapping_handle = handle;
    vstaudio_mapping = mapping;
    vstaudio_mapping_bytes = bytes;
    vstaudio_header = header;
    vstaudio_status = (mpvst_status *)((uint8_t *)mapping + header->status_offset);
    vstaudio_commands = (mpvst_command *)((uint8_t *)mapping + header->commands_offset);
    vstaudio_events = (mpvst_event *)((uint8_t *)mapping + header->events_offset);
    vstaudio_work = (mpvst_work_slot *)((uint8_t *)mapping + header->work_offset);
    vstaudio_outputs = (uint8_t *)mapping + header->outputs_offset;
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
    audiosample_reset_buffer(sample_obj, false, 0);
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
            Sleep(1);
            continue;
        }

        process_commands(&command_position, reload_callback);

        mpvst_work_slot *work = &vstaudio_work[work_position % vstaudio_header->work_slot_count];
        mpvst_output_slot *output = output_at(output_position);
        if (atomic_load_u64(&work->sequence) != work_position + 1u ||
            atomic_load_u64(&output->sequence) != output_position) {
            Sleep(0);
            continue;
        }

        output->generation = work->generation;
        output->frame_count = work->frame_count;
        output->start_sample = work->start_sample;
        output->channel_count = 2u;
        output->flags = MPVST_OUTPUT_FLAG_SILENT;
        const uint64_t render_started_ns = monotonic_ns();
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

static const mp_rom_map_elem_t vstaudio_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_vstaudio) },
    { MP_ROM_QSTR(MP_QSTR_configure), MP_ROM_PTR(&vstaudio_configure_obj) },
    { MP_ROM_QSTR(MP_QSTR_sample_rate), MP_ROM_PTR(&vstaudio_sample_rate_obj) },
    { MP_ROM_QSTR(MP_QSTR_output), MP_ROM_PTR(&vstaudio_output_obj) },
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
};
static MP_DEFINE_CONST_DICT(vstaudio_module_globals, vstaudio_module_globals_table);

const mp_obj_module_t vstaudio_module = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&vstaudio_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_vstaudio, vstaudio_module);
