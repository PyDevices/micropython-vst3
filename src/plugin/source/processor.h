#pragma once

#include "public.sdk/source/vst/vstaudioeffect.h"

#include "parameters.h"
#include "sidecar_transport.h"

#include <array>
#include <atomic>
#include <string>
#include <vector>

namespace PyDevices::MicroPythonVST3 {

class Processor final : public Steinberg::Vst::AudioEffect
{
public:
    // effectMode adds a stereo audio-input bus whose blocks travel to the
    // sidecar alongside the events, and gives bypass pass-through semantics.
    explicit Processor (bool effectMode = false);

    static Steinberg::FUnknown* createInstance (void*);
    static Steinberg::FUnknown* createEffectInstance (void*);

    Steinberg::tresult PLUGIN_API initialize (Steinberg::FUnknown* context) override;
    Steinberg::tresult PLUGIN_API setBusArrangements (
        Steinberg::Vst::SpeakerArrangement* inputs,
        Steinberg::int32 numInputs,
        Steinberg::Vst::SpeakerArrangement* outputs,
        Steinberg::int32 numOutputs) override;
    Steinberg::tresult PLUGIN_API canProcessSampleSize (
        Steinberg::int32 symbolicSampleSize) override;
    Steinberg::tresult PLUGIN_API setupProcessing (
        Steinberg::Vst::ProcessSetup& setup) override;
    Steinberg::tresult PLUGIN_API setActive (Steinberg::TBool state) override;
    Steinberg::tresult PLUGIN_API setProcessing (Steinberg::TBool state) override;
    Steinberg::uint32 PLUGIN_API getLatencySamples () override;
    Steinberg::tresult PLUGIN_API process (Steinberg::Vst::ProcessData& data) override;
    Steinberg::tresult PLUGIN_API setState (Steinberg::IBStream* state) override;
    Steinberg::tresult PLUGIN_API getState (Steinberg::IBStream* state) override;
    Steinberg::tresult PLUGIN_API connect (
        Steinberg::Vst::IConnectionPoint* other) override;

private:
    enum class ReloadFadeState : std::uint8_t
    {
        Idle,
        FadingOut,
        Holding,
        FadingIn
    };

    std::uint32_t collectParameterChanges (
        Steinberg::Vst::IParameterChanges* changes,
        Steinberg::int32 frameCount, std::uint32_t count) noexcept;
    std::uint32_t collectEvents (Steinberg::Vst::IEventList* input,
                                 Steinberg::int32 frameCount,
                                 std::uint32_t count) noexcept;
    std::uint32_t emitMacroResync (Steinberg::int32 frameCount,
                                   std::uint32_t count) noexcept;
    SidecarTransport::TransportInfo readTransport (
        Steinberg::Vst::ProcessData& data) noexcept;
    std::uint32_t emitTransportEvent (
        const SidecarTransport::TransportInfo& transport,
        Steinberg::int32 frameCount, std::uint32_t count) noexcept;
    void sortEvents (std::uint32_t count) noexcept;
    void publishEngineStatus (
        Steinberg::Vst::IParameterChanges* changes) noexcept;
    void applyReloadFade (float* left, float* right,
                          std::uint32_t frames) noexcept;
    // Tell the controller where the editor's mapping is. Sent whenever it
    // could have changed - a connection, an activation, a deactivation - and
    // never from the audio thread.
    void publishUiMapping () noexcept;
    static void clearOutput (Steinberg::Vst::ProcessData& data) noexcept;

    std::atomic<Steinberg::uint32> bypass_ {0};
    std::atomic<Steinberg::uint32> reloadLatch_ {0};
    std::atomic<Steinberg::uint32> active_ {0};
    std::atomic<Steinberg::uint32> macroResyncPending_ {1};
    std::array<std::atomic<float>, kMacroParameterCount> macros_ {};
    std::string scriptSource_;
    Steinberg::int32 pipelineBlocks_ {kDefaultPipelineBlocks};
    float publishedReady_ {-1.0F};
    float publishedError_ {-1.0F};
    std::uint32_t configuredMaxFrames_ {0U};
    double sampleRate_ {48000.0};
    std::int64_t expectedProjectSample_ {0};
    bool haveTransport_ {false};
    bool lastPlaying_ {false};
    std::uint32_t fadeSamplesRemaining_ {0U};
    std::uint32_t holdSamplesRemaining_ {0U};
    ReloadFadeState reloadFadeState_ {ReloadFadeState::Idle};
    std::array<mpvst_event, 256> events_ {};
    const bool effectMode_ {false};
    // Host input is staged before the output buffers are cleared because
    // hosts may process in place, and the bypass path replays it through a
    // latency-matched delay so toggling bypass never shifts time.
    std::vector<float> inputStagingLeft_;
    std::vector<float> inputStagingRight_;
    std::vector<float> bypassDelayLeft_;
    std::vector<float> bypassDelayRight_;
    std::uint32_t bypassDelayIndex_ {0U};
    SidecarTransport sidecar_;
};

static_assert (std::atomic<float>::is_always_lock_free,
               "VST parameter snapshots require lock-free float atomics");
static_assert (std::atomic<Steinberg::uint32>::is_always_lock_free,
               "VST bypass state requires a lock-free integer atomic");

} // namespace PyDevices::MicroPythonVST3
