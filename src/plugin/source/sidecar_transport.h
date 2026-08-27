#pragma once

#include "mpvst/child_process.h"
#include "mpvst/protocol.h"
#include "mpvst/shared_memory.h"
#include "mpvst/ui.h"

#include <cstdint>
#include <atomic>
#include <string>
#include <chrono>
#include <thread>

namespace PyDevices::MicroPythonVST3 {

class SidecarTransport final
{
public:
    ~SidecarTransport();

    SidecarTransport(const SidecarTransport&) = delete;
    SidecarTransport& operator=(const SidecarTransport&) = delete;
    SidecarTransport() = default;

    // Where an instance's script came from. A developer-file instance follows
    // MPVST_SCRIPT_PATH on disk so reloads pick up edits; a restored snapshot
    // stays pinned to the source embedded in the project state.
    enum class ScriptOrigin
    {
        DeveloperFile,
        RestoredSnapshot,
    };

    // The script a script-host instance starts with: MPVST_SCRIPT_PATH when
    // it is set, and otherwise the default that suits the slot - a synth for
    // an instrument, a pass-through for an effect. An effect host that loaded
    // the instrument default would be a polyphonic synth in an effect slot,
    // ignoring its input and silent until something sends it notes.
    static std::string initialScriptSource(bool effectMode);
    static std::string developerScriptPath();
    void setScriptSource(std::string source,
                         ScriptOrigin origin = ScriptOrigin::RestoredSnapshot);
    // Re-reads the developer file, if this instance follows one, and returns
    // the source that should be embedded in project state. Not real-time safe.
    std::string refreshDeveloperScriptSource();

    void configure(double sampleRate, std::uint32_t maxFrames,
                   std::uint32_t latencySamples) noexcept;
    // An effect instance carries host audio to the engine: the shared mapping
    // gains one input block per work slot and process() forwards the bus.
    // Must be set before start().
    void setInputEnabled(bool enabled) noexcept { inputEnabled_ = enabled; }
    bool inputEnabled() const noexcept { return inputEnabled_; }
    bool start();
    void stop() noexcept;

    // What the host says about its timeline for the current block. Defaults
    // describe a stopped transport at the start of the project.
    struct TransportInfo
    {
        std::int64_t projectSample = 0;
        std::uint64_t tempoMicroBpm = UINT64_C(120000000);
        std::uint16_t timeSignatureNumerator = 4U;
        std::uint16_t timeSignatureDenominator = 4U;
        bool playing = false;
        bool discontinuity = false;
    };

    // Audio-thread entry point: bounded, lock-free, and allocation-free.
    // inputLeft/inputRight carry the host's audio-input bus for effect
    // instances; they are copied into the block's input region before the
    // work slot is published and may alias the output pointers.
    bool process(float* left, float* right, std::uint32_t frames,
                 bool bypassed, const mpvst_event* events = nullptr,
                 std::uint32_t eventCount = 0U,
                 bool offline = false,
                 const TransportInfo* transport = nullptr,
                 const float* inputLeft = nullptr,
                 const float* inputRight = nullptr) noexcept;

    // A point-in-time view of how the sidecar is coping. Every field is
    // gathered from counters the audio thread only ever adds to, so reading it
    // never blocks the caller and never disturbs rendering. Read it from a
    // timer or the editor, not from the audio callback.
    struct Telemetry
    {
        std::uint64_t blocksRequested = 0U;
        std::uint64_t blocksRendered = 0U;
        std::uint64_t underruns = 0U;
        std::uint64_t eventDrops = 0U;
        std::uint64_t eventsConsumed = 0U;
        std::uint64_t restarts = 0U;
        std::uint64_t renderTimeLastNs = 0U;
        std::uint64_t renderTimeHighWaterNs = 0U;
        std::uint32_t queueDepth = 0U;
        std::uint32_t queueDepthHighWater = 0U;
        std::uint32_t errorCode = 0U;
        std::uint32_t engineState = 0U;
        std::int32_t lastExitCode = 0;
        bool lastExitWasUnexpected = false;
        bool ready = false;
    };

    Telemetry telemetry() noexcept;
    void resetTelemetryPeaks() noexcept;

    // The editor's shared mapping, created alongside the audio one and named
    // after it. Empty when the region could not be created, which costs the
    // instance an editor and nothing else. The view opens it by name from
    // whichever process the host puts the controller in.
    const std::string& uiMappingName() const noexcept { return uiMappingName_; }
    std::uint32_t uiGeneration() const noexcept { return uiGeneration_; }

    std::uint32_t latencySamples() const noexcept { return latencySamples_; }
    bool ready() const noexcept { return available_.load(); }
    std::uint64_t restartCount() const noexcept;
    std::uint32_t errorCode() noexcept;
    std::string diagnostic();
    bool requestReload() noexcept;

private:
    static std::string enginePath();
    bool launchEngine();
    bool resetMappingForRestart() noexcept;
    void supervise() noexcept;
    void waitForCallbacks() noexcept;
    mpvst_output_slot* outputAt(std::uint64_t position) const noexcept;
    void submitWork(std::int64_t startSample, std::uint32_t frames,
                    const mpvst_event* events,
                    std::uint32_t eventCount,
                    const TransportInfo* transport,
                    const float* inputLeft,
                    const float* inputRight) noexcept;
    bool consumeOutput(float* left, float* right, std::int64_t startSample,
                       std::uint32_t frames, bool countUnderrun = true) noexcept;

    mpvst::SharedMemory mapping_;
    mpvst::SharedMemory uiMapping_;
    mpvst::ChildProcess child_;
    mpvst_shared_header* header_ = nullptr;
    mpvst_status* status_ = nullptr;
    mpvst_command* commands_ = nullptr;
    mpvst_event* events_ = nullptr;
    mpvst_work_slot* work_ = nullptr;
    std::string mappingName_;
    std::string uiMappingName_;
    std::uint32_t uiGeneration_ = 0U;
    std::string scriptSource_;
    ScriptOrigin scriptOrigin_ {ScriptOrigin::RestoredSnapshot};
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
    bool inputEnabled_ = false;
    std::atomic<bool> available_ {false};
    std::atomic<bool> supervisorStop_ {false};
    std::atomic<std::uint32_t> activeCallbacks_ {0U};
    std::atomic<std::uint64_t> restartCount_ {0U};
    // steady_clock ticks at the last process() call, so the supervisor can tell
    // an engine that has stopped working from a host that has stopped asking.
    std::atomic<std::chrono::steady_clock::rep> lastCallbackTicks_ {0};
    std::atomic<std::uint64_t> renderTimeLastNs_ {0U};
    std::atomic<std::uint64_t> renderTimeHighWaterNs_ {0U};
    std::atomic<std::uint32_t> queueDepth_ {0U};
    std::atomic<std::uint32_t> queueDepthHighWater_ {0U};
    std::atomic<std::int32_t> lastExitCode_ {0};
    std::atomic<bool> lastExitWasUnexpected_ {false};
    std::thread supervisor_;
};

} // namespace PyDevices::MicroPythonVST3
