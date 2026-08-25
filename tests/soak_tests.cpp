// Long-running soak for the sidecar transport.
//
// The short form runs as part of the ordinary suite so the soak itself cannot
// rot. Passing a longer duration on the command line runs the same scenario for
// as long as wanted, which is how the multi-minute soaks are exercised.
//
// The scenario deliberately mixes the things that have historically broken
// pipelines: several instances competing for the machine, block sizes that
// change every callback, a steady stream of events, periodic bypass, and
// periodic transport locates.
//
// Offline export is deliberately not part of this loop. An offline block may
// wait for its exact output slot, so interleaving one into a real-time paced
// loop starves every other instance and measures the harness rather than the
// product. offlineRenderingWaitsForOutput covers that path directly, and every
// render in the REAPER matrix is an offline render.

#include "sidecar_transport.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <memory>
#include <random>
#include <thread>
#include <string>
#include <vector>

namespace {

using PyDevices::MicroPythonVST3::SidecarTransport;

constexpr std::uint32_t kMaxFrames = 512U;
constexpr std::size_t kInstanceCount = 4U;

void setEnvironment(const char* name, const std::string& value)
{
#if defined(_WIN32)
    (void)_putenv_s(name, value.c_str());
#else
    (void)setenv(name, value.c_str(), 1);
#endif
}

struct Instance
{
    std::unique_ptr<SidecarTransport> transport;
    std::vector<float> left;
    std::vector<float> right;
    std::int64_t samplesRendered = 0;
};

bool finite(const std::vector<float>& samples, std::uint32_t frames)
{
    for (std::uint32_t index = 0; index < frames; ++index)
    {
        if (!std::isfinite(samples[index]))
            return false;
    }
    return true;
}

} // namespace

int main(int argc, char** argv)
{
    if (argc < 2)
    {
        std::cerr << "usage: mpvst_soak_tests <engine-path> [seconds]\n";
        return 2;
    }
    setEnvironment("MPVST_ENGINE_PATH", argv[1]);
    setEnvironment("MPVST_NATIVE_EVENT_GATE", "1");
    const auto seconds = argc > 2 ? std::stod(argv[2]) : 5.0;

    std::vector<Instance> instances(kInstanceCount);
    for (auto& instance : instances)
    {
        instance.transport = std::make_unique<SidecarTransport>();
        instance.left.assign(kMaxFrames, 0.0F);
        instance.right.assign(kMaxFrames, 0.0F);
        instance.transport->configure(48000.0, kMaxFrames, kMaxFrames * 4U);
        if (!instance.transport->start())
        {
            std::cerr << "soak: an instance failed to start\n";
            return 3;
        }
    }

    std::mt19937_64 random(UINT64_C(0xc0ffee));
    const auto deadline = std::chrono::steady_clock::now() +
                          std::chrono::milliseconds(
                              static_cast<std::int64_t>(seconds * 1000.0));
    std::uint64_t callbacks = 0U;
    bool gateOpen = false;
    std::vector<std::uint64_t> lastRestarts(instances.size(), 0U);
    const auto started = std::chrono::steady_clock::now();

    while (std::chrono::steady_clock::now() < deadline)
    {
        // Every callback uses a different block size, including the extremes.
        const auto frames = static_cast<std::uint32_t>(
            1U + random() % kMaxFrames);
        const bool bypassed = (callbacks % 601U) == 0U;

        std::array<mpvst_event, 4> events {};
        std::uint32_t eventCount = 0U;
        if ((callbacks % 17U) == 0U)
        {
            gateOpen = !gateOpen;
            events[eventCount].sample_position =
                static_cast<std::int64_t>(random() % frames);
            events[eventCount].type = gateOpen ? MPVST_EVENT_NOTE_ON
                                               : MPVST_EVENT_NOTE_OFF;
            events[eventCount].data0 = 60;
            events[eventCount].value0 = gateOpen ? 1.0F : 0.0F;
            ++eventCount;
        }
        if ((callbacks % 53U) == 0U)
        {
            events[eventCount].sample_position = 0;
            events[eventCount].type = MPVST_EVENT_PARAMETER;
            events[eventCount].data0 = 0;
            events[eventCount].value0 =
                static_cast<float>(random() % 1000U) / 1000.0F;
            ++eventCount;
        }

        SidecarTransport::TransportInfo transport;
        transport.playing = true;
        // A locate every so often, so discontinuity handling is under load too.
        transport.discontinuity = (callbacks % 997U) == 0U;

        const auto callbackStarted = std::chrono::steady_clock::now();
        for (auto& instance : instances)
        {
            transport.projectSample = instance.samplesRendered;
            (void)instance.transport->process(
                instance.left.data(), instance.right.data(), frames, bypassed,
                events.data(), eventCount, false, &transport);
            instance.samplesRendered += frames;
            if (!finite(instance.left, frames) || !finite(instance.right, frames))
            {
                std::cerr << "soak: non-finite sample after " << callbacks
                          << " callbacks\n";
                return 4;
            }
        }
        ++callbacks;

        // Report the moment anything restarts rather than only the totals, so
        // a soak failure says when the pipeline broke and what it was doing.
        if ((callbacks % 64U) == 0U)
        {
            for (std::size_t index = 0; index < instances.size(); ++index)
            {
                const auto snapshot = instances[index].transport->telemetry();
                if (snapshot.restarts > lastRestarts[index])
                {
                    const auto since = std::chrono::duration_cast<
                        std::chrono::milliseconds>(
                        std::chrono::steady_clock::now() - started).count();
                    std::cout << "  [" << since << "ms] instance " << index
                              << " restarted (" << snapshot.restarts
                              << " total) after " << callbacks
                              << " callbacks, last exit code "
                              << snapshot.lastExitCode << '\n';
                    lastRestarts[index] = snapshot.restarts;
                }
            }
        }

        // Pace the loop at roughly the rate a host would call back. Without
        // this the soak just outruns the engine and measures a starved
        // pipeline rather than a working one.
        const auto blockDuration = std::chrono::microseconds(
            static_cast<std::int64_t>(frames * 1000000.0 / 48000.0));
        const auto elapsed = std::chrono::steady_clock::now() - callbackStarted;
        if (elapsed < blockDuration)
            std::this_thread::sleep_for(blockDuration - elapsed);
    }

    int status = 0;
    std::uint64_t totalUnderruns = 0U;
    std::uint64_t totalDrops = 0U;
    for (std::size_t index = 0; index < instances.size(); ++index)
    {
        const auto snapshot = instances[index].transport->telemetry();
        totalUnderruns += snapshot.underruns;
        totalDrops += snapshot.eventDrops;
        if (!snapshot.ready)
        {
            std::cerr << "soak: instance " << index << " is not ready\n";
            status = 5;
        }
        if (snapshot.restarts != 0U)
        {
            std::cerr << "soak: instance " << index << " restarted "
                      << snapshot.restarts << " times\n";
            status = 6;
        }
        // Work and output are separate eight-slot rings, so a fully backed up
        // pipeline holds sixteen blocks. Anything beyond that means the
        // producer overran a ring rather than being throttled by it.
        if (snapshot.queueDepthHighWater > 16U)
        {
            std::cerr << "soak: instance " << index << " queue peaked at "
                      << snapshot.queueDepthHighWater << '\n';
            status = 7;
        }
        std::cout << "instance " << index
                  << " blocks=" << snapshot.blocksRendered
                  << " underruns=" << snapshot.underruns
                  << " drops=" << snapshot.eventDrops
                  << " queue_peak=" << snapshot.queueDepthHighWater
                  << " render_peak_ns=" << snapshot.renderTimeHighWaterNs << '\n';
    }
    for (auto& instance : instances)
        instance.transport->stop();

    std::cout << "soak completed " << callbacks << " callbacks per instance over "
              << seconds << "s: underruns=" << totalUnderruns
              << " drops=" << totalDrops << '\n';
    return status;
}
