// Fuzz targets for the two byte streams the plug-in accepts from outside its
// own process: the shared-memory mapping an engine hands back, and the project
// state a host restores.
//
// Both are written as libFuzzer entry points so a clang build can drive them
// with coverage feedback, and both are also exercised by the portable driver in
// fuzz_driver.cpp so the same code runs under the ordinary GCC/MSVC test suite.
//
// The contract under test is simply that no input, however malformed, may
// crash, read out of bounds, or hang. Rejection is always an acceptable answer.

#include "mpvst/protocol.h"

#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <vector>

// Abort hard on a violated invariant. Fuzzers detect the crash; this has to be
// something no toolchain can optimise away, so it is not an assert.
#if defined(_MSC_VER)
#define MPVST_FUZZ_FAIL() (__debugbreak(), std::abort())
#else
#define MPVST_FUZZ_FAIL() __builtin_trap()
#endif

namespace {

// Mirrors the state layout the processor writes: version, bypass, sixteen
// macro floats, then for version 2 a pipeline depth and an embedded script.
constexpr std::int32_t kLegacyStateVersion = 1;
constexpr std::int32_t kStateVersion = 2;
constexpr std::size_t kMacroCount = 16U;
constexpr std::int32_t kMaximumPipelineBlocks = 64;
constexpr std::int32_t kMaximumEmbeddedScriptBytes = 1024 * 1024;

class Reader
{
public:
    Reader(const std::uint8_t* data, std::size_t size)
        : data_(data), size_(size)
    {
    }

    bool readInt32(std::int32_t& value)
    {
        if (size_ - offset_ < sizeof(std::int32_t))
            return false;
        std::memcpy(&value, data_ + offset_, sizeof(value));
        offset_ += sizeof(value);
        return true;
    }

    bool readFloat(float& value)
    {
        if (size_ - offset_ < sizeof(float))
            return false;
        std::memcpy(&value, data_ + offset_, sizeof(value));
        offset_ += sizeof(value);
        return true;
    }

    bool readRaw(void* destination, std::size_t bytes)
    {
        if (size_ - offset_ < bytes)
            return false;
        std::memcpy(destination, data_ + offset_, bytes);
        offset_ += bytes;
        return true;
    }

private:
    const std::uint8_t* data_ = nullptr;
    std::size_t size_ = 0U;
    std::size_t offset_ = 0U;
};

// A faithful copy of the processor's state-acceptance rules. Keeping the
// decision here rather than instantiating the plug-in lets the fuzzer explore
// the parser at full speed; the smoke host covers the same rules end to end
// against the real component.
bool acceptsState(const std::uint8_t* data, std::size_t size)
{
    Reader reader(data, size);
    std::int32_t version = 0;
    std::int32_t bypass = 0;
    if (!reader.readInt32(version) ||
        (version != kLegacyStateVersion && version != kStateVersion) ||
        !reader.readInt32(bypass))
        return false;

    for (std::size_t index = 0; index < kMacroCount; ++index)
    {
        float macro = 0.0F;
        if (!reader.readFloat(macro))
            return false;
    }

    if (version < kStateVersion)
        return true;

    std::int32_t pipelineBlocks = 0;
    std::int32_t scriptBytes = 0;
    if (!reader.readInt32(pipelineBlocks) || pipelineBlocks < 1 ||
        pipelineBlocks > kMaximumPipelineBlocks ||
        !reader.readInt32(scriptBytes) || scriptBytes < 0 ||
        scriptBytes > kMaximumEmbeddedScriptBytes)
        return false;

    std::vector<char> script(static_cast<std::size_t>(scriptBytes));
    return scriptBytes == 0 ||
           reader.readRaw(script.data(), static_cast<std::size_t>(scriptBytes));
}

} // namespace

// Treats the input as a shared mapping and asks the protocol to validate it.
// A valid mapping must also survive having every declared region resolved.
extern "C" int mpvst_fuzz_mapping(const std::uint8_t* data, std::size_t size)
{
    if (size < sizeof(mpvst_shared_header))
        return 0;

    // Copy into an over-aligned buffer so the header is read at the alignment
    // the ABI promises rather than wherever the fuzzer's allocation landed.
    std::vector<std::uint64_t> storage((size + 7U) / 8U);
    std::memcpy(storage.data(), data, size);

    if (mpvst_validate_mapping(storage.data(), size) != 1)
        return 0;

    // Validation said yes, so every region it blessed must be inside the
    // mapping and the derived strides must be self-consistent.
    const auto* header =
        reinterpret_cast<const mpvst_shared_header*>(storage.data());
    const std::uint64_t offsets[] = {
        header->status_offset, header->commands_offset,
        header->events_offset, header->work_offset,
        header->outputs_offset,
    };
    for (const auto offset : offsets)
    {
        if (offset >= size)
            MPVST_FUZZ_FAIL();
        if (mpvst_const_region(storage.data(), offset) == nullptr)
            MPVST_FUZZ_FAIL();
    }
    // The optional region either owns no bytes or is exactly one input-audio
    // block per work slot (protocol minor 1); validation enforces that, so a
    // blessed mapping must satisfy it here too.
    if (header->optional_offset > size ||
        header->optional_bytes > size - header->optional_offset)
        MPVST_FUZZ_FAIL();
    if (header->optional_bytes != 0U)
    {
        const auto inputStride = mpvst_input_stride_bytes(header);
        if (inputStride == 0U ||
            header->optional_bytes !=
                inputStride * header->work_slot_count)
            MPVST_FUZZ_FAIL();
        if (mpvst_const_input_channel(storage.data(), header,
                                      header->work_slot_count - 1U, 1U) ==
            nullptr)
            MPVST_FUZZ_FAIL();
    }
    const auto stride = mpvst_output_stride_bytes(header);
    if (stride == 0U ||
        header->outputs_offset + stride * header->output_slot_count > size)
        MPVST_FUZZ_FAIL();
    return 0;
}

extern "C" int mpvst_fuzz_state(const std::uint8_t* data, std::size_t size)
{
    (void)acceptsState(data, size);
    return 0;
}

#if defined(MPVST_LIBFUZZER_MAPPING)
extern "C" int LLVMFuzzerTestOneInput(const std::uint8_t* data, std::size_t size)
{
    return mpvst_fuzz_mapping(data, size);
}
#elif defined(MPVST_LIBFUZZER_STATE)
extern "C" int LLVMFuzzerTestOneInput(const std::uint8_t* data, std::size_t size)
{
    return mpvst_fuzz_state(data, size);
}
#endif
