#pragma once

#include "mpvst/child_process.h"
#include "mpvst/protocol.h"
#include "mpvst/shared_memory.h"

#include <cstdint>
#include <atomic>
#include <string>
#include <thread>

namespace PyDevices::MicroPythonVST3 {

class SidecarTransport final
{
public:
    ~SidecarTransport();

    SidecarTransport(const SidecarTransport&) = delete;
    SidecarTransport& operator=(const SidecarTransport&) = delete;
    SidecarTransport() = default;

    static std::string initialScriptSource();
    void setScriptSource(std::string source);

    void configure(double sampleRate, std::uint32_t maxFrames,
                   std::uint32_t latencySamples) noexcept;
    bool start();
    void stop() noexcept;

    // Audio-thread entry point: bounded, lock-free, and allocation-free.
    bool process(float* left, float* right, std::uint32_t frames,
                 bool bypassed, const mpvst_event* events = nullptr,
                 std::uint32_t eventCount = 0U,
                 bool offline = false) noexcept;

    std::uint32_t latencySamples() const noexcept { return latencySamples_; }
    bool ready() const noexcept { return available_.load(); }
    std::uint64_t restartCount() const noexcept;
    std::uint32_t errorCode() noexcept;
    std::string diagnostic();
    bool requestReload() noexcept;

private:
    static std::string nativeEnginePath();
    bool launchEngine();
    bool resetMappingForRestart() noexcept;
    void supervise() noexcept;
    void waitForCallbacks() noexcept;
    mpvst_output_slot* outputAt(std::uint64_t position) const noexcept;
    void submitWork(std::int64_t startSample, std::uint32_t frames,
                    const mpvst_event* events,
                    std::uint32_t eventCount) noexcept;
    bool consumeOutput(float* left, float* right, std::int64_t startSample,
                       std::uint32_t frames, bool countUnderrun = true) noexcept;

    mpvst::SharedMemory mapping_;
    mpvst::ChildProcess child_;
    mpvst_shared_header* header_ = nullptr;
    mpvst_status* status_ = nullptr;
    mpvst_command* commands_ = nullptr;
    mpvst_event* events_ = nullptr;
    mpvst_work_slot* work_ = nullptr;
    std::string mappingName_;
    std::string scriptSource_;
    std::string materializedScriptPath_;
    std::uint64_t mappingBytes_ = 0U;
    std::uint64_t instanceNonce_ = 0U;
    double sampleRate_ = 48000.0;
    std::uint64_t sampleRateMillihz_ = UINT64_C(48000000);
    std::uint32_t maxFrames_ = 0U;
    std::uint32_t latencySamples_ = 0U;
    std::uint64_t workPosition_ = 0U;
    std::uint64_t commandPosition_ = 0U;
    std::uint64_t eventPosition_ = 0U;
    std::uint64_t outputPosition_ = 0U;
    std::uint32_t outputOffset_ = 0U;
    std::int64_t streamPosition_ = 0;
    bool testTone_ = false;
    std::atomic<bool> available_ {false};
    std::atomic<bool> supervisorStop_ {false};
    std::atomic<std::uint32_t> activeCallbacks_ {0U};
    std::atomic<std::uint64_t> restartCount_ {0U};
    std::thread supervisor_;
};

} // namespace PyDevices::MicroPythonVST3
