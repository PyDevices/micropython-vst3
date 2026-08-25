#include "sidecar_transport.h"

#include <array>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <memory>
#include <string>
#include <thread>

namespace {

using PyDevices::MicroPythonVST3::SidecarTransport;

void setEnvironment(const char* name, const std::string& value)
{
#if defined(_WIN32)
    (void)_putenv_s(name, value.c_str());
#else
    (void)setenv(name, value.c_str(), 1);
#endif
}

void clearEnvironment(const char* name)
{
#if defined(_WIN32)
    (void)_putenv_s(name, "");
#else
    (void)unsetenv(name);
#endif
}

bool hasSignal(const std::array<float, 64>& samples)
{
    for (const auto sample : samples)
    {
        if (!std::isfinite(sample))
            return false;
        if (std::abs(sample) > 0.000001F)
            return true;
    }
    return false;
}

bool eightIndependentInstances()
{
    std::array<std::unique_ptr<SidecarTransport>, 8> instances;
    for (auto& instance : instances)
    {
        instance = std::make_unique<SidecarTransport>();
        instance->configure(48000.0, 64U, 256U);
        if (!instance->start())
            return false;
    }

    std::array<bool, 8> heard {};
    for (std::uint32_t block = 0; block < 24U; ++block)
    {
        for (std::size_t index = 0; index < instances.size(); ++index)
        {
            std::array<float, 64> left {};
            std::array<float, 64> right {};
            const auto rendered = instances[index]->process(
                left.data(), right.data(), static_cast<std::uint32_t>(left.size()), false);
            heard[index] = heard[index] || (rendered && hasSignal(left));
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(2));
    }
    for (auto& instance : instances)
        instance->stop();
    for (const auto value : heard)
    {
        if (!value)
            return false;
    }
    return true;
}

bool failureRecoveryIsBounded(const char* failureVariable,
                              std::uint32_t blockCount)
{
    setEnvironment(failureVariable, "6");
    SidecarTransport instance;
    instance.configure(48000.0, 64U, 256U);
    if (!instance.start())
        return false;

    bool heardAfterRestart = false;
    std::chrono::steady_clock::duration longest {};
    for (std::uint32_t block = 0; block < blockCount; ++block)
    {
        std::array<float, 64> left {};
        std::array<float, 64> right {};
        const auto before = std::chrono::steady_clock::now();
        const auto rendered = instance.process(
            left.data(), right.data(), static_cast<std::uint32_t>(left.size()), false);
        const auto elapsed = std::chrono::steady_clock::now() - before;
        if (elapsed > longest)
            longest = elapsed;
        if (instance.restartCount() > 0U && rendered && hasSignal(left))
            heardAfterRestart = true;
        std::this_thread::sleep_for(std::chrono::milliseconds(2));
    }
    const auto restarts = instance.restartCount();
    instance.stop();
    clearEnvironment(failureVariable);
    return restarts == 1U && heardAfterRestart &&
           longest < std::chrono::milliseconds(20);
}

bool eventOffsetsSurviveLatencyPipeline()
{
    setEnvironment("MPVST_NATIVE_EVENT_GATE", "1");
    SidecarTransport instance;
    instance.configure(48000.0, 64U, 256U);
    if (!instance.start())
        return false;

    std::array<float, 512> captured {};
    for (std::uint32_t block = 0U; block < 8U; ++block)
    {
        std::array<float, 64> right {};
        std::array<mpvst_event, 2> events {};
        std::uint32_t eventCount = 0U;
        if (block == 0U)
        {
            events[0].sample_position = 17;
            events[0].type = MPVST_EVENT_NOTE_ON;
            events[0].data0 = 60;
            events[1].sample_position = 49;
            events[1].type = MPVST_EVENT_NOTE_OFF;
            events[1].data0 = 60;
            eventCount = 2U;
        }
        (void)instance.process(captured.data() + block * 64U, right.data(), 64U,
                               false, events.data(), eventCount);
        std::this_thread::sleep_for(std::chrono::milliseconds(6));
    }
    instance.stop();
    clearEnvironment("MPVST_NATIVE_EVENT_GATE");

    for (std::uint32_t sample = 0U; sample < captured.size(); ++sample)
    {
        const bool expectedOpen = sample >= 256U + 17U && sample < 256U + 49U;
        const bool isOpen = std::abs(captured[sample] - 0.125F) < 0.000001F;
        if (isOpen != expectedOpen)
        {
            std::cerr << "variable block mismatch at sample " << sample
                      << ": expected=" << expectedOpen
                      << " actual=" << captured[sample] << '\n';
            return false;
        }
    }
    return true;
}

bool variableBlocksPreserveBoundaryEvents()
{
    setEnvironment("MPVST_NATIVE_EVENT_GATE", "1");
    SidecarTransport instance;
    instance.configure(48000.0, 128U, 256U);
    if (!instance.start())
        return false;

    constexpr std::array<std::uint32_t, 10> sizes {
        31U, 97U, 1U, 64U, 128U, 17U, 111U, 23U, 89U, 128U};
    constexpr std::size_t capturedSize = 689U;
    std::array<float, capturedSize> captured {};
    std::size_t destination = 0U;
    for (std::size_t block = 0U; block < sizes.size(); ++block)
    {
        std::array<float, 128> right {};
        std::array<mpvst_event, 2> events {};
        std::uint32_t eventCount = 0U;
        if (block == 0U)
        {
            events[0].sample_position = 0;
            events[0].type = MPVST_EVENT_NOTE_ON;
            events[1].sample_position = 30;
            events[1].type = MPVST_EVENT_NOTE_OFF;
            eventCount = 2U;
        }
        else if (block == 1U)
        {
            events[0].sample_position = 0;
            events[0].type = MPVST_EVENT_NOTE_ON;
            events[1].sample_position = 48;
            events[1].type = MPVST_EVENT_NOTE_OFF;
            eventCount = 2U;
        }
        else if (block == 2U)
        {
            events[0].sample_position = 0;
            events[0].type = MPVST_EVENT_NOTE_ON;
            eventCount = 1U;
        }
        else if (block == 3U)
        {
            events[0].sample_position = 63;
            events[0].type = MPVST_EVENT_NOTE_OFF;
            eventCount = 1U;
        }

        const auto frames = sizes[block];
        (void)instance.process(captured.data() + destination, right.data(),
                               frames, false, events.data(), eventCount);
        destination += frames;
        std::this_thread::sleep_for(std::chrono::milliseconds(3));
    }
    instance.stop();
    clearEnvironment("MPVST_NATIVE_EVENT_GATE");

    for (std::size_t sample = 0U; sample < captured.size(); ++sample)
    {
        const bool expectedOpen =
            (sample >= 256U && sample < 286U) ||
            (sample >= 287U && sample < 335U) ||
            (sample >= 384U && sample < 448U);
        const bool isOpen = std::abs(captured[sample] - 0.125F) < 0.000001F;
        if (isOpen != expectedOpen)
            return false;
    }
    return true;
}

bool offlineRenderingWaitsForOutput()
{
    setEnvironment("MPVST_NATIVE_EVENT_GATE", "1");
    SidecarTransport instance;
    instance.configure(48000.0, 64U, 256U);
    if (!instance.start())
        return false;

    std::array<float, 512> captured {};
    for (std::uint32_t block = 0U; block < 8U; ++block)
    {
        std::array<float, 64> right {};
        mpvst_event event {};
        std::uint32_t eventCount = 0U;
        if (block == 0U)
        {
            event.sample_position = 0;
            event.type = MPVST_EVENT_NOTE_ON;
            eventCount = 1U;
        }
        (void)instance.process(captured.data() + block * 64U, right.data(), 64U,
                               false, &event, eventCount, true);
    }
    instance.stop();
    clearEnvironment("MPVST_NATIVE_EVENT_GATE");

    for (std::size_t sample = 0U; sample < captured.size(); ++sample)
    {
        const auto expected = sample >= 256U ? 0.125F : 0.0F;
        if (std::abs(captured[sample] - expected) > 0.000001F)
            return false;
    }
    return true;
}

} // namespace

int main(int argc, char** argv)
{
    if (argc != 2)
        return 2;
    setEnvironment("MPVST_ENGINE_PATH", argv[1]);
    setEnvironment("MPVST_NATIVE_TEST_TONE", "1");

    if (!eightIndependentInstances())
    {
        std::cerr << "eight-instance isolation failed\n";
        return 3;
    }
    if (!failureRecoveryIsBounded("MPVST_NATIVE_EXIT_AFTER_BLOCKS", 300U))
    {
        std::cerr << "bounded crash recovery failed\n";
        return 4;
    }
    if (!failureRecoveryIsBounded("MPVST_NATIVE_STALL_AFTER_BLOCKS", 600U))
    {
        std::cerr << "bounded stall recovery failed\n";
        return 5;
    }
    if (!eventOffsetsSurviveLatencyPipeline())
    {
        std::cerr << "sample-offset event pipeline failed\n";
        return 6;
    }
    if (!variableBlocksPreserveBoundaryEvents())
    {
        std::cerr << "variable-block boundary event pipeline failed\n";
        return 7;
    }
    if (!offlineRenderingWaitsForOutput())
    {
        std::cerr << "offline render was outrun by host\n";
        return 8;
    }
    std::cout << "eight instances, recovery, fixed/variable events, and offline render passed\n";
    return 0;
}
