#pragma once

#include <stddef.h>
#include <stdint.h>

#if defined(__cplusplus)
#define MPVST_ALIGNAS(value) alignas(value)
#define MPVST_STATIC_ASSERT(condition, message) static_assert(condition, message)
#elif defined(_MSC_VER)
#define MPVST_ALIGNAS(value) __declspec(align(value))
#define MPVST_STATIC_ASSERT(condition, message) static_assert(condition, message)
#else
#define MPVST_ALIGNAS(value) __attribute__((aligned(value)))
#define MPVST_STATIC_ASSERT(condition, message) _Static_assert(condition, message)
#endif

#define MPVST_PROTOCOL_MAGIC UINT32_C(0x3356504d)
#define MPVST_PROTOCOL_MAJOR UINT16_C(1)
/* Minor 1 defines the optional region: when optional_bytes is non-zero it
   holds one input-audio block per work slot (planar float32, stereo,
   max_frames per channel, each block aligned to a cache line). The block for
   a work slot is written before the slot's sequence is published, so the
   consumer's acquire on the sequence covers the audio. A mapping with
   optional_bytes of zero is exactly a minor-0 mapping. */
#define MPVST_PROTOCOL_MINOR UINT16_C(1)
#define MPVST_ENDIAN_MARKER UINT32_C(0x01020304)
#define MPVST_CACHE_LINE_BYTES UINT32_C(64)
#define MPVST_DIAGNOSTIC_BYTES UINT32_C(56)
#define MPVST_CHANNEL_COUNT UINT32_C(2)
#define MPVST_WORK_FLAG_TEST_TONE UINT32_C(1)
/* The host transport was rolling when this block was submitted. */
#define MPVST_WORK_FLAG_PLAYING UINT32_C(2)
/* The host timeline jumped before this block: a locate, a loop wrap, or a
   change of play state. The block carries a transport event at the sample the
   jump takes effect so a script can release voices and reset. */
#define MPVST_WORK_FLAG_DISCONTINUITY UINT32_C(4)
#define MPVST_OUTPUT_FLAG_SILENT UINT32_C(1)

typedef enum mpvst_lifecycle
{
    MPVST_LIFECYCLE_EMPTY = 0,
    MPVST_LIFECYCLE_HOST_READY = 1,
    MPVST_LIFECYCLE_ENGINE_READY = 2,
    MPVST_LIFECYCLE_RUNNING = 3,
    MPVST_LIFECYCLE_STOPPING = 4,
    MPVST_LIFECYCLE_STOPPED = 5,
    MPVST_LIFECYCLE_FAILED = 6
} mpvst_lifecycle;

typedef enum mpvst_event_type
{
    MPVST_EVENT_NONE = 0,
    MPVST_EVENT_NOTE_ON = 1,
    MPVST_EVENT_NOTE_OFF = 2,
    MPVST_EVENT_POLY_PRESSURE = 3,
    MPVST_EVENT_PITCH_BEND = 4,
    MPVST_EVENT_CONTROL_CHANGE = 5,
    MPVST_EVENT_PARAMETER = 6,
    MPVST_EVENT_CHANNEL_PRESSURE = 7,
    /* Transport discontinuity. data0 is non-zero while the host is playing,
       value0 carries the new project position in seconds. */
    MPVST_EVENT_TRANSPORT = 8,
    /* Patch select. data0 is the program index 0-127; value0 is the same
       value normalized to 0.0-1.0. VST3 has no native "program change"
       input event, so the host maps an incoming MIDI Program Change
       message onto the plug-in's kIsProgramChange-flagged parameter, and
       that parameter change becomes this event. */
    MPVST_EVENT_PROGRAM_CHANGE = 9
} mpvst_event_type;

typedef enum mpvst_command_type
{
    MPVST_COMMAND_NONE = 0,
    MPVST_COMMAND_START = 1,
    MPVST_COMMAND_STOP = 2,
    MPVST_COMMAND_RESET = 3,
    MPVST_COMMAND_RELOAD = 4
} mpvst_command_type;

typedef struct MPVST_ALIGNAS(8) mpvst_shared_header
{
    uint32_t magic;
    uint16_t protocol_major;
    uint16_t protocol_minor;
    uint32_t header_bytes;
    uint32_t endian_marker;
    uint64_t mapping_bytes;
    uint32_t max_frames;
    uint32_t channel_count;
    uint32_t work_slot_count;
    uint32_t output_slot_count;
    uint32_t event_capacity;
    uint32_t command_capacity;
    uint64_t status_offset;
    uint64_t commands_offset;
    uint64_t events_offset;
    uint64_t work_offset;
    uint64_t outputs_offset;
    uint64_t optional_offset;
    uint64_t optional_bytes;
    uint64_t instance_nonce;
    MPVST_ALIGNAS(4) uint32_t generation;
    MPVST_ALIGNAS(4) uint32_t lifecycle;
    uint64_t sample_rate_millihz;
} mpvst_shared_header;

typedef struct MPVST_ALIGNAS(8) mpvst_status
{
    MPVST_ALIGNAS(8) uint64_t engine_heartbeat;
    MPVST_ALIGNAS(8) uint64_t blocks_requested;
    MPVST_ALIGNAS(8) uint64_t blocks_rendered;
    MPVST_ALIGNAS(8) uint64_t underruns;
    MPVST_ALIGNAS(8) uint64_t event_drops;
    MPVST_ALIGNAS(8) uint64_t restart_count;
    MPVST_ALIGNAS(8) uint64_t events_consumed;
    MPVST_ALIGNAS(4) uint32_t engine_state;
    MPVST_ALIGNAS(4) uint32_t error_code;
    uint32_t diagnostic_size;
    uint32_t diagnostic_flags;
    char diagnostic[MPVST_DIAGNOSTIC_BYTES];
} mpvst_status;

typedef struct MPVST_ALIGNAS(8) mpvst_command
{
    MPVST_ALIGNAS(8) uint64_t sequence;
    uint32_t generation;
    uint32_t type;
    uint64_t argument0;
    uint64_t argument1;
    uint8_t payload[32];
} mpvst_command;

typedef struct MPVST_ALIGNAS(8) mpvst_event
{
    int64_t sample_position;
    uint32_t type;
    uint16_t channel;
    uint16_t flags;
    int32_t note_id;
    int32_t data0;
    float value0;
    float value1;
} mpvst_event;

typedef struct MPVST_ALIGNAS(8) mpvst_work_slot
{
    MPVST_ALIGNAS(8) uint64_t sequence;
    uint32_t generation;
    uint32_t frame_count;
    int64_t start_sample;
    uint64_t sample_rate_millihz;
    int64_t transport_sample;
    uint32_t event_first;
    uint32_t event_count;
    uint32_t flags;
    uint16_t time_signature_numerator;
    uint16_t time_signature_denominator;
    uint64_t tempo_micro_bpm;
} mpvst_work_slot;

typedef struct MPVST_ALIGNAS(8) mpvst_output_slot
{
    MPVST_ALIGNAS(8) uint64_t sequence;
    uint32_t generation;
    uint32_t frame_count;
    int64_t start_sample;
    uint32_t flags;
    uint32_t channel_count;
    uint64_t render_time_ns;
    uint64_t reserved0;
    uint64_t reserved1;
    uint64_t reserved2;
} mpvst_output_slot;

typedef struct mpvst_layout_request
{
    uint32_t max_frames;
    uint32_t work_slot_count;
    uint32_t output_slot_count;
    uint32_t event_capacity;
    uint32_t command_capacity;
    /* Zero for an instrument. For an effect it must equal work_slot_count:
       every work slot then owns one input-audio block in the optional
       region. Aggregate initializers that omit it get zero, so existing
       instrument call sites are unchanged. */
    uint32_t input_slot_count;
} mpvst_layout_request;

MPVST_STATIC_ASSERT(sizeof(mpvst_shared_header) == 128, "shared header ABI");
MPVST_STATIC_ASSERT(sizeof(mpvst_status) == 128, "status ABI");
MPVST_STATIC_ASSERT(sizeof(mpvst_command) == 64, "command ABI");
MPVST_STATIC_ASSERT(sizeof(mpvst_event) == 32, "event ABI");
MPVST_STATIC_ASSERT(sizeof(mpvst_work_slot) == 64, "work slot ABI");
MPVST_STATIC_ASSERT(sizeof(mpvst_output_slot) == 64, "output slot ABI");
MPVST_STATIC_ASSERT(offsetof(mpvst_shared_header, generation) == 112,
                    "generation offset ABI");
MPVST_STATIC_ASSERT(offsetof(mpvst_work_slot, sequence) == 0,
                    "work sequence offset ABI");
MPVST_STATIC_ASSERT(offsetof(mpvst_output_slot, sequence) == 0,
                    "output sequence offset ABI");

#if defined(__cplusplus)
extern "C" {
#endif

uint64_t mpvst_compute_mapping_bytes(const mpvst_layout_request* request);
int mpvst_initialize_mapping(void* mapping, uint64_t mapping_bytes,
                             const mpvst_layout_request* request,
                             uint64_t instance_nonce);
int mpvst_validate_mapping(const void* mapping, uint64_t mapping_bytes);
void* mpvst_region(void* mapping, uint64_t offset);
const void* mpvst_const_region(const void* mapping, uint64_t offset);
uint64_t mpvst_output_stride_bytes(const mpvst_shared_header* header);
float* mpvst_output_channel(mpvst_output_slot* slot, uint32_t max_frames,
                            uint32_t channel);
const float* mpvst_const_output_channel(const mpvst_output_slot* slot,
                                        uint32_t max_frames, uint32_t channel);
/* Input-audio region accessors. The region exists when optional_bytes is
   non-zero; slot_index addresses the block owned by the work slot at the
   same ring position. Returns null when the mapping has no input region. */
uint64_t mpvst_input_stride_bytes(const mpvst_shared_header* header);
float* mpvst_input_channel(void* mapping, const mpvst_shared_header* header,
                           uint32_t slot_index, uint32_t channel);
const float* mpvst_const_input_channel(const void* mapping,
                                       const mpvst_shared_header* header,
                                       uint32_t slot_index, uint32_t channel);

#if defined(__cplusplus)
}
#endif

#undef MPVST_ALIGNAS
#undef MPVST_STATIC_ASSERT
