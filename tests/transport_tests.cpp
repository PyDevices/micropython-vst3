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

template <std::size_t N>
bool hasSignal(const std::array<float, N>& samples)
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

bool bypassDoesNotStrandThePipeline()
{
    // Bypassed blocks still submit work. If their output is never consumed the
    // ring fills, the engine cannot publish, and the supervisor restarts what
    // looks like a hung engine. Far more bypassed blocks than there are slots
    // must pass without a single restart, and audio must return afterwards.
    SidecarTransport transport;
    transport.configure(48000.0, 128U, 512U);
    if (!transport.start())
        return false;

    std::array<float, 128> left {};
    std::array<float, 128> right {};
    const auto frames = static_cast<std::uint32_t>(left.size());

    for (std::uint32_t block = 0; block < 8U; ++block)
    {
        (void)transport.process(left.data(), right.data(), frames, false);
        std::this_thread::sleep_for(std::chrono::milliseconds(2));
    }
    for (std::uint32_t block = 0; block < 64U; ++block)
    {
        (void)transport.process(left.data(), right.data(), frames, true);
        for (const auto sample : left)
        {
            if (sample != 0.0F)
            {
                transport.stop();
                return false;
            }
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(2));
    }

    bool heardAfterBypass = false;
    for (std::uint32_t block = 0; block < 48U; ++block)
    {
        (void)transport.process(left.data(), right.data(), frames, false);
        heardAfterBypass = heardAfterBypass || hasSignal(left);
        std::this_thread::sleep_for(std::chrono::milliseconds(2));
    }

    const auto snapshot = transport.telemetry();
    transport.stop();
    return heardAfterBypass && snapshot.restarts == 0U && snapshot.ready;
}

bool telemetryReportsPipelineHealth()
{
    SidecarTransport transport;
    transport.configure(48000.0, 128U, 512U);
    if (!transport.start())
        return false;

    std::array<float, 128> left {};
    std::array<float, 128> right {};
    for (std::uint32_t block = 0; block < 64U; ++block)
    {
        (void)transport.process(left.data(), right.data(),
                                static_cast<std::uint32_t>(left.size()), false);
        std::this_thread::sleep_for(std::chrono::milliseconds(2));
    }

    const auto snapshot = transport.telemetry();
    transport.stop();

    if (!snapshot.ready || snapshot.blocksRequested == 0U ||
        snapshot.blocksRendered == 0U)
        return false;
    // The engine timed every block it retired, so a high-water mark of zero
    // would mean the render clock never ran.
    if (snapshot.renderTimeHighWaterNs == 0U)
        return false;
    if (snapshot.renderTimeLastNs > snapshot.renderTimeHighWaterNs)
        return false;
    // Blocks are handed over before they come back, so the pipeline is never
    // empty in steady state and its peak cannot exceed the ring.
    if (snapshot.queueDepthHighWater == 0U || snapshot.queueDepthHighWater > 8U)
        return false;
    if (snapshot.queueDepth > snapshot.queueDepthHighWater)
        return false;
    if (snapshot.restarts != 0U || snapshot.lastExitWasUnexpected)
        return false;
    return snapshot.blocksRendered <= snapshot.blocksRequested;
}

bool telemetryRecordsCrashReason()
{
    setEnvironment("MPVST_NATIVE_EXIT_AFTER_BLOCKS", "8");
    SidecarTransport transport;
    transport.configure(48000.0, 128U, 512U);
    if (!transport.start())
    {
        clearEnvironment("MPVST_NATIVE_EXIT_AFTER_BLOCKS");
        return false;
    }

    std::array<float, 128> left {};
    std::array<float, 128> right {};
    for (std::uint32_t block = 0; block < 200U; ++block)
    {
        (void)transport.process(left.data(), right.data(),
                                static_cast<std::uint32_t>(left.size()), false);
        std::this_thread::sleep_for(std::chrono::milliseconds(2));
    }
    const auto snapshot = transport.telemetry();
    transport.stop();
    clearEnvironment("MPVST_NATIVE_EXIT_AFTER_BLOCKS");

    // The engine was told to exit early, so the supervisor must have replaced
    // it and telemetry must be able to say that it went away unexpectedly.
    return snapshot.restarts > 0U && snapshot.lastExitWasUnexpected;
}

bool effectCarriesHostAudio()
{
    // An input-enabled transport must deliver the host bus to the engine and
    // return the processed audio on the same latency contract as an
    // instrument. The native engine halves its input exactly, so every output
    // sample must equal the input from one pipeline-latency earlier times 0.5,
    // on both channels independently.
    SidecarTransport instance;
    instance.setInputEnabled(true);
    instance.configure(48000.0, 64U, 256U);
    if (!instance.start())
        return false;

    std::array<float, 512> capturedLeft {};
    std::array<float, 512> capturedRight {};
    std::array<float, 512> sent {};
    for (std::uint32_t block = 0U; block < 8U; ++block)
    {
        std::array<float, 64> inputLeft {};
        std::array<float, 64> inputRight {};
        for (std::uint32_t frame = 0U; frame < 64U; ++frame)
        {
            const auto sample = block * 64U + frame;
            const auto value =
                static_cast<float>(sample % 97U) / 128.0F - 0.35F;
            inputLeft[frame] = value;
            inputRight[frame] = -0.5F * value;
            sent[sample] = value;
        }
        (void)instance.process(capturedLeft.data() + block * 64U,
                               capturedRight.data() + block * 64U, 64U,
                               false, nullptr, 0U, true, nullptr,
                               inputLeft.data(), inputRight.data());
    }
    instance.stop();

    for (std::size_t sample = 0U; sample < capturedLeft.size(); ++sample)
    {
        const auto expectedLeft = sample >= 256U ? sent[sample - 256U] * 0.5F
                                                 : 0.0F;
        const auto expectedRight = -0.5F * expectedLeft;
        if (std::abs(capturedLeft[sample] - expectedLeft) > 0.000001F ||
            std::abs(capturedRight[sample] - expectedRight) > 0.000001F)
        {
            std::cerr << "effect audio mismatch at sample " << sample
                      << ": expected=" << expectedLeft
                      << " actual=" << capturedLeft[sample] << '\n';
            return false;
        }
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
    if (!bypassDoesNotStrandThePipeline())
    {
        std::cerr << "bypass stranded the sidecar pipeline\n";
        return 11;
    }
    if (!telemetryReportsPipelineHealth())
    {
        std::cerr << "telemetry snapshot was not plausible\n";
        return 9;
    }
    if (!telemetryRecordsCrashReason())
    {
        std::cerr << "telemetry did not record an unexpected engine exit\n";
        return 10;
    }
    if (!effectCarriesHostAudio())
    {
        std::cerr << "effect input pipeline failed\n";
        return 12;
    }
    std::cout << "eight instances, recovery, fixed/variable events, offline render, "
                 "and telemetry passed\n";
    return 0;
}
