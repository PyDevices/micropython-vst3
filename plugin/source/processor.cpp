#include "processor.h"

#include "cids.h"

#include "base/source/fstreamer.h"
#include "pluginterfaces/vst/ivstevents.h"
#include "pluginterfaces/vst/ivstmidicontrollers.h"
#include "pluginterfaces/vst/ivstparameterchanges.h"

#include <algorithm>
#include <cmath>

namespace PyDevices::MicroPythonVST3 {

using namespace Steinberg;
using namespace Steinberg::Vst;

Processor::Processor (bool effectMode)
    : scriptSource_ (SidecarTransport::initialScriptSource ())
    , effectMode_ (effectMode)
{
    setControllerClass (effectMode_ ? kEffectControllerUID : kControllerUID);
    for (auto& value : macros_)
        value.store (0.5f, std::memory_order_relaxed);
    sidecar_.setInputEnabled (effectMode_);
    sidecar_.setScriptSource (scriptSource_,
                              SidecarTransport::ScriptOrigin::DeveloperFile);
}

FUnknown* Processor::createInstance (void*)
{
    return static_cast<IAudioProcessor*> (new Processor ());
}

FUnknown* Processor::createEffectInstance (void*)
{
    return static_cast<IAudioProcessor*> (new Processor (true));
}

tresult PLUGIN_API Processor::initialize (FUnknown* context)
{
    const auto result = AudioEffect::initialize (context);
    if (result != kResultOk)
        return result;

    if (effectMode_)
        addAudioInput (STR16 ("Stereo In"), SpeakerArr::kStereo);
    addAudioOutput (STR16 ("Stereo Out"), SpeakerArr::kStereo);
    addEventInput (STR16 ("Event In"), static_cast<int32> (kMidiChannelCount));
    return kResultOk;
}

tresult PLUGIN_API Processor::setBusArrangements (
    SpeakerArrangement* inputs, int32 numInputs,
    SpeakerArrangement* outputs, int32 numOutputs)
{
    if (numOutputs != 1 || outputs == nullptr || outputs[0] != SpeakerArr::kStereo)
        return kResultFalse;
    if (effectMode_)
    {
        if (numInputs != 1 || inputs == nullptr || inputs[0] != SpeakerArr::kStereo)
            return kResultFalse;
        return AudioEffect::setBusArrangements (inputs, numInputs, outputs,
                                                numOutputs);
    }
    if (numInputs != 0)
        return kResultFalse;
    return AudioEffect::setBusArrangements (nullptr, 0, outputs, numOutputs);
}

tresult PLUGIN_API Processor::canProcessSampleSize (int32 symbolicSampleSize)
{
    return symbolicSampleSize == kSample32 ? kResultTrue : kResultFalse;
}

tresult PLUGIN_API Processor::setupProcessing (ProcessSetup& setup)
{
    if (setup.symbolicSampleSize != kSample32 || setup.maxSamplesPerBlock <= 0 ||
        setup.sampleRate <= 0.0)
        return kResultFalse;

    const auto maxFrames = static_cast<uint32> (setup.maxSamplesPerBlock);
    configuredMaxFrames_ = maxFrames;
    sampleRate_ = setup.sampleRate;
    sidecar_.configure (setup.sampleRate, maxFrames,
                        maxFrames * static_cast<uint32> (pipelineBlocks_));
    if (effectMode_)
    {
        inputStagingLeft_.assign (maxFrames, 0.0F);
        inputStagingRight_.assign (maxFrames, 0.0F);
        // Sized for the largest latency any pipeline depth can report, so a
        // depth restored from project state never needs a resize here.
        const auto delayFrames = static_cast<std::size_t> (maxFrames) *
                                 static_cast<std::size_t> (kMaximumPipelineBlocks);
        bypassDelayLeft_.assign (delayFrames, 0.0F);
        bypassDelayRight_.assign (delayFrames, 0.0F);
        bypassDelayIndex_ = 0U;
    }
    return AudioEffect::setupProcessing (setup);
}

tresult PLUGIN_API Processor::setActive (TBool state)
{
    if (state)
    {
        reloadFadeState_ = ReloadFadeState::Idle;
        fadeSamplesRemaining_ = 0U;
        holdSamplesRemaining_ = 0U;
        active_.store (1U, std::memory_order_relaxed);
        macroResyncPending_.store (1U, std::memory_order_relaxed);
        (void)sidecar_.start ();
    }
    else
    {
        active_.store (0U, std::memory_order_relaxed);
        sidecar_.stop ();
    }
    return AudioEffect::setActive (state);
}

tresult PLUGIN_API Processor::setProcessing (TBool)
{
    return kResultOk;
}

uint32 PLUGIN_API Processor::getLatencySamples ()
{
    return sidecar_.latencySamples ();
}

std::uint32_t Processor::collectParameterChanges (IParameterChanges* changes,
                                                  int32 frameCount,
                                                  std::uint32_t count) noexcept
{
    if (changes == nullptr)
        return count;

    const auto parameterCount = changes->getParameterCount ();
    for (int32 index = 0; index < parameterCount; ++index)
    {
        auto* queue = changes->getParameterData (index);
        if (queue == nullptr || queue->getPointCount () <= 0)
            continue;

        const auto id = queue->getParameterId ();
        std::uint16_t midiChannel = 0;
        std::uint16_t midiController = 0;
        if (decodeMidiParameter (id, midiChannel, midiController))
        {
            const auto pointCount = queue->getPointCount ();
            for (int32 point = 0;
                 point < pointCount && count < events_.size (); ++point)
            {
                int32 sampleOffset = 0;
                ParamValue value = 0.0;
                if (queue->getPoint (point, sampleOffset, value) != kResultTrue)
                    continue;
                if (frameCount <= 0)
                    continue;

                mpvst_event event {};
                event.sample_position = std::clamp<int32> (sampleOffset, 0,
                                                            frameCount - 1);
                event.channel = midiChannel;
                event.data0 = midiController;
                event.value0 = static_cast<float> (std::clamp (value, 0.0, 1.0));
                if (midiController == kPitchBend)
                {
                    event.type = MPVST_EVENT_PITCH_BEND;
                    event.value1 = event.value0 * 2.0F - 1.0F;
                }
                else if (midiController == kAfterTouch)
                {
                    event.type = MPVST_EVENT_CHANNEL_PRESSURE;
                }
                else
                {
                    event.type = MPVST_EVENT_CONTROL_CHANGE;
                }
                events_[count++] = event;
            }
            continue;
        }

        if (isMacroParameter (id))
        {
            const auto pointCount = queue->getPointCount ();
            for (int32 point = 0; point < pointCount; ++point)
            {
                int32 sampleOffset = 0;
                ParamValue value = 0.0;
                if (queue->getPoint (point, sampleOffset, value) != kResultTrue)
                    continue;
                const auto bounded = static_cast<float> (
                    std::clamp (value, 0.0, 1.0));
                macros_[macroIndex (id)].store (bounded,
                                                 std::memory_order_relaxed);
                if (frameCount <= 0 || count >= events_.size ())
                    continue;
                mpvst_event event {};
                event.sample_position = std::clamp<int32> (sampleOffset, 0,
                                                            frameCount - 1);
                event.type = MPVST_EVENT_PARAMETER;
                event.data0 = static_cast<std::int32_t> (macroIndex (id));
                event.value0 = bounded;
                events_[count++] = event;
            }
            continue;
        }

        int32 sampleOffset = 0;
        ParamValue value = 0.0;
        if (queue->getPoint (queue->getPointCount () - 1, sampleOffset, value) !=
            kResultTrue)
            continue;

        if (id == kPatchParameter)
        {
            const auto bounded = std::clamp (value, 0.0, 1.0);
            const auto index = static_cast<std::int32_t> (
                bounded * static_cast<double> (kPatchCount - 1) + 0.5);
            if (frameCount > 0 && count < events_.size ())
            {
                mpvst_event event {};
                event.sample_position = std::clamp<int32> (sampleOffset, 0,
                                                            frameCount - 1);
                event.type = MPVST_EVENT_PROGRAM_CHANGE;
                event.data0 = index;
                event.value0 = static_cast<float> (bounded);
                events_[count++] = event;
            }
        }
        else if (id == kBypassParameter)
        {
            bypass_.store (value >= 0.5 ? 1U : 0U, std::memory_order_relaxed);
        }
        else if (id == kReloadParameter)
        {
            const auto next = value >= 0.5 ? 1U : 0U;
            const auto previous = reloadLatch_.exchange (next,
                                                          std::memory_order_relaxed);
            if (next != 0U && previous == 0U &&
                reloadFadeState_ == ReloadFadeState::Idle)
            {
                reloadFadeState_ = ReloadFadeState::FadingOut;
                fadeSamplesRemaining_ = 128U;
            }
        }
    }
    return count;
}

void Processor::clearOutput (ProcessData& data) noexcept
{
    if (data.numOutputs <= 0 || data.outputs == nullptr)
        return;

    auto& output = data.outputs[0];
    const auto channelCount = output.numChannels;
    for (int32 channel = 0; channel < channelCount; ++channel)
    {
        auto* samples = output.channelBuffers32[channel];
        if (samples != nullptr)
            std::fill_n (samples, data.numSamples, 0.0f);
    }

    output.silenceFlags = channelCount >= 64
        ? static_cast<uint64> (~uint64 {0})
        : (uint64 {1} << static_cast<uint32> (channelCount)) - 1U;
}

std::uint32_t Processor::collectEvents (IEventList* input,
                                        int32 frameCount,
                                        std::uint32_t count) noexcept
{
    if (input == nullptr || frameCount <= 0)
        return count;

    const auto hostCount = input->getEventCount ();
    for (int32 index = 0; index < hostCount && count < events_.size (); ++index)
    {
        Event source {};
        if (input->getEvent (index, source) != kResultTrue || source.busIndex != 0)
            continue;

        mpvst_event event {};
        event.sample_position = std::clamp<int32> (source.sampleOffset, 0,
                                                    frameCount - 1);
        event.flags = source.flags;
        if (source.type == Event::kNoteOnEvent)
        {
            event.type = MPVST_EVENT_NOTE_ON;
            event.channel = static_cast<std::uint16_t> (source.noteOn.channel);
            event.note_id = source.noteOn.noteId;
            event.data0 = source.noteOn.pitch;
            event.value0 = source.noteOn.velocity;
            event.value1 = source.noteOn.tuning;
        }
        else if (source.type == Event::kNoteOffEvent)
        {
            event.type = MPVST_EVENT_NOTE_OFF;
            event.channel = static_cast<std::uint16_t> (source.noteOff.channel);
            event.note_id = source.noteOff.noteId;
            event.data0 = source.noteOff.pitch;
            event.value0 = source.noteOff.velocity;
            event.value1 = source.noteOff.tuning;
        }
        else if (source.type == Event::kPolyPressureEvent)
        {
            event.type = MPVST_EVENT_POLY_PRESSURE;
            event.channel = static_cast<std::uint16_t> (source.polyPressure.channel);
            event.note_id = source.polyPressure.noteId;
            event.data0 = source.polyPressure.pitch;
            event.value0 = source.polyPressure.pressure;
        }
        else
        {
            continue;
        }
        events_[count++] = event;
    }
    return count;
}

void Processor::sortEvents (std::uint32_t count) noexcept
{
    // Insertion sort keeps equal sample positions in submission order, so the
    // macro resynchronisation emitted at position zero stays ahead of any note
    // that starts in the same frame. It also never allocates, which std::sort's
    // stable counterpart does not guarantee in a real-time callback. Host
    // events arrive in ascending order, so the common case is linear.
    for (std::uint32_t index = 1U; index < count; ++index)
    {
        const auto pending = events_[index];
        std::uint32_t position = index;
        while (position > 0U &&
               events_[position - 1U].sample_position > pending.sample_position)
        {
            events_[position] = events_[position - 1U];
            --position;
        }
        events_[position] = pending;
    }
}

SidecarTransport::TransportInfo Processor::readTransport (
    ProcessData& data) noexcept
{
    SidecarTransport::TransportInfo info;
    const auto* context = data.processContext;
    if (context == nullptr)
    {
        // Hosts are allowed to omit the context. Treat that as a stopped
        // transport that never jumps rather than inventing a timeline.
        haveTransport_ = false;
        return info;
    }

    info.playing = (context->state & ProcessContext::kPlaying) != 0U;
    if ((context->state & ProcessContext::kProjectTimeMusicValid) != 0U ||
        (context->state & ProcessContext::kTempoValid) != 0U)
        info.tempoMicroBpm = static_cast<std::uint64_t> (
            std::llround (context->tempo * 1000000.0));
    if ((context->state & ProcessContext::kTimeSigValid) != 0U)
    {
        info.timeSignatureNumerator =
            static_cast<std::uint16_t> (std::max<int32> (context->timeSigNumerator, 1));
        info.timeSignatureDenominator =
            static_cast<std::uint16_t> (std::max<int32> (context->timeSigDenominator, 1));
    }
    info.projectSample = context->projectTimeSamples;

    // A block is continuous with the last one when it starts exactly where the
    // last one ended and the play state has not changed. Anything else is a
    // locate, a loop wrap, or a start/stop, and the script needs to know.
    const bool continuous = haveTransport_ &&
        info.projectSample == expectedProjectSample_ &&
        info.playing == lastPlaying_;
    info.discontinuity = !continuous;

    haveTransport_ = true;
    lastPlaying_ = info.playing;
    expectedProjectSample_ = info.projectSample +
        static_cast<std::int64_t> (data.numSamples);
    return info;
}

std::uint32_t Processor::emitTransportEvent (
    const SidecarTransport::TransportInfo& transport, int32 frameCount,
    std::uint32_t count) noexcept
{
    if (frameCount <= 0 || count >= events_.size ())
        return count;
    mpvst_event event {};
    event.sample_position = 0;
    event.type = MPVST_EVENT_TRANSPORT;
    event.data0 = transport.playing ? 1 : 0;
    event.value0 = sampleRate_ > 0.0
        ? static_cast<float> (static_cast<double> (transport.projectSample) /
                              sampleRate_)
        : 0.0F;
    events_[count++] = event;
    return count;
}

std::uint32_t Processor::emitMacroResync (int32 frameCount,
                                          std::uint32_t count) noexcept
{
    // A freshly loaded script starts from its own defaults and has never seen a
    // parameter change, so the host's macro values and the script's idea of
    // them diverge until the user happens to move a control. Replaying the
    // current values as ordinary parameter events at the head of the block
    // makes an automated, restored, or reloaded instance sound the same as one
    // the user has just touched.
    if (frameCount <= 0)
        return count;

    for (std::size_t index = 0; index < macros_.size (); ++index)
    {
        if (count >= events_.size ())
            break;
        mpvst_event event {};
        event.sample_position = 0;
        event.type = MPVST_EVENT_PARAMETER;
        event.data0 = static_cast<std::int32_t> (index);
        event.value0 = macros_[index].load (std::memory_order_relaxed);
        events_[count++] = event;
    }
    return count;
}

void Processor::publishEngineStatus (IParameterChanges* changes) noexcept
{
    if (changes == nullptr)
        return;
    const auto publish = [changes] (ParamID id, float value, float& previous) {
        if (value == previous)
            return;
        int32 queueIndex = 0;
        auto* queue = changes->addParameterData (id, queueIndex);
        if (queue == nullptr)
            return;
        int32 pointIndex = 0;
        if (queue->addPoint (0, value, pointIndex) == kResultTrue)
            previous = value;
    };
    publish (kEngineReadyParameter, sidecar_.ready () ? 1.0F : 0.0F,
             publishedReady_);
    const auto error = std::min<std::uint32_t> (sidecar_.errorCode (), 255U);
    publish (kEngineErrorParameter, static_cast<float> (error) / 255.0F,
             publishedError_);
}

void Processor::applyReloadFade (float* left, float* right,
                                 std::uint32_t frames) noexcept
{
    constexpr std::uint32_t kFadeSamples = 128U;
    for (std::uint32_t frame = 0U; frame < frames; ++frame)
    {
        float gain = 1.0F;
        if (reloadFadeState_ == ReloadFadeState::FadingOut)
        {
            gain = static_cast<float> (fadeSamplesRemaining_) /
                   static_cast<float> (kFadeSamples);
            if (fadeSamplesRemaining_ > 0U)
                --fadeSamplesRemaining_;
            if (fadeSamplesRemaining_ == 0U)
            {
                (void)sidecar_.requestReload ();
                // The engine drains commands before it consumes the next work
                // slot, so events submitted from the following block reach the
                // reloaded script rather than the outgoing one.
                macroResyncPending_.store (1U, std::memory_order_relaxed);
                reloadFadeState_ = ReloadFadeState::Holding;
                holdSamplesRemaining_ = sidecar_.latencySamples () +
                                        configuredMaxFrames_;
            }
        }
        else if (reloadFadeState_ == ReloadFadeState::Holding)
        {
            gain = 0.0F;
            if (holdSamplesRemaining_ > 0U)
                --holdSamplesRemaining_;
            if (holdSamplesRemaining_ == 0U)
            {
                reloadFadeState_ = ReloadFadeState::FadingIn;
                fadeSamplesRemaining_ = kFadeSamples;
            }
        }
        else if (reloadFadeState_ == ReloadFadeState::FadingIn)
        {
            gain = 1.0F - static_cast<float> (fadeSamplesRemaining_) /
                              static_cast<float> (kFadeSamples);
            if (fadeSamplesRemaining_ > 0U)
                --fadeSamplesRemaining_;
            if (fadeSamplesRemaining_ == 0U)
                reloadFadeState_ = ReloadFadeState::Idle;
        }
        left[frame] *= gain;
        right[frame] *= gain;
    }
}

tresult PLUGIN_API Processor::process (ProcessData& data)
{
    if (data.symbolicSampleSize != kSample32)
        return kResultFalse;

    // Hosts may process in place, so the input bus has to be captured before
    // the output buffers are cleared.
    const float* stagedInputLeft = nullptr;
    const float* stagedInputRight = nullptr;
    if (effectMode_ && data.numSamples > 0 && data.numInputs > 0 &&
        data.inputs != nullptr && data.inputs[0].numChannels >= 2 &&
        data.inputs[0].channelBuffers32[0] != nullptr &&
        data.inputs[0].channelBuffers32[1] != nullptr &&
        static_cast<std::size_t> (data.numSamples) <= inputStagingLeft_.size ())
    {
        std::copy_n (data.inputs[0].channelBuffers32[0], data.numSamples,
                     inputStagingLeft_.data ());
        std::copy_n (data.inputs[0].channelBuffers32[1], data.numSamples,
                     inputStagingRight_.data ());
        stagedInputLeft = inputStagingLeft_.data ();
        stagedInputRight = inputStagingRight_.data ();
    }

    clearOutput (data);
    const auto transport = readTransport (data);
    std::uint32_t eventCount = 0U;
    if (transport.discontinuity)
        eventCount = emitTransportEvent (transport, data.numSamples, eventCount);
    if (macroResyncPending_.load (std::memory_order_relaxed) != 0U &&
        sidecar_.ready () && data.numSamples > 0)
    {
        eventCount = emitMacroResync (data.numSamples, eventCount);
        macroResyncPending_.store (0U, std::memory_order_relaxed);
    }
    eventCount = collectEvents (data.inputEvents, data.numSamples, eventCount);
    eventCount = collectParameterChanges (data.inputParameterChanges,
                                          data.numSamples, eventCount);
    sortEvents (eventCount);
    if (data.numOutputs > 0 && data.outputs != nullptr &&
        data.outputs[0].numChannels >= 2 &&
        data.outputs[0].channelBuffers32[0] != nullptr &&
        data.outputs[0].channelBuffers32[1] != nullptr)
    {
        const auto bypassed = bypass_.load (std::memory_order_relaxed) != 0U;
        const auto wroteNonSilent = sidecar_.process (
            data.outputs[0].channelBuffers32[0],
            data.outputs[0].channelBuffers32[1],
            static_cast<uint32> (data.numSamples),
            bypassed,
            events_.data (), eventCount, data.processMode == kOffline,
            &transport, stagedInputLeft, stagedInputRight);
        if (effectMode_ && !bypassDelayLeft_.empty ())
        {
            // The dry signal runs through a delay matched to the reported
            // pipeline latency at all times, so engaging bypass swaps to a
            // time-aligned pass-through instead of jumping the audio earlier
            // by the plug-in's own latency.
            const auto latency = std::min<std::uint32_t> (
                sidecar_.latencySamples (),
                static_cast<std::uint32_t> (bypassDelayLeft_.size ()));
            auto* outLeft = data.outputs[0].channelBuffers32[0];
            auto* outRight = data.outputs[0].channelBuffers32[1];
            bool bypassWroteNonSilent = false;
            for (int32 frame = 0; frame < data.numSamples; ++frame)
            {
                const float dryLeft = stagedInputLeft != nullptr
                    ? stagedInputLeft[frame] : 0.0F;
                const float dryRight = stagedInputRight != nullptr
                    ? stagedInputRight[frame] : 0.0F;
                float delayedLeft = dryLeft;
                float delayedRight = dryRight;
                if (latency != 0U)
                {
                    delayedLeft = bypassDelayLeft_[bypassDelayIndex_];
                    delayedRight = bypassDelayRight_[bypassDelayIndex_];
                    bypassDelayLeft_[bypassDelayIndex_] = dryLeft;
                    bypassDelayRight_[bypassDelayIndex_] = dryRight;
                    bypassDelayIndex_ = bypassDelayIndex_ + 1U == latency
                        ? 0U : bypassDelayIndex_ + 1U;
                }
                if (bypassed)
                {
                    outLeft[frame] = delayedLeft;
                    outRight[frame] = delayedRight;
                    bypassWroteNonSilent = bypassWroteNonSilent ||
                        delayedLeft != 0.0F || delayedRight != 0.0F;
                }
            }
            if (bypassWroteNonSilent)
                data.outputs[0].silenceFlags = 0U;
        }
        applyReloadFade (data.outputs[0].channelBuffers32[0],
                         data.outputs[0].channelBuffers32[1],
                         static_cast<uint32> (data.numSamples));
        if (wroteNonSilent)
            data.outputs[0].silenceFlags = 0U;
    }
    publishEngineStatus (data.outputParameterChanges);
    return kResultOk;
}

tresult PLUGIN_API Processor::setState (IBStream* state)
{
    if (state == nullptr)
        return kResultFalse;

    IBStreamer stream (state, kLittleEndian);
    int32 version = 0;
    int32 bypass = 0;
    if (!stream.readInt32 (version) ||
        (version != kLegacyStateVersion && version != kStateVersion) ||
        !stream.readInt32 (bypass))
        return kResultFalse;

    std::array<float, kMacroParameterCount> values {};
    for (auto& value : values)
    {
        if (!stream.readFloat (value))
            return kResultFalse;
    }

    int32 pipelineBlocks = kDefaultPipelineBlocks;
    std::string scriptSource = scriptSource_;
    if (version >= kStateVersion)
    {
        int32 scriptBytes = 0;
        if (!stream.readInt32 (pipelineBlocks) ||
            pipelineBlocks < 1 || pipelineBlocks > kMaximumPipelineBlocks ||
            !stream.readInt32 (scriptBytes) || scriptBytes < 0 ||
            scriptBytes > kMaximumEmbeddedScriptBytes)
            return kResultFalse;
        scriptSource.resize (static_cast<std::size_t> (scriptBytes));
        if (scriptBytes != 0 &&
            stream.readRaw (scriptSource.data(), scriptBytes) != scriptBytes)
            return kResultFalse;
    }

    bypass_.store (bypass != 0 ? 1U : 0U, std::memory_order_relaxed);
    for (std::size_t index = 0; index < values.size (); ++index)
        macros_[index].store (std::clamp (values[index], 0.0f, 1.0f),
                              std::memory_order_relaxed);
    pipelineBlocks_ = pipelineBlocks;
    scriptSource_ = std::move (scriptSource);
    macroResyncPending_.store (1U, std::memory_order_relaxed);
    if (active_.load (std::memory_order_relaxed) != 0U)
        sidecar_.stop ();
    sidecar_.setScriptSource (scriptSource_);
    if (active_.load (std::memory_order_relaxed) != 0U)
        (void)sidecar_.start ();
    return kResultOk;
}

tresult PLUGIN_API Processor::getState (IBStream* state)
{
    if (state == nullptr)
        return kResultFalse;

    // Saving is the moment the project takes its own copy of the script, so an
    // instance that follows a developer file embeds what is on disk now rather
    // than what it happened to read when it was created.
    scriptSource_ = sidecar_.refreshDeveloperScriptSource ();

    IBStreamer stream (state, kLittleEndian);
    if (!stream.writeInt32 (kStateVersion) ||
        !stream.writeInt32 (bypass_.load (std::memory_order_relaxed) != 0 ? 1 : 0))
        return kResultFalse;

    for (const auto& value : macros_)
    {
        if (!stream.writeFloat (value.load (std::memory_order_relaxed)))
            return kResultFalse;
    }
    if (scriptSource_.size () >
        static_cast<std::size_t> (kMaximumEmbeddedScriptBytes) ||
        !stream.writeInt32 (pipelineBlocks_) ||
        !stream.writeInt32 (static_cast<int32> (scriptSource_.size ())) ||
        (!scriptSource_.empty () &&
         stream.writeRaw (scriptSource_.data (),
                          static_cast<TSize> (scriptSource_.size ())) !=
             static_cast<TSize> (scriptSource_.size ())))
        return kResultFalse;
    return kResultOk;
}

} // namespace PyDevices::MicroPythonVST3
