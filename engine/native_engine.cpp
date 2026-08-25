#include "mpvst/atomic.h"
#include "mpvst/protocol.h"
#include "mpvst/shared_memory.h"
#include "mpvst/spsc_ring.h"

#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <thread>

namespace {

std::uint64_t exitAfterBlocks()
{
    const auto* value = std::getenv("MPVST_NATIVE_EXIT_AFTER_BLOCKS");
    return value == nullptr ? 0U : std::strtoull(value, nullptr, 10);
}

std::uint64_t stallAfterBlocks()
{
    const auto* value = std::getenv("MPVST_NATIVE_STALL_AFTER_BLOCKS");
    return value == nullptr ? 0U : std::strtoull(value, nullptr, 10);
}

mpvst_output_slot* outputAt(void* mapping, const mpvst_shared_header& header,
                            std::uint64_t position)
{
    auto* bytes = static_cast<std::uint8_t*>(mpvst_region(mapping, header.outputs_offset));
    return reinterpret_cast<mpvst_output_slot*>(
        bytes + (position % header.output_slot_count) * mpvst_output_stride_bytes(&header));
}

} // namespace

int main(int argc, char** argv)
{
    if (argc != 3)
        return 2;
    const auto bytes = std::strtoull(argv[2], nullptr, 10);
    mpvst::SharedMemory mapping;
    if (!mapping.open(argv[1], bytes) || !mpvst_validate_mapping(mapping.data(), bytes))
        return 3;

    auto& header = *static_cast<mpvst_shared_header*>(mapping.data());
    auto* status = static_cast<mpvst_status*>(mpvst_region(mapping.data(), header.status_offset));
    auto* events = static_cast<mpvst_event*>(mpvst_region(mapping.data(), header.events_offset));
    auto* work = static_cast<mpvst_work_slot*>(mpvst_region(mapping.data(), header.work_offset));
    std::uint64_t workPosition = 0U;
    std::uint64_t outputPosition = 0U;
    const auto forcedExitBlock = exitAfterBlocks();
    const auto forcedStallBlock = stallAfterBlocks();
    const bool eventGate = std::getenv("MPVST_NATIVE_EVENT_GATE") != nullptr;
    bool gateOpen = false;
    float gateLevel = 0.125F;
    mpvst::release_store_u32(&header.lifecycle, MPVST_LIFECYCLE_ENGINE_READY);

    while (true)
    {
        const auto lifecycle = mpvst::acquire_load_u32(&header.lifecycle);
        if (lifecycle == MPVST_LIFECYCLE_STOPPING)
            break;
        if (lifecycle != MPVST_LIFECYCLE_RUNNING)
        {
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
            continue;
        }

        auto* request = mpvst::try_acquire_consumer(work, header.work_slot_count,
                                                    workPosition);
        auto* output = outputAt(mapping.data(), header, outputPosition);
        if (request == nullptr ||
            mpvst::acquire_load_u64(&output->sequence) != outputPosition)
        {
            std::this_thread::yield();
            continue;
        }

        output->generation = request->generation;
        output->frame_count = request->frame_count;
        output->start_sample = request->start_sample;
        output->channel_count = header.channel_count;
        const auto renderStarted = std::chrono::steady_clock::now();
        output->flags = eventGate ||
                                (request->flags & MPVST_WORK_FLAG_TEST_TONE) != 0U
                            ? 0U
                            : MPVST_OUTPUT_FLAG_SILENT;
        const auto sampleRate = static_cast<double>(request->sample_rate_millihz) / 1000.0;
        constexpr double twoPi = 6.283185307179586476925286766559;
        for (std::uint32_t frame = 0; frame < request->frame_count; ++frame)
        {
            const auto samplePosition = request->start_sample + frame;
            for (std::uint32_t eventIndex = 0U;
                 eventIndex < request->event_count; ++eventIndex)
            {
                const auto& event = events[
                    (request->event_first + eventIndex) % header.event_capacity];
                if (event.sample_position == samplePosition)
                {
                    if (event.type == MPVST_EVENT_NOTE_ON)
                        gateOpen = true;
                    else if (event.type == MPVST_EVENT_NOTE_OFF)
                        gateOpen = false;
                    else if (event.type == MPVST_EVENT_PITCH_BEND &&
                             event.channel == 3U && event.data0 == 129)
                        gateLevel = 0.125F + 0.125F * event.value0;
                    else if (event.type == MPVST_EVENT_PARAMETER &&
                             event.data0 == 0)
                        gateLevel = 0.25F * event.value0;
                }
            }
            const auto sample = eventGate
                                    ? (gateOpen ? gateLevel : 0.0F)
                                : (request->flags & MPVST_WORK_FLAG_TEST_TONE) != 0U
                                    ? static_cast<float>(0.125 * std::sin(
                                          twoPi * 440.0 *
                                          static_cast<double>(samplePosition) / sampleRate))
                                    : 0.0F;
            mpvst_output_channel(output, header.max_frames, 0U)[frame] = sample;
            mpvst_output_channel(output, header.max_frames, 1U)[frame] = sample;
        }
        (void)mpvst::relaxed_fetch_add_u64(
            &status->events_consumed, request->event_count);
        mpvst::release_consumer(request, header.work_slot_count, workPosition);
        output->render_time_ns = static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::nanoseconds>(
                std::chrono::steady_clock::now() - renderStarted)
                .count());
        mpvst::publish_producer(output, outputPosition);
        ++workPosition;
        ++outputPosition;
        (void)mpvst::relaxed_fetch_add_u64(&status->engine_heartbeat, 1U);
        (void)mpvst::relaxed_fetch_add_u64(&status->blocks_rendered, 1U);
        if (forcedExitBlock != 0U &&
            mpvst::acquire_load_u64(&status->restart_count) == 0U &&
            outputPosition >= forcedExitBlock)
            return 17;
        if (forcedStallBlock != 0U &&
            mpvst::acquire_load_u64(&status->restart_count) == 0U &&
            outputPosition >= forcedStallBlock)
        {
            for (;;)
                std::this_thread::sleep_for(std::chrono::seconds(1));
        }
    }

    mpvst::release_store_u32(&header.lifecycle, MPVST_LIFECYCLE_STOPPED);
    return 0;
}
