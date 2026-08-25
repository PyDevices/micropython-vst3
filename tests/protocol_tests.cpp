#include "mpvst/atomic.h"
#include "mpvst/protocol.h"
#include "mpvst/spsc_ring.h"

#include <cmath>
#include <cstdint>
#include <iostream>
#include <vector>

namespace {

int failures = 0;

void check(bool condition, const char* message)
{
    if (!condition)
    {
        std::cerr << "FAIL: " << message << '\n';
        ++failures;
    }
}

mpvst_output_slot* outputAt(void* mapping, const mpvst_shared_header& header,
                            std::uint64_t position)
{
    auto* bytes = static_cast<std::uint8_t*>(mpvst_region(mapping, header.outputs_offset));
    return reinterpret_cast<mpvst_output_slot*>(
        bytes + (position % header.output_slot_count) * mpvst_output_stride_bytes(&header));
}

void testLayoutAndValidation()
{
    const mpvst_layout_request request {512U, 8U, 8U, 256U, 8U};
    const auto bytes = mpvst_compute_mapping_bytes(&request);
    check(bytes > 0U && bytes % MPVST_CACHE_LINE_BYTES == 0U,
          "mapping is non-empty and cache-line aligned");
    std::vector<std::uint64_t> storage((bytes + 7U) / 8U);
    check(mpvst_initialize_mapping(storage.data(), bytes, &request,
                                   UINT64_C(0x0123456789abcdef)) == 1,
          "mapping initializes");
    check(mpvst_validate_mapping(storage.data(), bytes) == 1, "mapping validates");

    auto* header = reinterpret_cast<mpvst_shared_header*>(storage.data());
    check(header->status_offset % 64U == 0U && header->outputs_offset % 64U == 0U,
          "regions are cache-line aligned");
    const auto savedMagic = header->magic;
    header->magic = 0U;
    check(mpvst_validate_mapping(storage.data(), bytes) == 0,
          "bad protocol magic is rejected");
    header->magic = savedMagic;

    struct Mutation
    {
        const char* name;
        void (*apply)(mpvst_shared_header&);
    };
    const Mutation mutations[] = {
        {"protocol major", [](mpvst_shared_header& value) {
             ++value.protocol_major;
         }},
        {"header size", [](mpvst_shared_header& value) {
             value.header_bytes = 0U;
         }},
        {"endian marker", [](mpvst_shared_header& value) {
             value.endian_marker = 0U;
         }},
        {"mapping size", [](mpvst_shared_header& value) {
             value.mapping_bytes += 64U;
         }},
        {"channel count", [](mpvst_shared_header& value) {
             value.channel_count = 1U;
         }},
        {"status offset", [](mpvst_shared_header& value) {
             value.status_offset += 64U;
         }},
        {"event offset", [](mpvst_shared_header& value) {
             value.events_offset += 64U;
         }},
        {"work offset", [](mpvst_shared_header& value) {
             value.work_offset += 64U;
         }},
        {"output offset", [](mpvst_shared_header& value) {
             value.outputs_offset += 64U;
         }},
    };
    const auto validHeader = *header;
    for (const auto& mutation : mutations)
    {
        *header = validHeader;
        mutation.apply(*header);
        check(mpvst_validate_mapping(storage.data(), bytes) == 0, mutation.name);
    }
    *header = validHeader;
}

void testBoundedWorkRing()
{
    mpvst_work_slot slots[4] {};
    for (std::uint64_t index = 0; index < 4U; ++index)
        slots[index].sequence = index;

    for (std::uint64_t position = 0; position < 4U; ++position)
    {
        auto* slot = mpvst::try_acquire_producer(slots, 4U, position);
        check(slot != nullptr, "producer owns each initially free slot");
        slot->start_sample = static_cast<std::int64_t>(position * 64U);
        mpvst::publish_producer(slot, position);
    }
    check(mpvst::try_acquire_producer(slots, 4U, 4U) == nullptr,
          "full producer ring returns immediately");

    for (std::uint64_t position = 0; position < 12U; ++position)
    {
        const auto producerPosition = position + 4U;
        auto* consumed = mpvst::try_acquire_consumer(slots, 4U, position);
        check(consumed != nullptr, "consumer sees only published slot");
        mpvst::release_consumer(consumed, 4U, position);

        auto* produced = mpvst::try_acquire_producer(slots, 4U, producerPosition);
        check(produced != nullptr, "released slot wraps to producer");
        produced->start_sample = static_cast<std::int64_t>(producerPosition * 64U);
        mpvst::publish_producer(produced, producerPosition);
    }
}

void testOutputAndGeneration()
{
    const mpvst_layout_request request {64U, 4U, 4U, 32U, 4U};
    const auto bytes = mpvst_compute_mapping_bytes(&request);
    std::vector<std::uint64_t> storage((bytes + 7U) / 8U);
    check(mpvst_initialize_mapping(storage.data(), bytes, &request, 9U) == 1,
          "output test mapping initializes");
    auto& header = *reinterpret_cast<mpvst_shared_header*>(storage.data());

    auto* produced = outputAt(storage.data(), header, 0U);
    check(mpvst::acquire_load_u64(&produced->sequence) == 0U,
          "output slot starts producer-owned");
    produced->generation = 1U;
    produced->frame_count = 64U;
    produced->start_sample = 256;
    for (std::uint32_t frame = 0; frame < 64U; ++frame)
    {
        mpvst_output_channel(produced, 64U, 0U)[frame] =
            std::sin(static_cast<float>(frame) * 0.1F);
        mpvst_output_channel(produced, 64U, 1U)[frame] =
            mpvst_output_channel(produced, 64U, 0U)[frame];
    }
    mpvst::publish_producer(produced, 0U);

    auto* consumed = outputAt(storage.data(), header, 0U);
    check(mpvst::acquire_load_u64(&consumed->sequence) == 1U,
          "published output becomes consumer-owned");
    check(consumed->generation == mpvst::acquire_load_u32(&header.generation),
          "current generation is accepted");
    check(mpvst_const_output_channel(consumed, 64U, 0U)[17] ==
              mpvst_const_output_channel(consumed, 64U, 1U)[17],
          "planar channels address independent sample regions");

    mpvst::release_store_u32(&header.generation, 2U);
    check(consumed->generation != mpvst::acquire_load_u32(&header.generation),
          "stale generation is detectable before playback");
}

} // namespace

int main()
{
    testLayoutAndValidation();
    testBoundedWorkRing();
    testOutputAndGeneration();
    if (failures != 0)
        return 1;
    std::cout << "mpvst protocol layout and bounded-ring tests passed\n";
    return 0;
}
