// Portable driver for the fuzz targets.
//
// Coverage-guided fuzzing needs clang, which is not required to build this
// project. This driver runs the same entry points over a deterministic corpus
// so the targets are exercised by the ordinary test suite on every toolchain,
// and so a crash found by libFuzzer elsewhere can be replayed here by dropping
// its input into the corpus directory.
//
// Inputs come from three places: seeds derived from a valid mapping and a valid
// state blob, mutations of those seeds, and any files in a corpus directory
// passed on the command line.

#include "mpvst/protocol.h"

#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <random>
#include <string>
#include <vector>

extern "C" int mpvst_fuzz_mapping(const std::uint8_t* data, std::size_t size);
extern "C" int mpvst_fuzz_state(const std::uint8_t* data, std::size_t size);

namespace {

std::vector<std::uint8_t> validMapping()
{
    const mpvst_layout_request request {128U, 8U, 8U, 256U, 8U, 0U};
    const auto bytes = mpvst_compute_mapping_bytes(&request);
    std::vector<std::uint64_t> storage((bytes + 7U) / 8U);
    if (mpvst_initialize_mapping(storage.data(), bytes, &request,
                                 UINT64_C(0x0123456789abcdef)) != 1)
        return {};
    std::vector<std::uint8_t> result(static_cast<std::size_t>(bytes));
    std::memcpy(result.data(), storage.data(), result.size());
    return result;
}

void append(std::vector<std::uint8_t>& target, const void* data, std::size_t size)
{
    const auto* bytes = static_cast<const std::uint8_t*>(data);
    target.insert(target.end(), bytes, bytes + size);
}

std::vector<std::uint8_t> validState()
{
    std::vector<std::uint8_t> state;
    const std::int32_t version = 2;
    const std::int32_t bypass = 0;
    append(state, &version, sizeof(version));
    append(state, &bypass, sizeof(bypass));
    for (int index = 0; index < 16; ++index)
    {
        const float macro = 0.5F;
        append(state, &macro, sizeof(macro));
    }
    const std::int32_t pipelineBlocks = 4;
    const char script[] = "import vstaudio\n";
    const std::int32_t scriptBytes = static_cast<std::int32_t>(sizeof(script) - 1);
    append(state, &pipelineBlocks, sizeof(pipelineBlocks));
    append(state, &scriptBytes, sizeof(scriptBytes));
    append(state, script, static_cast<std::size_t>(scriptBytes));
    return state;
}

// Bit flips, byte splices, truncations, and growth: enough structural damage to
// reach the parsers' rejection paths without a coverage signal to steer by.
void mutate(std::vector<std::uint8_t>& buffer, std::mt19937_64& random)
{
    if (buffer.empty())
        return;
    const auto choice = random() % 5U;
    if (choice == 0U)
    {
        const auto index = random() % buffer.size();
        buffer[index] ^= static_cast<std::uint8_t>(1U << (random() % 8U));
    }
    else if (choice == 1U)
    {
        const auto index = random() % buffer.size();
        buffer[index] = static_cast<std::uint8_t>(random());
    }
    else if (choice == 2U && buffer.size() > 1U)
    {
        buffer.resize(1U + random() % (buffer.size() - 1U));
    }
    else if (choice == 3U)
    {
        buffer.push_back(static_cast<std::uint8_t>(random()));
    }
    else
    {
        const auto index = random() % buffer.size();
        const auto count = std::min<std::size_t>(buffer.size() - index,
                                                  1U + random() % 8U);
        for (std::size_t offset = 0; offset < count; ++offset)
            buffer[index + offset] = static_cast<std::uint8_t>(random());
    }
}

std::size_t runCorpus(const std::string& directory)
{
    std::size_t count = 0U;
    std::error_code error;
    if (directory.empty() || !std::filesystem::is_directory(directory, error))
        return 0U;
    for (const auto& entry : std::filesystem::directory_iterator(directory, error))
    {
        if (!entry.is_regular_file())
            continue;
        std::ifstream input(entry.path(), std::ios::binary);
        std::vector<std::uint8_t> bytes((std::istreambuf_iterator<char>(input)),
                                         std::istreambuf_iterator<char>());
        if (bytes.empty())
            continue;
        (void)mpvst_fuzz_mapping(bytes.data(), bytes.size());
        (void)mpvst_fuzz_state(bytes.data(), bytes.size());
        ++count;
    }
    return count;
}

} // namespace

int main(int argc, char** argv)
{
    // Fixed seed: a failure here must be reproducible from the test name alone.
    std::mt19937_64 random(UINT64_C(0x5eed5eed5eed5eed));
    const std::size_t iterations = argc > 1
        ? static_cast<std::size_t>(std::stoul(argv[1]))
        : 20000U;
    const std::string corpus = argc > 2 ? argv[2] : std::string {};

    const auto mappingSeed = validMapping();
    const auto stateSeed = validState();
    if (mappingSeed.empty())
    {
        std::cerr << "could not build a valid mapping seed\n";
        return 2;
    }

    (void)mpvst_fuzz_mapping(mappingSeed.data(), mappingSeed.size());
    (void)mpvst_fuzz_state(stateSeed.data(), stateSeed.size());

    for (std::size_t iteration = 0; iteration < iterations; ++iteration)
    {
        auto mapping = mappingSeed;
        mutate(mapping, random);
        if (iteration % 3U == 0U)
            mutate(mapping, random);
        (void)mpvst_fuzz_mapping(mapping.data(), mapping.size());

        auto state = stateSeed;
        mutate(state, random);
        if (iteration % 5U == 0U)
            mutate(state, random);
        (void)mpvst_fuzz_state(state.data(), state.size());
    }

    const auto replayed = runCorpus(corpus);
    std::cout << "fuzz driver completed " << iterations
              << " mutation rounds and " << replayed << " corpus inputs\n";
    return 0;
}
