#include "mpvst/protocol.h"

#include <cstdint>
#include <cstring>
#include <limits>

namespace {

constexpr std::uint64_t alignUp(std::uint64_t value, std::uint64_t alignment) noexcept
{
    return (value + alignment - 1U) & ~(alignment - 1U);
}

bool checkedAdd(std::uint64_t& value, std::uint64_t amount) noexcept
{
    if (amount > std::numeric_limits<std::uint64_t>::max() - value)
        return false;
    value += amount;
    return true;
}

bool validRequest(const mpvst_layout_request* request) noexcept
{
    return request != nullptr && request->max_frames > 0U &&
           request->work_slot_count >= 2U && request->output_slot_count >= 2U &&
           request->event_capacity > 0U && request->command_capacity >= 2U;
}

bool computeOffsets(const mpvst_layout_request* request, mpvst_shared_header& header) noexcept
{
    if (!validRequest(request))
        return false;

    std::uint64_t cursor = sizeof(mpvst_shared_header);
    cursor = alignUp(cursor, MPVST_CACHE_LINE_BYTES);
    header.status_offset = cursor;
    if (!checkedAdd(cursor, sizeof(mpvst_status)))
        return false;

    cursor = alignUp(cursor, MPVST_CACHE_LINE_BYTES);
    header.commands_offset = cursor;
    if (!checkedAdd(cursor, static_cast<std::uint64_t>(request->command_capacity) *
                               sizeof(mpvst_command)))
        return false;

    cursor = alignUp(cursor, MPVST_CACHE_LINE_BYTES);
    header.events_offset = cursor;
    if (!checkedAdd(cursor, static_cast<std::uint64_t>(request->event_capacity) *
                               sizeof(mpvst_event)))
        return false;

    cursor = alignUp(cursor, MPVST_CACHE_LINE_BYTES);
    header.work_offset = cursor;
    if (!checkedAdd(cursor, static_cast<std::uint64_t>(request->work_slot_count) *
                               sizeof(mpvst_work_slot)))
        return false;

    cursor = alignUp(cursor, MPVST_CACHE_LINE_BYTES);
    header.outputs_offset = cursor;
    const auto sampleBytes = static_cast<std::uint64_t>(request->max_frames) *
                             MPVST_CHANNEL_COUNT * sizeof(float);
    const auto outputStride = alignUp(sizeof(mpvst_output_slot) + sampleBytes,
                                      MPVST_CACHE_LINE_BYTES);
    if (!checkedAdd(cursor, static_cast<std::uint64_t>(request->output_slot_count) *
                               outputStride))
        return false;

    header.optional_offset = alignUp(cursor, MPVST_CACHE_LINE_BYTES);
    header.optional_bytes = 0U;
    header.mapping_bytes = header.optional_offset;
    return true;
}

} // namespace

extern "C" uint64_t mpvst_compute_mapping_bytes(const mpvst_layout_request* request)
{
    mpvst_shared_header header {};
    return computeOffsets(request, header) ? header.mapping_bytes : 0U;
}

extern "C" int mpvst_initialize_mapping(void* mapping, uint64_t mapping_bytes,
                                         const mpvst_layout_request* request,
                                         uint64_t instance_nonce)
{
    if (mapping == nullptr)
        return 0;

    mpvst_shared_header expected {};
    if (!computeOffsets(request, expected) || expected.mapping_bytes != mapping_bytes)
        return 0;

    std::memset(mapping, 0, static_cast<std::size_t>(mapping_bytes));
    auto* header = static_cast<mpvst_shared_header*>(mapping);
    *header = expected;
    header->magic = MPVST_PROTOCOL_MAGIC;
    header->protocol_major = MPVST_PROTOCOL_MAJOR;
    header->protocol_minor = MPVST_PROTOCOL_MINOR;
    header->header_bytes = sizeof(mpvst_shared_header);
    header->endian_marker = MPVST_ENDIAN_MARKER;
    header->max_frames = request->max_frames;
    header->channel_count = MPVST_CHANNEL_COUNT;
    header->work_slot_count = request->work_slot_count;
    header->output_slot_count = request->output_slot_count;
    header->event_capacity = request->event_capacity;
    header->command_capacity = request->command_capacity;
    header->instance_nonce = instance_nonce;
    header->generation = 1U;
    header->lifecycle = MPVST_LIFECYCLE_HOST_READY;

    auto* commands = static_cast<mpvst_command*>(mpvst_region(mapping, header->commands_offset));
    for (std::uint32_t index = 0; index < header->command_capacity; ++index)
        commands[index].sequence = index;

    auto* work = static_cast<mpvst_work_slot*>(mpvst_region(mapping, header->work_offset));
    for (std::uint32_t index = 0; index < header->work_slot_count; ++index)
        work[index].sequence = index;

    auto* outputBytes = static_cast<std::uint8_t*>(mpvst_region(mapping, header->outputs_offset));
    const auto stride = mpvst_output_stride_bytes(header);
    for (std::uint32_t index = 0; index < header->output_slot_count; ++index)
    {
        auto* slot = reinterpret_cast<mpvst_output_slot*>(outputBytes + index * stride);
        slot->sequence = index;
        slot->channel_count = MPVST_CHANNEL_COUNT;
    }
    return 1;
}

extern "C" int mpvst_validate_mapping(const void* mapping, uint64_t mapping_bytes)
{
    if (mapping == nullptr || mapping_bytes < sizeof(mpvst_shared_header))
        return 0;
    const auto* header = static_cast<const mpvst_shared_header*>(mapping);
    if (header->magic != MPVST_PROTOCOL_MAGIC ||
        header->protocol_major != MPVST_PROTOCOL_MAJOR ||
        header->header_bytes != sizeof(mpvst_shared_header) ||
        header->endian_marker != MPVST_ENDIAN_MARKER ||
        header->mapping_bytes != mapping_bytes ||
        header->channel_count != MPVST_CHANNEL_COUNT)
        return 0;

    const mpvst_layout_request request {header->max_frames, header->work_slot_count,
                                        header->output_slot_count, header->event_capacity,
                                        header->command_capacity};
    mpvst_shared_header expected {};
    return computeOffsets(&request, expected) &&
           expected.mapping_bytes == mapping_bytes &&
           expected.status_offset == header->status_offset &&
           expected.commands_offset == header->commands_offset &&
           expected.events_offset == header->events_offset &&
           expected.work_offset == header->work_offset &&
           expected.outputs_offset == header->outputs_offset;
}

extern "C" void* mpvst_region(void* mapping, uint64_t offset)
{
    return static_cast<std::uint8_t*>(mapping) + offset;
}

extern "C" const void* mpvst_const_region(const void* mapping, uint64_t offset)
{
    return static_cast<const std::uint8_t*>(mapping) + offset;
}

extern "C" uint64_t mpvst_output_stride_bytes(const mpvst_shared_header* header)
{
    if (header == nullptr)
        return 0U;
    const auto bytes = sizeof(mpvst_output_slot) +
                       static_cast<std::uint64_t>(header->max_frames) *
                           header->channel_count * sizeof(float);
    return alignUp(bytes, MPVST_CACHE_LINE_BYTES);
}

extern "C" float* mpvst_output_channel(mpvst_output_slot* slot, uint32_t max_frames,
                                        uint32_t channel)
{
    auto* samples = reinterpret_cast<float*>(reinterpret_cast<std::uint8_t*>(slot) +
                                             sizeof(mpvst_output_slot));
    return samples + static_cast<std::uint64_t>(max_frames) * channel;
}

extern "C" const float* mpvst_const_output_channel(const mpvst_output_slot* slot,
                                                    uint32_t max_frames,
                                                    uint32_t channel)
{
    const auto* samples = reinterpret_cast<const float*>(
        reinterpret_cast<const std::uint8_t*>(slot) + sizeof(mpvst_output_slot));
    return samples + static_cast<std::uint64_t>(max_frames) * channel;
}
