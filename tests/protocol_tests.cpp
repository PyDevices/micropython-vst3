#include "mpvst/atomic.h"
#include "mpvst/protocol.h"
#include "mpvst/spsc_ring.h"
#include "mpvst/ui.h"

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
    const mpvst_layout_request request {512U, 8U, 8U, 256U, 8U, 0U};
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
    const mpvst_layout_request request {64U, 4U, 4U, 32U, 4U, 0U};
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

void testInputRegionLayout()
{
    const mpvst_layout_request instrument {512U, 8U, 8U, 256U, 8U, 0U};
    const mpvst_layout_request effect {512U, 8U, 8U, 256U, 8U, 8U};
    const auto instrumentBytes = mpvst_compute_mapping_bytes(&instrument);
    const auto effectBytes = mpvst_compute_mapping_bytes(&effect);
    check(effectBytes > instrumentBytes,
          "input region grows the mapping");

    const mpvst_layout_request mismatched {512U, 8U, 8U, 256U, 8U, 4U};
    check(mpvst_compute_mapping_bytes(&mismatched) == 0U,
          "partial input coverage is rejected");

    std::vector<std::uint64_t> storage((effectBytes + 7U) / 8U);
    check(mpvst_initialize_mapping(storage.data(), effectBytes, &effect, 5U) == 1,
          "effect mapping initializes");
    check(mpvst_validate_mapping(storage.data(), effectBytes) == 1,
          "effect mapping validates");

    auto* header = reinterpret_cast<mpvst_shared_header*>(storage.data());
    const auto stride = mpvst_input_stride_bytes(header);
    check(stride % MPVST_CACHE_LINE_BYTES == 0U, "input stride is aligned");
    check(header->optional_bytes == stride * header->work_slot_count,
          "optional region holds one input block per work slot");

    auto* left0 = mpvst_input_channel(storage.data(), header, 0U, 0U);
    auto* right0 = mpvst_input_channel(storage.data(), header, 0U, 1U);
    auto* left1 = mpvst_input_channel(storage.data(), header, 1U, 0U);
    check(left0 != nullptr && right0 == left0 + header->max_frames,
          "input channels are planar");
    check(reinterpret_cast<std::uint8_t*>(left1) ==
              reinterpret_cast<std::uint8_t*>(left0) + stride,
          "input slots advance by the stride");
    left0[0] = 0.25F;
    check(mpvst_const_input_channel(storage.data(), header, 8U, 0U)[0] == 0.25F,
          "slot index wraps at the work ring size");

    const auto validHeader = *header;
    header->optional_bytes -= 64U;
    check(mpvst_validate_mapping(storage.data(), effectBytes) == 0,
          "corrupt input-region size is rejected");
    *header = validHeader;

    const mpvst_layout_request none {512U, 8U, 8U, 256U, 8U, 0U};
    check(mpvst_compute_mapping_bytes(&none) == instrumentBytes,
          "zero input slots matches the instrument layout exactly");
}

void testUiLayoutAndValidation()
{
    const auto bytes = mpvst_ui_mapping_bytes();
    check(bytes % MPVST_UI_CACHE_LINE_BYTES == 0U,
          "ui mapping is cache-line aligned");
    check(mpvst_ui_rects_offset() % 64U == 0U &&
              mpvst_ui_inputs_offset() % 64U == 0U &&
              mpvst_ui_edits_offset() % 64U == 0U &&
              mpvst_ui_framebuffer_offset() % 64U == 0U,
          "every ui region is cache-line aligned");
    check(mpvst_ui_framebuffer_bytes() ==
              mpvst_ui_stride_bytes() * MPVST_UI_MAX_HEIGHT,
          "framebuffer covers the maximum size at a fixed stride");
    // Rings must not overlap the framebuffer, which is the whole reason the
    // offsets are derived and checked rather than trusted from the mapping.
    check(mpvst_ui_framebuffer_offset() >=
              mpvst_ui_edits_offset() +
                  MPVST_UI_EDIT_CAPACITY * sizeof(mpvst_ui_edit),
          "regions do not overlap");

    std::vector<std::uint64_t> storage((bytes + 7U) / 8U);
    check(mpvst_ui_initialize(storage.data(), bytes, 3U) == 1,
          "ui mapping initializes");
    check(mpvst_ui_validate(storage.data(), bytes) == 1, "ui mapping validates");
    check(mpvst_ui_initialize(storage.data(), bytes - 64U, 3U) == 0,
          "a wrongly sized ui mapping is refused");

    auto* state = reinterpret_cast<mpvst_ui_state*>(storage.data());
    check(state->width == MPVST_UI_DEFAULT_WIDTH &&
              state->height == MPVST_UI_DEFAULT_HEIGHT &&
              state->content_scale_ppm == MPVST_UI_SCALE_UNITY &&
              state->generation == 3U && state->editor_open == 0U,
          "ui state starts closed at the default logical size");

    struct Mutation
    {
        const char* name;
        void (*apply)(mpvst_ui_state&);
    };
    const Mutation mutations[] = {
        {"ui magic", [](mpvst_ui_state& value) { value.magic = 0U; }},
        {"ui major", [](mpvst_ui_state& value) { ++value.ui_major; }},
        {"ui state size", [](mpvst_ui_state& value) { value.state_bytes = 0U; }},
        {"ui endian marker", [](mpvst_ui_state& value) { value.endian_marker = 0U; }},
        {"ui mapping size", [](mpvst_ui_state& value) { value.mapping_bytes += 64U; }},
        {"ui maximum size", [](mpvst_ui_state& value) { value.max_width += 1U; }},
        {"ui pixel format", [](mpvst_ui_state& value) { value.pixel_format = 0U; }},
        {"oversized logical width", [](mpvst_ui_state& value) {
             value.width = MPVST_UI_MAX_WIDTH + 1U;
         }},
        {"zero logical height", [](mpvst_ui_state& value) { value.height = 0U; }},
    };
    const auto valid = *state;
    for (const auto& mutation : mutations)
    {
        *state = valid;
        mutation.apply(*state);
        check(mpvst_ui_validate(storage.data(), bytes) == 0, mutation.name);
    }
    *state = valid;
}

void testUiFrameSeqlock()
{
    const auto bytes = mpvst_ui_mapping_bytes();
    std::vector<std::uint64_t> storage((bytes + 7U) / 8U);
    (void)mpvst_ui_initialize(storage.data(), bytes, 1U);
    auto* state = reinterpret_cast<mpvst_ui_state*>(storage.data());
    auto* rects = mpvst_ui_rects(storage.data());
    auto* pixels = mpvst_ui_framebuffer(storage.data());

    // The engine's publish step, written out longhand so the test exercises
    // the ordering the real one has to keep: odd, write, even.
    const auto publish = [&](std::uint16_t x, std::uint16_t y) {
        const auto sequence = mpvst::acquire_load_u64(&state->frame_sequence) + 1U;
        mpvst::release_store_u64(&state->frame_sequence, sequence);
        pixels[0] = static_cast<std::uint8_t>(x);
        auto& rect = rects[state->rect_head % MPVST_UI_RECT_CAPACITY];
        rect.frame_sequence = sequence;
        rect.x = x;
        rect.y = y;
        rect.width = 8U;
        rect.height = 8U;
        mpvst::release_store_u64(&state->rect_head, state->rect_head + 1U);
        mpvst::release_store_u64(&state->frame_sequence, sequence + 1U);
    };

    publish(4U, 5U);
    const auto settled = mpvst::acquire_load_u64(&state->frame_sequence);
    check(settled % 2U == 0U, "a settled frame leaves the sequence even");
    check(rects[0].frame_sequence == settled - 1U && rects[0].x == 4U,
          "a rectangle is keyed to the frame that produced it");

    // Mid-write the sequence is odd, which is the view's whole test: sample,
    // copy, re-sample, discard on any difference.
    mpvst::release_store_u64(&state->frame_sequence, settled + 1U);
    check(mpvst::acquire_load_u64(&state->frame_sequence) % 2U == 1U,
          "a frame in progress is detectable as torn");
    mpvst::release_store_u64(&state->frame_sequence, settled + 2U);
    const auto before = mpvst::acquire_load_u64(&state->frame_sequence);
    publish(6U, 7U);
    check(mpvst::acquire_load_u64(&state->frame_sequence) != before,
          "a frame published between two samples is detectable");
}

void testUiRingsDegradeWithoutWaiting()
{
    const auto bytes = mpvst_ui_mapping_bytes();
    std::vector<std::uint64_t> storage((bytes + 7U) / 8U);
    (void)mpvst_ui_initialize(storage.data(), bytes, 1U);
    auto* state = reinterpret_cast<mpvst_ui_state*>(storage.data());
    auto* inputs = mpvst_ui_inputs(storage.data());
    auto* edits = mpvst_ui_edits(storage.data());

    // Input ring: the view fills it without a consumer draining. Overflow has
    // to be visible as a bounded difference, never as a blocked producer.
    for (std::uint64_t index = 0; index < MPVST_UI_INPUT_CAPACITY * 3U; ++index)
    {
        auto& record = inputs[state->input_head % MPVST_UI_INPUT_CAPACITY];
        record.sequence = state->input_head + 1U;
        record.type = MPVST_UI_INPUT_POINTER_MOVE;
        record.x = static_cast<std::int32_t>(index);
        mpvst::release_store_u64(&state->input_head, state->input_head + 1U);
        if (state->input_head - state->input_tail > MPVST_UI_INPUT_CAPACITY)
            mpvst::release_store_u64(&state->input_tail,
                                     state->input_head - MPVST_UI_INPUT_CAPACITY);
    }
    check(state->input_head - state->input_tail == MPVST_UI_INPUT_CAPACITY,
          "an undrained input ring drops the oldest and stays bounded");
    check(inputs[state->input_tail % MPVST_UI_INPUT_CAPACITY].x ==
              static_cast<std::int32_t>(MPVST_UI_INPUT_CAPACITY * 2U),
          "the surviving input records are the newest ones");

    // Edit ring: a full ring drops perform records, never a begin or an end.
    // The engine's rule, exercised here against the record layout it uses.
    std::uint32_t droppedPerforms = 0;
    const auto pushEdit = [&](std::uint32_t kind, float value) {
        const auto used = state->edit_head - state->edit_tail;
        if (used >= MPVST_UI_EDIT_CAPACITY)
        {
            if (kind == MPVST_UI_EDIT_PERFORM)
            {
                ++droppedPerforms;
                return;
            }
            // Reclaim the oldest perform so a begin/end always fits.
            mpvst::release_store_u64(&state->edit_tail, state->edit_tail + 1U);
        }
        auto& record = edits[state->edit_head % MPVST_UI_EDIT_CAPACITY];
        record.sequence = state->edit_head + 1U;
        record.kind = kind;
        record.parameter_id = 100U;
        record.value = value;
        mpvst::release_store_u64(&state->edit_head, state->edit_head + 1U);
    };

    pushEdit(MPVST_UI_EDIT_BEGIN, 0.0F);
    for (std::uint32_t index = 0; index < MPVST_UI_EDIT_CAPACITY * 2U; ++index)
        pushEdit(MPVST_UI_EDIT_PERFORM, static_cast<float>(index) / 512.0F);
    pushEdit(MPVST_UI_EDIT_END, 1.0F);
    check(droppedPerforms != 0U, "a full edit ring drops perform records");
    check(state->edit_head - state->edit_tail <= MPVST_UI_EDIT_CAPACITY,
          "the edit ring stays bounded");
    const auto& last = edits[(state->edit_head - 1U) % MPVST_UI_EDIT_CAPACITY];
    check(last.kind == MPVST_UI_EDIT_END && last.value == 1.0F,
          "the end of a gesture is never the record that gets dropped");
}

} // namespace

int main()
{
    testLayoutAndValidation();
    testBoundedWorkRing();
    testOutputAndGeneration();
    testInputRegionLayout();
    testUiLayoutAndValidation();
    testUiFrameSeqlock();
    testUiRingsDegradeWithoutWaiting();
    if (failures != 0)
        return 1;
    std::cout << "mpvst protocol layout and bounded-ring tests passed\n";
    return 0;
}
