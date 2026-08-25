#include "mpvst/atomic.h"
#include "mpvst/child_process.h"
#include "mpvst/protocol.h"
#include "mpvst/shared_memory.h"
#include "mpvst/spsc_ring.h"

#include <chrono>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <string>
#include <thread>

namespace {

mpvst_output_slot* outputAt(void* mapping, const mpvst_shared_header& header,
                            std::uint64_t position)
{
    auto* bytes = static_cast<std::uint8_t*>(mpvst_region(mapping, header.outputs_offset));
    return reinterpret_cast<mpvst_output_slot*>(
        bytes + (position % header.output_slot_count) * mpvst_output_stride_bytes(&header));
}

template <typename Predicate>
bool waitUntil(Predicate predicate, std::uint32_t timeoutMs)
{
    const auto deadline = std::chrono::steady_clock::now() +
                          std::chrono::milliseconds(timeoutMs);
    while (!predicate())
    {
        if (std::chrono::steady_clock::now() >= deadline)
            return false;
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
    return true;
}

} // namespace

int main(int argc, char** argv)
{
    if (argc != 2)
        return 2;
    const mpvst_layout_request request {128U, 8U, 8U, 256U, 8U};
    const auto bytes = mpvst_compute_mapping_bytes(&request);
    const auto name = mpvst::uniqueMappingName();
    mpvst::SharedMemory mapping;
    if (!mapping.create(name, bytes) ||
        !mpvst_initialize_mapping(mapping.data(), bytes, &request, 42U))
        return 3;

    mpvst::ChildProcess engine;
    if (!engine.start(argv[1], {name, std::to_string(bytes)}))
        return 4;
    auto& header = *static_cast<mpvst_shared_header*>(mapping.data());
    if (!waitUntil([&] {
            return mpvst::acquire_load_u32(&header.lifecycle) ==
                   MPVST_LIFECYCLE_ENGINE_READY;
        }, 3000U))
        return 5;
    mpvst::release_store_u32(&header.lifecycle, MPVST_LIFECYCLE_RUNNING);

    auto* work = static_cast<mpvst_work_slot*>(mpvst_region(mapping.data(),
                                                            header.work_offset));
    std::int64_t startSample = 0;
    for (std::uint64_t position = 0; position < 64U; ++position)
    {
        auto* requestSlot = mpvst::try_acquire_producer(work, header.work_slot_count,
                                                        position);
        if (requestSlot == nullptr)
            return 6;
        const auto frames = static_cast<std::uint32_t>(17U + position % 97U);
        requestSlot->generation = 1U;
        requestSlot->frame_count = frames;
        requestSlot->start_sample = startSample;
        requestSlot->sample_rate_millihz = UINT64_C(48000000);
        requestSlot->transport_sample = startSample;
        requestSlot->flags = MPVST_WORK_FLAG_TEST_TONE;
        mpvst::publish_producer(requestSlot, position);

        auto* output = outputAt(mapping.data(), header, position);
        if (!waitUntil([&] {
                return mpvst::acquire_load_u64(&output->sequence) == position + 1U;
            }, 3000U))
            return 7;
        if (output->generation != 1U || output->start_sample != startSample ||
            output->frame_count != frames)
            return 8;
        constexpr double twoPi = 6.283185307179586476925286766559;
        const auto expected = static_cast<float>(
            0.125 * std::sin(twoPi * 440.0 * static_cast<double>(startSample) / 48000.0));
        const auto actual = mpvst_const_output_channel(output, header.max_frames, 0U)[0];
        if (std::abs(actual - expected) > 0.000001F)
            return 9;
        mpvst::release_consumer(output, header.output_slot_count, position);
        startSample += frames;
    }

    mpvst::release_store_u32(&header.lifecycle, MPVST_LIFECYCLE_STOPPING);
    int exitCode = -1;
    if (!engine.wait(3000U, &exitCode) || exitCode != 0 ||
        mpvst::acquire_load_u32(&header.lifecycle) != MPVST_LIFECYCLE_STOPPED)
        return 10;
    std::cout << "native sidecar rendered 64 variable blocks through shared memory\n";
    return 0;
}
