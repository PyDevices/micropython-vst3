#include "public.sdk/source/common/memorystream.h"
#include "base/source/fstreamer.h"
#include "public.sdk/source/vst/hosting/eventlist.h"
#include "public.sdk/source/vst/hosting/hostclasses.h"
#include "public.sdk/source/vst/hosting/module.h"
#include "public.sdk/source/vst/hosting/parameterchanges.h"

#include "pluginterfaces/vst/ivstaudioprocessor.h"
#include "pluginterfaces/vst/ivstcomponent.h"
#include "pluginterfaces/vst/ivsteditcontroller.h"
#include "pluginterfaces/base/ustring.h"

#include <array>
#include <chrono>
#include <cmath>
#include <cstring>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <thread>

namespace {

using namespace Steinberg;
using namespace Steinberg::Vst;
using VST3::Hosting::ClassInfo;
using VST3::Hosting::Module;
using VST3::Hosting::PluginFactory;

bool ok(tresult result) { return result == kResultOk || result == kResultTrue; }

bool selectBundledEngine(const std::filesystem::path& bundle)
{
#if defined(_WIN32)
    const auto wanted = "micropython-vst-engine.exe";
#else
    const auto wanted = "micropython-vst-engine";
#endif
    for (const auto& entry : std::filesystem::recursive_directory_iterator(bundle))
    {
        if (entry.is_regular_file() && entry.path().filename() == wanted)
        {
#if defined(_WIN32)
            return _putenv_s("MPVST_ENGINE_PATH", entry.path().string().c_str()) == 0;
#else
            return setenv("MPVST_ENGINE_PATH", entry.path().string().c_str(), 1) == 0;
#endif
        }
    }
    return false;
}

void setScriptPath(const std::string& path)
{
#if defined(_WIN32)
    (void)_putenv_s("MPVST_SCRIPT_PATH", path.c_str());
#else
    if (path.empty())
        (void)unsetenv("MPVST_SCRIPT_PATH");
    else
        (void)setenv("MPVST_SCRIPT_PATH", path.c_str(), 1);
#endif
}

IPtr<IComponent> createComponent(const PluginFactory& factory,
                                 const ClassInfo& classInfo,
                                 FUnknown* host)
{
    auto component = factory.createInstance<IComponent>(classInfo.ID());
    if (!component || !ok(component->initialize(host)))
        return nullptr;
    return component;
}

IPtr<IAudioProcessor> getProcessor(IComponent* component)
{
    IAudioProcessor* raw = nullptr;
    if (component == nullptr ||
        !ok(component->queryInterface(IAudioProcessor::iid,
                                      reinterpret_cast<void**>(&raw))))
        return nullptr;
    return owned(raw);
}

const ClassInfo* findAudioClass(const PluginFactory& factory,
                                ClassInfo& selected)
{
    for (const auto& classInfo : factory.classInfos())
    {
        if (classInfo.category() == kVstAudioEffectClass)
        {
            selected = classInfo;
            return &selected;
        }
    }
    return nullptr;
}

const ClassInfo* findAudioClassNamed(const PluginFactory& factory,
                                     const std::string& name,
                                     ClassInfo& selected)
{
    for (const auto& classInfo : factory.classInfos())
    {
        if (classInfo.category() == kVstAudioEffectClass &&
            classInfo.name() == name)
        {
            selected = classInfo;
            return &selected;
        }
    }
    return nullptr;
}

bool stateRoundTrip(const PluginFactory& factory, const ClassInfo& classInfo,
                    FUnknown* host)
{
    auto original = createComponent(factory, classInfo, host);
    if (!original)
        return false;
    MemoryStream snapshot;
    if (!ok(original->getState(&snapshot)) || snapshot.getSize() == 0U)
        return false;
    const auto snapshotSize = snapshot.getSize();
    std::string expected(snapshot.getData(), snapshot.getData() + snapshotSize);
    original->terminate();
    original = nullptr;

    auto restored = createComponent(factory, classInfo, host);
    if (!restored)
        return false;
    snapshot.seek(0, IBStream::kIBSeekSet, nullptr);
    if (!ok(restored->setState(&snapshot)))
        return false;
    MemoryStream verification;
    if (!ok(restored->getState(&verification)) ||
        verification.getSize() != snapshotSize ||
        std::memcmp(expected.data(), verification.getData(),
                    static_cast<std::size_t>(snapshotSize)) != 0)
        return false;

    MemoryStream legacyState;
    IBStreamer legacyWriter(&legacyState, kLittleEndian);
    if (!legacyWriter.writeInt32(1) || !legacyWriter.writeInt32(0))
        return false;
    for (int index = 0; index < 16; ++index)
    {
        if (!legacyWriter.writeFloat(0.5F))
            return false;
    }
    legacyState.seek(0, IBStream::kIBSeekSet, nullptr);
    if (!ok(restored->setState(&legacyState)))
        return false;

    MemoryStream emptyState;
    if (ok(restored->setState(&emptyState)))
        return false;

    const auto writeV2Prefix = [] (MemoryStream& target) {
        IBStreamer writer(&target, kLittleEndian);
        if (!writer.writeInt32(2) || !writer.writeInt32(0))
            return false;
        for (int index = 0; index < 16; ++index)
        {
            if (!writer.writeFloat(0.5F))
                return false;
        }
        return true;
    };
    MemoryStream invalidPipeline;
    if (!writeV2Prefix(invalidPipeline))
        return false;
    IBStreamer invalidPipelineWriter(&invalidPipeline, kLittleEndian);
    invalidPipelineWriter.seek(0, kSeekEnd);
    if (!invalidPipelineWriter.writeInt32(0) ||
        !invalidPipelineWriter.writeInt32(0))
        return false;
    invalidPipeline.seek(0, IBStream::kIBSeekSet, nullptr);
    if (ok(restored->setState(&invalidPipeline)))
        return false;

    MemoryStream oversizedScript;
    if (!writeV2Prefix(oversizedScript))
        return false;
    IBStreamer oversizedWriter(&oversizedScript, kLittleEndian);
    oversizedWriter.seek(0, kSeekEnd);
    if (!oversizedWriter.writeInt32(4) ||
        !oversizedWriter.writeInt32(1024 * 1024 + 1))
        return false;
    oversizedScript.seek(0, IBStream::kIBSeekSet, nullptr);
    if (ok(restored->setState(&oversizedScript)))
        return false;

    MemoryStream truncatedScript;
    if (!writeV2Prefix(truncatedScript))
        return false;
    IBStreamer truncatedWriter(&truncatedScript, kLittleEndian);
    truncatedWriter.seek(0, kSeekEnd);
    if (!truncatedWriter.writeInt32(4) || !truncatedWriter.writeInt32(8) ||
        truncatedWriter.writeRaw("short", 5) != 5)
        return false;
    truncatedScript.seek(0, IBStream::kIBSeekSet, nullptr);
    if (ok(restored->setState(&truncatedScript)))
        return false;
    restored->terminate();
    return true;
}

bool processLifecycle(const PluginFactory& factory, const ClassInfo& classInfo,
                      FUnknown* host, bool expectMicroPython)
{
#if defined(_WIN32)
    (void)_putenv_s("MPVST_NATIVE_TEST_TONE", "");
    (void)_putenv_s("MPVST_NATIVE_EVENT_GATE", expectMicroPython ? "" : "1");
#else
    (void)unsetenv("MPVST_NATIVE_TEST_TONE");
    if (expectMicroPython)
        (void)unsetenv("MPVST_NATIVE_EVENT_GATE");
    else
        (void)setenv("MPVST_NATIVE_EVENT_GATE", "1", 1);
#endif
    auto component = createComponent(factory, classInfo, host);
    auto processor = getProcessor(component);
    if (!component || !processor)
        return false;

    SpeakerArrangement stereo = SpeakerArr::kStereo;
    ProcessSetup setup {};
    setup.processMode = kRealtime;
    setup.symbolicSampleSize = kSample32;
    setup.maxSamplesPerBlock = 128;
    setup.sampleRate = 48000.0;
    const auto require = [](tresult result, const char* step) {
        if (!ok(result))
            std::cerr << "HOOK lifecycle." << step << " FAIL: " << result << '\n';
        return ok(result);
    };
    if (!require(processor->setBusArrangements(nullptr, 0, &stereo, 1),
                 "arrangements") ||
        !require(component->activateBus(kAudio, kOutput, 0, true), "audio_bus") ||
        !require(component->activateBus(kEvent, kInput, 0, true), "event_bus") ||
        !require(processor->setupProcessing(setup), "setup") ||
        !require(component->setActive(true), "activate") ||
        !require(processor->setProcessing(true), "start_processing"))
        return false;

    std::array<float, 128> left {};
    std::array<float, 128> right {};
    Sample32* channels[] = {left.data(), right.data()};
    AudioBusBuffers output {};
    output.numChannels = 2;
    output.channelBuffers32 = channels;
    ProcessData data {};
    data.processMode = kRealtime;
    data.symbolicSampleSize = kSample32;
    data.numSamples = static_cast<int32>(left.size());
    data.numOutputs = 1;
    data.outputs = &output;
    EventList inputEvents;
    Event noteOn {};
    Event noteOff {};
    const auto midiChannel = expectMicroPython ? 0 : 3;
    noteOn.busIndex = 0;
    noteOn.sampleOffset = 64;
    noteOn.type = Event::kNoteOnEvent;
    noteOn.noteOn.channel = midiChannel;
    noteOn.noteOn.pitch = 57;
    noteOn.noteOn.velocity = 1.0F;
    noteOn.noteOn.noteId = 1;
    (void)inputEvents.addEvent(noteOn);
    data.inputEvents = &inputEvents;

    noteOff.busIndex = 0;
    noteOff.sampleOffset = 32;
    noteOff.type = Event::kNoteOffEvent;
    noteOff.noteOff.channel = midiChannel;
    noteOff.noteOff.pitch = 57;
    noteOff.noteOff.velocity = 0.0F;
    noteOff.noteOff.noteId = 1;

    ParameterChanges parameterChanges {1};
    ParameterChanges outputChanges {2};
    data.outputParameterChanges = &outputChanges;
    bool sawEngineReady = false;
    bool heardTone = false;
    int firstAudibleSample = -1;
    bool havePreviousSample = false;
    float previousSample = 0.0F;
    int zeroCrossings = 0;
    int lastAudibleSample = -1;
    const auto blockCount = expectMicroPython ? 96 : 12;
    for (int block = 0; block < blockCount; ++block)
    {
        if (block == 6)
        {
            inputEvents.clear();
            (void)inputEvents.addEvent(noteOff);
            data.inputEvents = &inputEvents;
        }
        if (!expectMicroPython && block == 2)
        {
            constexpr ParamID pitchBendChannel3 = 0x10000U + 3U * 256U + 129U;
            int32 queueIndex = 0;
            int32 pointIndex = 0;
            auto* queue = parameterChanges.addParameterData (pitchBendChannel3,
                                                              queueIndex);
            if (queue == nullptr ||
                queue->addPoint (0, 1.0, pointIndex) != kResultTrue)
                return false;
            data.inputParameterChanges = &parameterChanges;
        }
        if (!expectMicroPython && block == 4)
        {
            constexpr ParamID macro01 = 100U;
            int32 queueIndex = 0;
            int32 pointIndex = 0;
            auto* queue = parameterChanges.addParameterData (macro01, queueIndex);
            if (queue == nullptr ||
                queue->addPoint (17, 0.75, pointIndex) != kResultTrue)
                return false;
            data.inputParameterChanges = &parameterChanges;
        }
        if (!require(processor->process(data), "process"))
            return false;
        for (int32 queueIndex = 0;
             queueIndex < outputChanges.getParameterCount(); ++queueIndex)
        {
            auto* queue = outputChanges.getParameterData(queueIndex);
            if (queue == nullptr || queue->getPointCount() == 0)
                continue;
            int32 sampleOffset = 0;
            ParamValue value = 0.0;
            if (queue->getParameterId() == 2U &&
                queue->getPoint(queue->getPointCount() - 1, sampleOffset, value) ==
                    kResultTrue && value >= 1.0)
                sawEngineReady = true;
        }
        outputChanges.clearQueue();
        if (block == 0 || block == 6)
        {
            inputEvents.clear();
            data.inputEvents = nullptr;
        }
        if (!expectMicroPython && (block == 2 || block == 4))
        {
            parameterChanges.clearQueue ();
            data.inputParameterChanges = nullptr;
        }
        for (std::size_t frame = 0; frame < left.size(); ++frame)
        {
            const auto sample = left[frame];
            if (!std::isfinite(sample))
                return false;
            if (std::abs(sample) > 0.000001F)
            {
                heardTone = true;
                if (firstAudibleSample < 0)
                    firstAudibleSample = block * data.numSamples +
                                         static_cast<int> (frame);
                lastAudibleSample = block * data.numSamples +
                                    static_cast<int> (frame);
            }
            if (block < 4 && sample != 0.0F)
            {
                std::cerr << "HOOK latency.initial_silence FAIL\n";
                return false;
            }
            if (expectMicroPython && block == 4 && frame < 64U && sample != 0.0F)
            {
                std::cerr << "HOOK midi.sample_offset FAIL: early sample="
                          << frame << '\n';
                return false;
            }
            if (!expectMicroPython)
            {
                const auto absoluteSample = block * data.numSamples +
                                            static_cast<int> (frame);
                const auto expected = absoluteSample < 576 ? 0.0F
                    : absoluteSample < 768 ? 0.125F
                    : absoluteSample < 1041 ? 0.25F
                    : absoluteSample < 1312 ? 0.1875F
                    : 0.0F;
                if (std::abs(sample - expected) > 0.000001F)
                {
                    std::cerr << "HOOK midi.pitch_bend FAIL: sample="
                              << absoluteSample << " expected=" << expected
                              << " actual=" << sample << '\n';
                    return false;
                }
            }
            const auto absoluteSample = block * data.numSamples +
                                        static_cast<int> (frame);
            if (block >= 4 && absoluteSample < 1312 &&
                std::abs(sample) > 0.000001F)
            {
                if (havePreviousSample &&
                    ((previousSample < 0.0F && sample >= 0.0F) ||
                     (previousSample > 0.0F && sample <= 0.0F)))
                    ++zeroCrossings;
                previousSample = sample;
                havePreviousSample = true;
            }
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(4));
    }

    if (!heardTone || !sawEngineReady || processor->getLatencySamples() != 512U)
    {
        std::cerr << "HOOK latency.fixed_pipeline FAIL: zero_crossings="
                  << zeroCrossings << '\n';
        return false;
    }
    std::cout << "HOOK latency.fixed_pipeline OK: 512 samples\n";
    std::cout << "HOOK engine.status_parameter OK: ready=1 error=0\n";
    if (expectMicroPython)
    {
        // The note-on at offset 64 must emerge at 512 + 64 after the fixed
        // pipeline. A native fallback ignores it, so audible 220 Hz output
        // also proves the event reached the Python synthio graph.
        if (zeroCrossings < 5 || zeroCrossings > 9 ||
            firstAudibleSample < 576 || firstAudibleSample > 580)
        {
            std::cerr << "HOOK engine.micropython_synthio FAIL: "
                      << "zero_crossings=" << zeroCrossings
                      << " first_audible=" << firstAudibleSample << '\n';
            return false;
        }
        std::cout << "HOOK engine.micropython_synthio OK: zero_crossings="
                  << zeroCrossings << '\n';
        std::cout << "HOOK midi.sample_offset OK: first_audible="
                  << firstAudibleSample << '\n';
        // Note-off is submitted in block 6 at offset 32, so it reaches Python
        // at sample 1312 after latency. The default voice's explicit 50 ms
        // release must continue past that boundary and finish within the run.
        if (lastAudibleSample <= 1312 || lastAudibleSample >= 5000)
        {
            std::cerr << "HOOK midi.note_off_tail FAIL: last_audible="
                      << lastAudibleSample << '\n';
            return false;
        }
        std::cout << "HOOK midi.note_off_tail OK: event_sample=1312"
                  << " last_audible=" << lastAudibleSample << '\n';
    }
    else
    {
        std::cout << "HOOK midi.pitch_bend OK: channel=3 event_sample=768\n";
        std::cout << "HOOK macro.sample_offset OK: macro=1 event_sample=1041\n";
    }

    const bool stopped = ok(processor->setProcessing(false)) &&
                         ok(component->setActive(false));
    processor = nullptr;
    const bool terminated = ok(component->terminate());
    component = nullptr;
    return stopped && terminated;
}

bool embeddedStateSurvivesMissingSource(const PluginFactory& factory,
                                        const ClassInfo& classInfo,
                                        FUnknown* host)
{
    const auto unique = std::chrono::steady_clock::now().time_since_epoch().count();
    const auto sourcePath = std::filesystem::temp_directory_path() /
        ("mpvst-state-source-" + std::to_string(unique) + ".py");
    constexpr const char* source =
        "# mpvst-macro-labels: Gain | Tone\n"
        "import synthio\n"
        "import vstaudio\n"
        "synth = synthio.Synthesizer(sample_rate=vstaudio.sample_rate(), "
        "channel_count=2)\n"
        "synth.press(synthio.Note(330.0))\n"
        "vstaudio.output(synth)\n";
    {
        std::ofstream output(sourcePath, std::ios::binary | std::ios::trunc);
        if (!output || !output.write(source, static_cast<std::streamsize>(
                                               std::strlen(source))))
            return false;
    }
    setScriptPath(sourcePath.string());

    auto original = createComponent(factory, classInfo, host);
    MemoryStream snapshot;
    if (!original || !ok(original->getState(&snapshot)) ||
        snapshot.getSize() <= static_cast<int64>(std::strlen(source)))
    {
        setScriptPath({});
        std::error_code ignored;
        (void)std::filesystem::remove(sourcePath, ignored);
        return false;
    }
    (void)original->terminate();
    original = nullptr;

    std::error_code removeError;
    const auto removed = std::filesystem::remove(sourcePath, removeError);
    setScriptPath({});
    if (!removed || removeError || std::filesystem::exists(sourcePath))
        return false;

    auto restored = createComponent(factory, classInfo, host);
    if (!restored)
        return false;
    snapshot.seek(0, IBStream::kIBSeekSet, nullptr);
    if (!ok(restored->setState(&snapshot)))
        return false;

    TUID controllerCID {};
    if (!ok(restored->getControllerClassId(controllerCID)))
        return false;
    auto controller = factory.createInstance<IEditController>(VST3::UID(controllerCID));
    if (!controller || !ok(controller->initialize(host)))
        return false;
    snapshot.seek(0, IBStream::kIBSeekSet, nullptr);
    if (!ok(controller->setComponentState(&snapshot)))
        return false;
    ParameterInfo macroInfo {};
    bool foundGain = false;
    for (int32 index = 0; index < controller->getParameterCount(); ++index)
    {
        if (controller->getParameterInfo(index, macroInfo) == kResultTrue &&
            macroInfo.id == 100U)
        {
            std::array<char, 128> title {};
            UString(macroInfo.title, str16BufferSize(macroInfo.title))
                .toAscii(title.data(), static_cast<int32>(title.size()));
            foundGain = std::string {title.data()} == "Gain";
            break;
        }
    }
    (void)controller->terminate();
    controller = nullptr;
    if (!foundGain)
        return false;
    auto processor = getProcessor(restored);
    if (!processor)
        return false;

    SpeakerArrangement stereo = SpeakerArr::kStereo;
    ProcessSetup setup {};
    setup.processMode = kRealtime;
    setup.symbolicSampleSize = kSample32;
    setup.maxSamplesPerBlock = 128;
    setup.sampleRate = 48000.0;
    if (!ok(processor->setBusArrangements(nullptr, 0, &stereo, 1)) ||
        !ok(restored->activateBus(kAudio, kOutput, 0, true)) ||
        !ok(processor->setupProcessing(setup)) ||
        !ok(restored->setActive(true)) ||
        !ok(processor->setProcessing(true)))
        return false;

    std::array<float, 128> left {};
    std::array<float, 128> right {};
    Sample32* channels[] = {left.data(), right.data()};
    AudioBusBuffers output {};
    output.numChannels = 2;
    output.channelBuffers32 = channels;
    ProcessData data {};
    data.processMode = kRealtime;
    data.symbolicSampleSize = kSample32;
    data.numSamples = static_cast<int32>(left.size());
    data.numOutputs = 1;
    data.outputs = &output;
    bool heard = false;
    for (int block = 0; block < 16; ++block)
    {
        if (!ok(processor->process(data)))
            return false;
        if (block >= 4)
        {
            for (const auto sample : left)
                heard = heard || std::abs(sample) > 0.000001F;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(4));
    }

    const bool stopped = ok(processor->setProcessing(false)) &&
                         ok(restored->setActive(false));
    processor = nullptr;
    const bool terminated = ok(restored->terminate());
    restored = nullptr;
    return heard && stopped && terminated;
}

// Renders a fixed script with a fixed event sequence and writes raw float32
// PCM. Running this on Windows and on Linux and comparing the two files is the
// cross-platform parity check: same script, same state, same events, same
// samples.
bool renderReference(const PluginFactory& factory, const ClassInfo& classInfo,
                     FUnknown* host, const std::string& outputPath)
{
    const auto sourcePath = std::filesystem::temp_directory_path() /
        "mpvst-reference-instrument.py";
    // synthio rather than a constant, so any difference in the audio path
    // between the two platforms shows up in the samples.
    constexpr const char* source =
        "import synthio\n"
        "import vstaudio\n"
        "synth = synthio.Synthesizer(sample_rate=vstaudio.sample_rate(), "
        "channel_count=2)\n"
        "envelope = synthio.Envelope(attack_time=0.01, decay_time=0.05,\n"
        "                            release_time=0.1, attack_level=1.0,\n"
        "                            sustain_level=0.7)\n"
        "voices = {}\n"
        "def handle_event(event_type, channel, note_id, data0, value0, value1,\n"
        "                 sample_position):\n"
        "    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:\n"
        "        note = synthio.Note(synthio.midi_to_hz(data0),\n"
        "                            amplitude=value0, envelope=envelope)\n"
        "        voices[data0] = note\n"
        "        synth.press(note)\n"
        "    elif event_type == vstaudio.EVENT_NOTE_OFF:\n"
        "        note = voices.pop(data0, None)\n"
        "        if note is not None:\n"
        "            synth.release(note)\n"
        "vstaudio.on_event(handle_event)\n"
        "vstaudio.output(synth)\n";
    {
        std::ofstream out(sourcePath, std::ios::binary | std::ios::trunc);
        if (!out || !out.write(source, static_cast<std::streamsize>(
                                           std::strlen(source))))
            return false;
    }
    setScriptPath(sourcePath.string());

    auto component = createComponent(factory, classInfo, host);
    auto processor = getProcessor(component);
    if (!component || !processor)
        return false;

    SpeakerArrangement stereo = SpeakerArr::kStereo;
    ProcessSetup setup {};
    setup.processMode = kOffline;
    setup.symbolicSampleSize = kSample32;
    setup.maxSamplesPerBlock = 128;
    setup.sampleRate = 48000.0;
    if (!ok(processor->setBusArrangements(nullptr, 0, &stereo, 1)) ||
        !ok(component->activateBus(kAudio, kOutput, 0, true)) ||
        !ok(component->activateBus(kEvent, kInput, 0, true)) ||
        !ok(processor->setupProcessing(setup)) ||
        !ok(component->setActive(true)) ||
        !ok(processor->setProcessing(true)))
        return false;

    std::array<float, 128> left {};
    std::array<float, 128> right {};
    Sample32* channels[] = {left.data(), right.data()};
    AudioBusBuffers output {};
    output.numChannels = 2;
    output.channelBuffers32 = channels;
    ProcessContext context {};
    context.state = ProcessContext::kPlaying | ProcessContext::kTempoValid;
    context.sampleRate = 48000.0;
    context.tempo = 120.0;
    context.projectTimeSamples = 0;
    ProcessData data {};
    data.processMode = kOffline;
    data.symbolicSampleSize = kSample32;
    data.numSamples = static_cast<int32>(left.size());
    data.numOutputs = 1;
    data.outputs = &output;
    data.processContext = &context;

    // A fixed score: three notes pressed and released at known blocks.
    struct Step { int block; bool on; int16 pitch; };
    const Step score[] = {
        {8, true, 60},  {16, true, 64},  {24, true, 67},
        {40, false, 60}, {48, false, 64}, {56, false, 67},
    };
    constexpr int kBlockCount = 96;

    std::ofstream pcm(outputPath, std::ios::binary | std::ios::trunc);
    if (!pcm)
        return false;

    EventList events;
    for (int block = 0; block < kBlockCount; ++block)
    {
        events.clear();
        for (const auto& step : score)
        {
            if (step.block != block)
                continue;
            Event event {};
            event.busIndex = 0;
            event.sampleOffset = 0;
            if (step.on)
            {
                event.type = Event::kNoteOnEvent;
                event.noteOn.channel = 0;
                event.noteOn.pitch = step.pitch;
                event.noteOn.velocity = 0.8F;
                event.noteOn.noteId = step.pitch;
            }
            else
            {
                event.type = Event::kNoteOffEvent;
                event.noteOff.channel = 0;
                event.noteOff.pitch = step.pitch;
                event.noteOff.velocity = 0.0F;
                event.noteOff.noteId = step.pitch;
            }
            (void)events.addEvent(event);
        }
        data.inputEvents = events.getEventCount() > 0 ? &events : nullptr;
        if (!ok(processor->process(data)))
            return false;
        context.projectTimeSamples += static_cast<int32>(left.size());
        pcm.write(reinterpret_cast<const char*>(left.data()),
                  static_cast<std::streamsize>(left.size() * sizeof(float)));
        pcm.write(reinterpret_cast<const char*>(right.data()),
                  static_cast<std::streamsize>(right.size() * sizeof(float)));
    }
    pcm.close();

    const bool stopped = ok(processor->setProcessing(false)) &&
                         ok(component->setActive(false));
    processor = nullptr;
    const bool terminated = ok(component->terminate());
    component = nullptr;
    setScriptPath({});
    std::error_code ignored;
    (void)std::filesystem::remove(sourcePath, ignored);
    return stopped && terminated;
}

// Runs the effect class with the real MicroPython engine and a script that
// simply plays the host input back: vstaudio.output(vstaudio.input()). Every
// output sample must equal the input sample from one pipeline latency
// earlier, to within the int16 quantisation the script-side audio path uses.
bool effectCase(const PluginFactory& factory, const ClassInfo& classInfo,
                FUnknown* host, const char* source, int32 blockFrames,
                float gain, float tolerance)
{
    const auto sourcePath = std::filesystem::temp_directory_path() /
        "mpvst-effect-case.py";
    {
        std::ofstream out(sourcePath, std::ios::binary | std::ios::trunc);
        if (!out || !out.write(source, static_cast<std::streamsize>(
                                           std::strlen(source))))
            return false;
    }
    setScriptPath(sourcePath.string());

    auto component = createComponent(factory, classInfo, host);
    auto processor = getProcessor(component);
    if (!component || !processor)
        return false;

    SpeakerArrangement stereo = SpeakerArr::kStereo;
    ProcessSetup setup {};
    setup.processMode = kOffline;
    setup.symbolicSampleSize = kSample32;
    setup.maxSamplesPerBlock = blockFrames;
    setup.sampleRate = 48000.0;
    if (!ok(processor->setBusArrangements(&stereo, 1, &stereo, 1)) ||
        !ok(component->activateBus(kAudio, kInput, 0, true)) ||
        !ok(component->activateBus(kAudio, kOutput, 0, true)) ||
        !ok(component->activateBus(kEvent, kInput, 0, true)) ||
        !ok(processor->setupProcessing(setup)) ||
        !ok(component->setActive(true)) ||
        !ok(processor->setProcessing(true)))
        return false;

    const auto kFrames = static_cast<std::uint32_t>(blockFrames);
    const std::uint32_t kLatency = kFrames * 4U;
    const int kBlockCount = static_cast<int>(8192U / kFrames) + 8;
    std::vector<float> sentLeft;
    std::vector<float> sentRight;
    std::vector<float> heardLeft;
    std::vector<float> heardRight;

    std::vector<float> inLeft(kFrames);
    std::vector<float> inRight(kFrames);
    std::vector<float> outLeft(kFrames);
    std::vector<float> outRight(kFrames);
    Sample32* inChannels[] = {inLeft.data(), inRight.data()};
    Sample32* outChannels[] = {outLeft.data(), outRight.data()};
    AudioBusBuffers inputBus {};
    inputBus.numChannels = 2;
    inputBus.channelBuffers32 = inChannels;
    AudioBusBuffers outputBus {};
    outputBus.numChannels = 2;
    outputBus.channelBuffers32 = outChannels;
    ProcessData data {};
    data.processMode = kOffline;
    data.symbolicSampleSize = kSample32;
    data.numSamples = static_cast<int32>(kFrames);
    data.numInputs = 1;
    data.inputs = &inputBus;
    data.numOutputs = 1;
    data.outputs = &outputBus;

    for (int block = 0; block < kBlockCount; ++block)
    {
        for (std::uint32_t frame = 0U; frame < kFrames; ++frame)
        {
            const auto sample =
                static_cast<std::uint32_t>(block) * kFrames + frame;
            const auto value = (static_cast<float>((sample * 7U) % 256U) -
                                128.0F) / 512.0F;
            inLeft[frame] = value;
            inRight[frame] = -0.5F * value;
            sentLeft.push_back(inLeft[frame]);
            sentRight.push_back(inRight[frame]);
        }
        if (!ok(processor->process(data)))
            return false;
        heardLeft.insert(heardLeft.end(), outLeft.begin(), outLeft.end());
        heardRight.insert(heardRight.end(), outRight.begin(), outRight.end());
    }

    const bool stopped = ok(processor->setProcessing(false)) &&
                         ok(component->setActive(false));
    processor = nullptr;
    const bool terminated = ok(component->terminate());
    component = nullptr;
    setScriptPath({});
    std::error_code ignored;
    (void)std::filesystem::remove(sourcePath, ignored);
    if (!stopped || !terminated)
        return false;

    // A script chain may buffer internally (an audiomixer voice prefetches a
    // silent chunk before the first host block arrives), so the stream can
    // lag the pipeline latency by a bounded extra amount. Find the actual
    // alignment, then require a full match at that shift.
    const std::uint32_t kMaxExtra = 2048U;
    for (std::uint32_t shift = kLatency; shift <= kLatency + kMaxExtra;
         ++shift)
    {
        bool matched = true;
        for (std::size_t sample = shift; sample < heardLeft.size(); ++sample)
        {
            const auto expectedLeft = sentLeft[sample - shift] * gain;
            const auto expectedRight = sentRight[sample - shift] * gain;
            if (std::abs(heardLeft[sample] - expectedLeft) > tolerance ||
                std::abs(heardRight[sample] - expectedRight) > tolerance)
            {
                matched = false;
                break;
            }
        }
        if (matched)
        {
            std::cerr << "effect aligned at shift " << shift << " (block="
                      << blockFrames << " gain=" << gain << ")\n";
            return true;
        }
    }
    std::cerr << "effect audio never aligned (block=" << blockFrames
              << " gain=" << gain << ")\n";
    return false;
}

bool effectProcessesHostAudio(const PluginFactory& factory,
                              const ClassInfo& classInfo, FUnknown* host)
{
    // Direct pass-through at a small block size, then an audiomixer chain at
    // a DAW-typical 512-frame block: the second shape is exactly what the
    // REAPER matrix runs.
    constexpr const char* passthrough =
        "import vstaudio\n"
        "vstaudio.output(vstaudio.input())\n";
    constexpr const char* mixerHalf =
        "import audiomixer\n"
        "import vstaudio\n"
        "mixer = audiomixer.Mixer(voice_count=1,\n"
        "                         sample_rate=vstaudio.sample_rate(),\n"
        "                         channel_count=2, bits_per_sample=16,\n"
        "                         samples_signed=True, buffer_size=1024)\n"
        "mixer.voice[0].play(vstaudio.input())\n"
        "mixer.voice[0].level = 0.5\n"
        "vstaudio.output(mixer)\n";
    if (!effectCase(factory, classInfo, host, passthrough, 128, 1.0F,
                    0.0001F))
        return false;
    std::cerr << "case passthrough@128 ok\n";
    if (!effectCase(factory, classInfo, host, passthrough, 512, 1.0F,
                    0.0001F))
        return false;
    std::cerr << "case passthrough@512 ok\n";
    if (!effectCase(factory, classInfo, host, mixerHalf, 128, 0.5F, 0.002F))
        return false;
    std::cerr << "case mixer@128 ok\n";
    return effectCase(factory, classInfo, host, mixerHalf, 512, 0.5F,
                      0.002F);
}

// Runs an arbitrary effect script from a file at a DAW-typical 512-frame
// block, feeding a 220 Hz sine that is quiet for the first half and loud for
// the second, and reports the output RMS of each half so a caller can assert
// per-effect behaviour (a compressor squeezes the loud half, a gate mutes
// the quiet one, a filter passes both, ...).
bool effectScriptProbe(const PluginFactory& factory,
                       const ClassInfo& classInfo, FUnknown* host,
                       const std::string& scriptPath)
{
    setScriptPath(scriptPath);
    auto component = createComponent(factory, classInfo, host);
    auto processor = getProcessor(component);
    if (!component || !processor)
        return false;

    SpeakerArrangement stereo = SpeakerArr::kStereo;
    ProcessSetup setup {};
    setup.processMode = kOffline;
    setup.symbolicSampleSize = kSample32;
    setup.maxSamplesPerBlock = 512;
    setup.sampleRate = 48000.0;
    if (!ok(processor->setBusArrangements(&stereo, 1, &stereo, 1)) ||
        !ok(component->activateBus(kAudio, kInput, 0, true)) ||
        !ok(component->activateBus(kAudio, kOutput, 0, true)) ||
        !ok(component->activateBus(kEvent, kInput, 0, true)) ||
        !ok(processor->setupProcessing(setup)) ||
        !ok(component->setActive(true)) ||
        !ok(processor->setProcessing(true)))
        return false;

    constexpr std::uint32_t kFrames = 512U;
    constexpr int kBlockCount = 128;           // 64k samples ~ 1.37 s
    constexpr std::uint32_t kHalf = kFrames * kBlockCount / 2U;
    std::vector<float> heard;
    heard.reserve(kFrames * kBlockCount);

    std::vector<float> inLeft(kFrames);
    std::vector<float> inRight(kFrames);
    std::vector<float> outLeft(kFrames);
    std::vector<float> outRight(kFrames);
    Sample32* inChannels[] = {inLeft.data(), inRight.data()};
    Sample32* outChannels[] = {outLeft.data(), outRight.data()};
    AudioBusBuffers inputBus {};
    inputBus.numChannels = 2;
    inputBus.channelBuffers32 = inChannels;
    AudioBusBuffers outputBus {};
    outputBus.numChannels = 2;
    outputBus.channelBuffers32 = outChannels;
    ProcessData data {};
    data.processMode = kOffline;
    data.symbolicSampleSize = kSample32;
    data.numSamples = static_cast<int32>(kFrames);
    data.numInputs = 1;
    data.inputs = &inputBus;
    data.numOutputs = 1;
    data.outputs = &outputBus;

    constexpr double twoPi = 6.283185307179586476925286766559;
    for (int block = 0; block < kBlockCount; ++block)
    {
        for (std::uint32_t frame = 0U; frame < kFrames; ++frame)
        {
            const auto sample =
                static_cast<std::uint32_t>(block) * kFrames + frame;
            const float amp = sample < kHalf ? 0.02F : 0.5F;
            const auto value = amp * static_cast<float>(
                std::sin(twoPi * 220.0 * sample / 48000.0));
            inLeft[frame] = value;
            inRight[frame] = value;
        }
        if (!ok(processor->process(data)))
            return false;
        heard.insert(heard.end(), outLeft.begin(), outLeft.end());
    }

    const bool stopped = ok(processor->setProcessing(false)) &&
                         ok(component->setActive(false));
    processor = nullptr;
    const bool terminated = ok(component->terminate());
    component = nullptr;
    setScriptPath({});
    if (!stopped || !terminated)
        return false;

    const auto rmsOf = [&heard](std::uint32_t begin, std::uint32_t end) {
        double acc = 0.0;
        for (std::uint32_t sample = begin; sample < end; ++sample)
            acc += static_cast<double>(heard[sample]) * heard[sample];
        return std::sqrt(acc / (end - begin));
    };
    // Skip pipeline latency plus generous chain-priming/settling headroom at
    // the start of each half.
    const auto quiet = rmsOf(8192U, kHalf);
    const auto loud = rmsOf(kHalf + 8192U, kFrames * kBlockCount);
    std::cout << "EFFECT_RMS quiet_in=0.014142 loud_in=0.353553 quiet_out="
              << quiet << " loud_out=" << loud << '\n';
    return true;
}

// Loads an arbitrary instrument script (e.g. one of lib/instruments/*.py)
// into the real MicroPython Instrument class and sweeps every one of its 16
// macros through 0.0/0.5/1.0 while pressing and releasing notes across a
// wide pitch range. Reports whether the sidecar ever raised (kEngineError
// going non-zero -- exactly how the ring_mod=/scale= API-misuse crashes
// surfaced) and whether the script produced any audible output at all.
bool instrumentScriptProbe(const PluginFactory& factory,
                           const ClassInfo& classInfo, FUnknown* host,
                           const std::string& scriptPath)
{
    setScriptPath(scriptPath);
    auto component = createComponent(factory, classInfo, host);
    auto processor = getProcessor(component);
    if (!component || !processor)
    {
        setScriptPath({});
        return false;
    }

    SpeakerArrangement stereo = SpeakerArr::kStereo;
    ProcessSetup setup {};
    setup.processMode = kOffline;
    setup.symbolicSampleSize = kSample32;
    setup.maxSamplesPerBlock = 256;
    setup.sampleRate = 48000.0;
    if (!ok(processor->setBusArrangements(nullptr, 0, &stereo, 1)) ||
        !ok(component->activateBus(kAudio, kOutput, 0, true)) ||
        !ok(component->activateBus(kEvent, kInput, 0, true)) ||
        !ok(processor->setupProcessing(setup)) ||
        !ok(component->setActive(true)) ||
        !ok(processor->setProcessing(true)))
    {
        setScriptPath({});
        return false;
    }

    std::array<float, 256> left {};
    std::array<float, 256> right {};
    Sample32* channels[] = {left.data(), right.data()};
    AudioBusBuffers output {};
    output.numChannels = 2;
    output.channelBuffers32 = channels;
    ProcessContext context {};
    context.state = ProcessContext::kPlaying | ProcessContext::kTempoValid;
    context.sampleRate = 48000.0;
    context.tempo = 120.0;
    ProcessData data {};
    data.processMode = kOffline;
    data.symbolicSampleSize = kSample32;
    data.numSamples = static_cast<int32>(left.size());
    data.numOutputs = 1;
    data.outputs = &output;
    data.processContext = &context;

    EventList events;
    ParameterChanges macroChange {1};
    ParameterChanges outputChanges {4};
    data.outputParameterChanges = &outputChanges;

    double peak = 0.0;
    int engineErrorCode = 0;
    bool sawReady = false;
    const int16 pitches[] = {24, 36, 48, 60, 67, 72, 84, 96};
    const float macroSettings[] = {0.0F, 0.5F, 1.0F};

    const auto pumpBlocks = [&](int count) {
        for (int i = 0; i < count && engineErrorCode == 0; ++i)
        {
            if (!ok(processor->process(data)))
            {
                engineErrorCode = -1;
                return;
            }
            data.inputEvents = nullptr;
            data.inputParameterChanges = nullptr;
            for (int32 queueIndex = 0;
                 queueIndex < outputChanges.getParameterCount(); ++queueIndex)
            {
                auto* queue = outputChanges.getParameterData(queueIndex);
                if (queue == nullptr || queue->getPointCount() == 0)
                    continue;
                int32 sampleOffset = 0;
                ParamValue value = 0.0;
                if (queue->getPoint(queue->getPointCount() - 1, sampleOffset,
                                     value) != kResultTrue)
                    continue;
                if (queue->getParameterId() == 2U && value >= 1.0)
                    sawReady = true;
                if (queue->getParameterId() == 3U)
                {
                    const auto code =
                        static_cast<int>(value * 255.0 + 0.5);
                    if (code != 0)
                        engineErrorCode = code;
                }
            }
            outputChanges.clearQueue();
            for (auto sample : left)
                peak = std::max(peak, static_cast<double>(std::abs(sample)));
            for (auto sample : right)
                peak = std::max(peak, static_cast<double>(std::abs(sample)));
            context.projectTimeSamples += data.numSamples;
        }
    };

    for (std::size_t settingIndex = 0;
         settingIndex < 3 && engineErrorCode == 0; ++settingIndex)
    {
        for (std::size_t macroIdx = 0;
             macroIdx < 16 && engineErrorCode == 0; ++macroIdx)
        {
            const ParamID id = 100U + static_cast<ParamID>(macroIdx);
            int32 queueIndex = 0;
            int32 pointIndex = 0;
            auto* queue = macroChange.addParameterData(id, queueIndex);
            if (queue == nullptr ||
                queue->addPoint(0, macroSettings[settingIndex], pointIndex) !=
                    kResultTrue)
            {
                engineErrorCode = -1;
                break;
            }
            data.inputParameterChanges = &macroChange;

            const auto pitch = pitches[macroIdx % 8];
            events.clear();
            Event noteOn {};
            noteOn.busIndex = 0;
            noteOn.sampleOffset = 0;
            noteOn.type = Event::kNoteOnEvent;
            noteOn.noteOn.channel = 0;
            noteOn.noteOn.pitch = pitch;
            noteOn.noteOn.velocity = 0.8F;
            noteOn.noteOn.noteId = pitch;
            (void)events.addEvent(noteOn);
            data.inputEvents = &events;

            pumpBlocks(16);
            macroChange.clearQueue();

            events.clear();
            Event noteOff {};
            noteOff.busIndex = 0;
            noteOff.sampleOffset = 0;
            noteOff.type = Event::kNoteOffEvent;
            noteOff.noteOff.channel = 0;
            noteOff.noteOff.pitch = pitch;
            noteOff.noteOff.velocity = 0.0F;
            noteOff.noteOff.noteId = pitch;
            (void)events.addEvent(noteOff);
            data.inputEvents = &events;
            pumpBlocks(12);
        }
    }

    const bool stopped = ok(processor->setProcessing(false)) &&
                         ok(component->setActive(false));
    processor = nullptr;
    const bool terminated = ok(component->terminate());
    component = nullptr;
    setScriptPath({});

    std::cout << "INSTRUMENT_PROBE ready=" << (sawReady ? 1 : 0)
              << " error=" << engineErrorCode << " peak=" << peak << '\n';
    return stopped && terminated && sawReady && engineErrorCode == 0 &&
          peak > 0.0005;
}

// Sets the Patch parameter (ParamID 4, the same one a host maps an
// incoming MIDI Program Change onto, since VST3 has no native
// program-change input event) to two different program indices and
// checks the script actually received MPVST_EVENT_PROGRAM_CHANGE with
// the right data0 both times, via a continuously-held note whose
// amplitude the script sets directly from the program index.
bool patchSelectDeliversProgramChange(const PluginFactory& factory,
                                      const ClassInfo& classInfo,
                                      FUnknown* host)
{
    const auto sourcePath = std::filesystem::temp_directory_path() /
        "mpvst-patch-select.py";
    constexpr const char* source =
        "import synthio\n"
        "import vstaudio\n"
        "synth = synthio.Synthesizer(sample_rate=vstaudio.sample_rate(), "
        "channel_count=2)\n"
        "vstaudio.output(synth)\n"
        "note = synthio.Note(220.0, amplitude=0.0)\n"
        "synth.press(note)\n"
        "def handle_event(event_type, channel, note_id, data0, value0, "
        "value1, sample_position):\n"
        "    if event_type == vstaudio.EVENT_PROGRAM_CHANGE:\n"
        "        note.amplitude = data0 / 127.0\n"
        "vstaudio.on_event(handle_event)\n";
    {
        std::ofstream out(sourcePath, std::ios::binary | std::ios::trunc);
        if (!out || !out.write(source, static_cast<std::streamsize>(
                                           std::strlen(source))))
            return false;
    }
    setScriptPath(sourcePath.string());

    auto component = createComponent(factory, classInfo, host);
    auto processor = getProcessor(component);
    if (!component || !processor)
    {
        setScriptPath({});
        return false;
    }

    SpeakerArrangement stereo = SpeakerArr::kStereo;
    ProcessSetup setup {};
    setup.processMode = kOffline;
    setup.symbolicSampleSize = kSample32;
    setup.maxSamplesPerBlock = 256;
    setup.sampleRate = 48000.0;
    if (!ok(processor->setBusArrangements(nullptr, 0, &stereo, 1)) ||
        !ok(component->activateBus(kAudio, kOutput, 0, true)) ||
        !ok(component->activateBus(kEvent, kInput, 0, true)) ||
        !ok(processor->setupProcessing(setup)) ||
        !ok(component->setActive(true)) ||
        !ok(processor->setProcessing(true)))
    {
        setScriptPath({});
        return false;
    }

    std::array<float, 256> left {};
    std::array<float, 256> right {};
    Sample32* channels[] = {left.data(), right.data()};
    AudioBusBuffers output {};
    output.numChannels = 2;
    output.channelBuffers32 = channels;
    ProcessData data {};
    data.processMode = kOffline;
    data.symbolicSampleSize = kSample32;
    data.numSamples = static_cast<int32>(left.size());
    data.numOutputs = 1;
    data.outputs = &output;

    constexpr ParamID kPatchParameter = 4;
    constexpr int kPatchCount = 128;

    // Give the sidecar time to boot before sending anything meaningful:
    // engine startup takes a handful of blocks, and events sent before it
    // reaches LIFECYCLE_RUNNING are not guaranteed to be consumed.
    ParameterChanges statusOut {2};
    data.outputParameterChanges = &statusOut;
    bool sawReady = false;
    int errorCode = 0;
    const auto pollStatus = [&] {
        for (int32 queueIndex = 0;
             queueIndex < statusOut.getParameterCount(); ++queueIndex)
        {
            auto* queue = statusOut.getParameterData(queueIndex);
            if (queue == nullptr || queue->getPointCount() == 0)
                continue;
            int32 sampleOffset = 0;
            ParamValue value = 0.0;
            if (queue->getPoint(queue->getPointCount() - 1, sampleOffset,
                                 value) != kResultTrue)
                continue;
            if (queue->getParameterId() == 2U && value >= 1.0)
                sawReady = true;
            if (queue->getParameterId() == 3U)
                errorCode = static_cast<int>(value * 255.0 + 0.5);
        }
        statusOut.clearQueue();
    };
    for (int block = 0; block < 64; ++block)
    {
        if (!ok(processor->process(data)))
            return false;
        pollStatus();
    }

    // The shared-memory pipeline buffers several blocks deep (see
    // Processor::getLatencySamples), so a parameter change submitted now
    // doesn't reach the rendered output until that many samples later.
    const auto latencyBlocks =
        static_cast<int>(processor->getLatencySamples() / left.size()) + 4;

    const auto rmsAtProgram = [&](int program) -> double {
        ParameterChanges patchChange {1};
        int32 queueIndex = 0;
        int32 pointIndex = 0;
        auto* queue = patchChange.addParameterData(kPatchParameter, queueIndex);
        const auto normalized =
            static_cast<ParamValue>(program) / static_cast<ParamValue>(kPatchCount - 1);
        if (queue == nullptr ||
            queue->addPoint(0, normalized, pointIndex) != kResultTrue)
            return -1.0;
        data.inputParameterChanges = &patchChange;
        if (!ok(processor->process(data)))
            return -1.0;
        data.inputParameterChanges = nullptr;

        for (int block = 0; block < latencyBlocks; ++block)
        {
            if (!ok(processor->process(data)))
                return -1.0;
            pollStatus();
        }

        double acc = 0.0;
        for (int block = 0; block < 4; ++block)
        {
            if (!ok(processor->process(data)))
                return -1.0;
            pollStatus();
            for (auto sample : left)
                acc += static_cast<double>(sample) * sample;
        }
        return std::sqrt(acc / (4 * left.size()));
    };

    const auto rmsLow = rmsAtProgram(16);
    const auto rmsHigh = rmsAtProgram(112);
    data.outputParameterChanges = nullptr;

    const bool stopped = ok(processor->setProcessing(false)) &&
                         ok(component->setActive(false));
    processor = nullptr;
    const bool terminated = ok(component->terminate());
    component = nullptr;
    setScriptPath({});
    std::error_code ignored;
    (void)std::filesystem::remove(sourcePath, ignored);

    std::cout << "PATCH_SELECT ready=" << (sawReady ? 1 : 0)
              << " error=" << errorCode << " rms_at_16=" << rmsLow
              << " rms_at_112=" << rmsHigh << '\n';
    // amplitude scales linearly with program index, so RMS should too
    // (within a comfortable margin for the one-block parameter-apply
    // delay and float32 quantisation).
    const auto expectedRatio = 112.0 / 16.0;
    const auto actualRatio = rmsLow > 1e-6 ? rmsHigh / rmsLow : -1.0;
    return stopped && terminated && sawReady && errorCode == 0 &&
          rmsLow > 0.0 && rmsHigh > rmsLow &&
          std::abs(actualRatio - expectedRatio) < expectedRatio * 0.25;
}

bool transportDiscontinuityGatesVoices(const PluginFactory& factory,
                                       const ClassInfo& classInfo,
                                       FUnknown* host)
{
    // The native engine closes its gate on a transport discontinuity, so a
    // locate while a note is held must silence the instrument even though no
    // note-off was sent. Without discontinuity detection the note would sustain
    // straight through the jump.
#if defined(_WIN32)
    (void)_putenv_s("MPVST_NATIVE_EVENT_GATE", "1");
#else
    (void)setenv("MPVST_NATIVE_EVENT_GATE", "1", 1);
#endif
    auto component = createComponent(factory, classInfo, host);
    auto processor = getProcessor(component);
    if (!component || !processor)
        return false;

    SpeakerArrangement stereo = SpeakerArr::kStereo;
    ProcessSetup setup {};
    setup.processMode = kRealtime;
    setup.symbolicSampleSize = kSample32;
    setup.maxSamplesPerBlock = 128;
    setup.sampleRate = 48000.0;
    if (!ok(processor->setBusArrangements(nullptr, 0, &stereo, 1)) ||
        !ok(component->activateBus(kAudio, kOutput, 0, true)) ||
        !ok(component->activateBus(kEvent, kInput, 0, true)) ||
        !ok(processor->setupProcessing(setup)) ||
        !ok(component->setActive(true)) ||
        !ok(processor->setProcessing(true)))
        return false;

    std::array<float, 128> left {};
    std::array<float, 128> right {};
    Sample32* channels[] = {left.data(), right.data()};
    AudioBusBuffers output {};
    output.numChannels = 2;
    output.channelBuffers32 = channels;

    ProcessContext context {};
    context.state = ProcessContext::kPlaying | ProcessContext::kTempoValid;
    context.sampleRate = 48000.0;
    context.tempo = 120.0;
    context.projectTimeSamples = 0;

    ProcessData data {};
    data.processMode = kRealtime;
    data.symbolicSampleSize = kSample32;
    data.numSamples = static_cast<int32>(left.size());
    data.numOutputs = 1;
    data.outputs = &output;
    data.processContext = &context;

    constexpr int kNoteBlock = 8;
    constexpr int kJumpBlock = 20;
    constexpr int kBlockCount = 32;
    constexpr int kLatency = 512;
    const int blockFrames = static_cast<int>(left.size());

    EventList events;
    bool heardBeforeJump = false;
    bool silentAfterJump = true;
    for (int block = 0; block < kBlockCount; ++block)
    {
        if (block == kNoteBlock)
        {
            Event noteOn {};
            noteOn.busIndex = 0;
            noteOn.sampleOffset = 0;
            noteOn.type = Event::kNoteOnEvent;
            noteOn.noteOn.channel = 0;
            noteOn.noteOn.pitch = 60;
            noteOn.noteOn.velocity = 1.0F;
            noteOn.noteOn.noteId = 1;
            (void)events.addEvent(noteOn);
            data.inputEvents = &events;
        }
        if (block == kJumpBlock)
        {
            // Locate backwards, the way a loop wrap or a rewind looks.
            context.projectTimeSamples = 0;
        }
        if (!ok(processor->process(data)))
            return false;
        if (block == kNoteBlock)
        {
            events.clear();
            data.inputEvents = nullptr;
        }
        if (block != kJumpBlock)
            context.projectTimeSamples += blockFrames;

        const int firstSample = block * blockFrames;
        for (std::size_t frame = 0; frame < left.size(); ++frame)
        {
            const auto sample = firstSample + static_cast<int>(frame);
            const bool audible = std::abs(left[frame]) > 0.000001F;
            if (sample >= kNoteBlock * blockFrames + kLatency &&
                sample < kJumpBlock * blockFrames + kLatency)
                heardBeforeJump = heardBeforeJump || audible;
            // Allow the pipeline that was already in flight to drain.
            if (sample >= (kJumpBlock + 1) * blockFrames + kLatency && audible)
                silentAfterJump = false;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(4));
    }

    const bool stopped = ok(processor->setProcessing(false)) &&
                         ok(component->setActive(false));
    processor = nullptr;
    const bool terminated = ok(component->terminate());
    component = nullptr;
    if (!heardBeforeJump)
    {
        std::cerr << "HOOK transport.discontinuity FAIL: note never sounded\n";
        return false;
    }
    if (!silentAfterJump)
    {
        std::cerr << "HOOK transport.discontinuity FAIL: note survived the jump\n";
        return false;
    }
    return stopped && terminated;
}

bool macroResyncAppliesRestoredState(const PluginFactory& factory,
                                     const ClassInfo& classInfo, FUnknown* host)
{
    // A restored instance must sound the way the saved project sounded. The
    // script starts from its own defaults and never sees a parameter change on
    // this path, so without a resynchronisation the restored macro value is
    // silently ignored until the user moves the control.
#if defined(_WIN32)
    (void)_putenv_s("MPVST_NATIVE_EVENT_GATE", "1");
#else
    (void)setenv("MPVST_NATIVE_EVENT_GATE", "1", 1);
#endif

    auto original = createComponent(factory, classInfo, host);
    if (!original)
        return false;
    MemoryStream snapshot;
    if (!ok(original->getState(&snapshot)))
        return false;
    (void)original->terminate();
    original = nullptr;

    // State is int32 version, int32 bypass, then the sixteen macro floats, so
    // Macro 01 begins at byte eight. Raising it to full scale makes the native
    // engine's gate level 0.25 instead of its 0.125 default.
    constexpr int64 kMacroOffset = 8;
    if (snapshot.getSize() < kMacroOffset + static_cast<int64>(sizeof(float)))
        return false;
    const float fullScale = 1.0F;
    std::memcpy(snapshot.getData() + kMacroOffset, &fullScale, sizeof(fullScale));

    auto restored = createComponent(factory, classInfo, host);
    auto processor = getProcessor(restored);
    if (!restored || !processor)
        return false;
    snapshot.seek(0, IBStream::kIBSeekSet, nullptr);
    if (!ok(restored->setState(&snapshot)))
        return false;

    SpeakerArrangement stereo = SpeakerArr::kStereo;
    ProcessSetup setup {};
    setup.processMode = kRealtime;
    setup.symbolicSampleSize = kSample32;
    setup.maxSamplesPerBlock = 128;
    setup.sampleRate = 48000.0;
    if (!ok(processor->setBusArrangements(nullptr, 0, &stereo, 1)) ||
        !ok(restored->activateBus(kAudio, kOutput, 0, true)) ||
        !ok(restored->activateBus(kEvent, kInput, 0, true)) ||
        !ok(processor->setupProcessing(setup)) ||
        !ok(restored->setActive(true)) ||
        !ok(processor->setProcessing(true)))
        return false;

    std::array<float, 128> left {};
    std::array<float, 128> right {};
    Sample32* channels[] = {left.data(), right.data()};
    AudioBusBuffers output {};
    output.numChannels = 2;
    output.channelBuffers32 = channels;
    ProcessData data {};
    data.processMode = kRealtime;
    data.symbolicSampleSize = kSample32;
    data.numSamples = static_cast<int32>(left.size());
    data.numOutputs = 1;
    data.outputs = &output;

    // The note starts well after the engine reports ready so the resynchronised
    // macro is already in effect for every audible sample.
    constexpr int kNoteBlock = 12;
    constexpr int kBlockCount = 28;
    constexpr int kLatency = 512;
    const int noteInputSample = kNoteBlock * static_cast<int>(left.size());
    const int firstAudibleSample = noteInputSample + kLatency;

    EventList events;
    for (int block = 0; block < kBlockCount; ++block)
    {
        if (block == kNoteBlock)
        {
            Event noteOn {};
            noteOn.busIndex = 0;
            noteOn.sampleOffset = 0;
            noteOn.type = Event::kNoteOnEvent;
            noteOn.noteOn.channel = 0;
            noteOn.noteOn.pitch = 60;
            noteOn.noteOn.velocity = 1.0F;
            noteOn.noteOn.noteId = 1;
            (void)events.addEvent(noteOn);
            data.inputEvents = &events;
        }
        if (!ok(processor->process(data)))
            return false;
        if (block == kNoteBlock)
        {
            events.clear();
            data.inputEvents = nullptr;
        }
        for (std::size_t frame = 0; frame < left.size(); ++frame)
        {
            const auto sample = block * static_cast<int>(left.size()) +
                                static_cast<int>(frame);
            const float expected = sample >= firstAudibleSample ? 0.25F : 0.0F;
            if (std::abs(left[frame] - expected) > 0.000001F)
            {
                std::cerr << "HOOK macro.resync FAIL: sample=" << sample
                          << " expected=" << expected
                          << " actual=" << left[frame] << '\n';
                return false;
            }
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(4));
    }

    const bool stopped = ok(processor->setProcessing(false)) &&
                         ok(restored->setActive(false));
    processor = nullptr;
    const bool terminated = ok(restored->terminate());
    restored = nullptr;
    return stopped && terminated;
}

bool reloadFadeLifecycle(const PluginFactory& factory, const ClassInfo& classInfo,
                         FUnknown* host)
{
#if defined(_WIN32)
    (void)_putenv_s("MPVST_NATIVE_EVENT_GATE", "1");
#else
    (void)setenv("MPVST_NATIVE_EVENT_GATE", "1", 1);
#endif
    auto component = createComponent(factory, classInfo, host);
    auto processor = getProcessor(component);
    if (!component || !processor)
        return false;

    SpeakerArrangement stereo = SpeakerArr::kStereo;
    ProcessSetup setup {};
    setup.processMode = kRealtime;
    setup.symbolicSampleSize = kSample32;
    setup.maxSamplesPerBlock = 128;
    setup.sampleRate = 48000.0;
    if (!ok(processor->setBusArrangements(nullptr, 0, &stereo, 1)) ||
        !ok(component->activateBus(kAudio, kOutput, 0, true)) ||
        !ok(component->activateBus(kEvent, kInput, 0, true)) ||
        !ok(processor->setupProcessing(setup)) ||
        !ok(component->setActive(true)) ||
        !ok(processor->setProcessing(true)))
        return false;

    std::array<float, 128> left {};
    std::array<float, 128> right {};
    Sample32* channels[] = {left.data(), right.data()};
    AudioBusBuffers output {};
    output.numChannels = 2;
    output.channelBuffers32 = channels;
    ProcessData data {};
    data.processMode = kRealtime;
    data.symbolicSampleSize = kSample32;
    data.numSamples = static_cast<int32>(left.size());
    data.numOutputs = 1;
    data.outputs = &output;

    EventList events;
    Event noteOn {};
    noteOn.busIndex = 0;
    noteOn.sampleOffset = 0;
    noteOn.type = Event::kNoteOnEvent;
    noteOn.noteOn.channel = 0;
    noteOn.noteOn.pitch = 60;
    noteOn.noteOn.velocity = 1.0F;
    noteOn.noteOn.noteId = 1;
    (void)events.addEvent(noteOn);
    data.inputEvents = &events;
    ParameterChanges reloadChanges {1};

    for (int block = 0; block < 14; ++block)
    {
        if (block == 5)
        {
            int32 queueIndex = 0;
            int32 pointIndex = 0;
            auto* queue = reloadChanges.addParameterData(1U, queueIndex);
            if (queue == nullptr ||
                queue->addPoint(0, 1.0, pointIndex) != kResultTrue)
                return false;
            data.inputParameterChanges = &reloadChanges;
        }
        if (!ok(processor->process(data)))
            return false;
        if (block == 0)
        {
            events.clear();
            data.inputEvents = nullptr;
        }
        if (block == 5)
        {
            reloadChanges.clearQueue();
            data.inputParameterChanges = nullptr;
        }
        for (std::size_t frame = 0; frame < left.size(); ++frame)
        {
            const auto sample = block * 128 + static_cast<int>(frame);
            float expected = 0.0F;
            if (sample >= 512 && sample < 640)
                expected = 0.125F;
            else if (sample >= 640 && sample < 768)
                expected = 0.125F * static_cast<float>(768 - sample) / 128.0F;
            else if (sample >= 1408 && sample < 1536)
                expected = 0.125F * static_cast<float>(sample - 1408) / 128.0F;
            else if (sample >= 1536)
                expected = 0.125F;
            if (std::abs(left[frame] - expected) > 0.000001F)
            {
                std::cerr << "HOOK reload.fade FAIL: sample=" << sample
                          << " expected=" << expected
                          << " actual=" << left[frame] << '\n';
                return false;
            }
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(4));
    }

    const bool stopped = ok(processor->setProcessing(false)) &&
                         ok(component->setActive(false));
    processor = nullptr;
    const bool terminated = ok(component->terminate());
    component = nullptr;
    return stopped && terminated;
}

} // namespace

int main(int argc, char** argv)
{
    const std::string mode = argc >= 3 ? argv[2] : "";
    const std::string modeArgument = argc >= 4 ? argv[3] : "";
    const bool renderMode = mode == "--render-reference";
    const bool scriptProbe = mode == "--effect-script";
    const bool instrumentProbe = mode == "--instrument-script";
    if (argc < 2 || argc > 4 ||
        ((renderMode || scriptProbe || instrumentProbe) && modeArgument.empty()) ||
        (!renderMode && !scriptProbe && !instrumentProbe && argc > 3) ||
        (!mode.empty() && mode != "--expect-micropython" &&
         mode != "--expect-embedded-state" && mode != "--expect-reload-fade" &&
         mode != "--expect-macro-resync" && mode != "--expect-transport" &&
         mode != "--expect-effect-audio" && mode != "--expect-patch-select" &&
         mode != "--effect-script" && mode != "--instrument-script" &&
         !renderMode))
    {
        std::cerr << "usage: mpvst_smoke_host <plugin.vst3> "
                     "[--expect-micropython|--expect-embedded-state|"
                     "--expect-reload-fade|--expect-macro-resync|"
                     "--expect-transport|--expect-effect-audio|"
                     "--expect-patch-select|"
                     "--effect-script <script.py>|"
                     "--instrument-script <script.py>|"
                     "--render-reference <out.pcm>]\n";
        return 2;
    }
    const bool embeddedState = mode == "--expect-embedded-state";
    const bool reloadFade = mode == "--expect-reload-fade";
    const bool macroResync = mode == "--expect-macro-resync";
    const bool transportMode = mode == "--expect-transport";
    const bool effectMode = mode == "--expect-effect-audio";
    const bool patchSelectMode = mode == "--expect-patch-select";
    const bool expectMicroPython = mode == "--expect-micropython" ||
                                   embeddedState || renderMode ||
                                   effectMode || scriptProbe || instrumentProbe ||
                                   patchSelectMode;

    std::string error;
    const auto modulePath = std::filesystem::weakly_canonical(argv[1]).string();
    if (!selectBundledEngine(modulePath))
    {
        std::cerr << "HOOK engine.select FAIL\n";
        return 3;
    }
    auto module = Module::create(modulePath, error);
    if (!module)
    {
        std::cerr << "HOOK module.load FAIL: " << error << '\n';
        return 3;
    }
    std::cout << "HOOK module.load OK\n";

    {
        auto host = owned(new HostApplication);
        const auto factory = module->getFactory();
        factory.setHostContext(host);
        ClassInfo classInfo;
        if (findAudioClass(factory, classInfo) == nullptr)
        {
            std::cerr << "HOOK class.scan FAIL\n";
            return 4;
        }
        std::cout << "HOOK class.scan OK: " << classInfo.name() << '\n';

        if (renderMode)
        {
            if (!renderReference(factory, classInfo, host, modeArgument))
            {
                std::cerr << "HOOK render.reference FAIL\n";
                return 5;
            }
            std::cout << "HOOK render.reference OK: " << modeArgument << '\n';
        }
        else if (effectMode)
        {
            ClassInfo effectInfo;
            if (findAudioClassNamed(factory, "MicroPython Effect",
                                    effectInfo) == nullptr)
            {
                std::cerr << "HOOK effect.scan FAIL\n";
                return 5;
            }
            if (!effectProcessesHostAudio(factory, effectInfo, host))
            {
                std::cerr << "HOOK effect.audio FAIL\n";
                return 5;
            }
            std::cout << "HOOK effect.audio OK: 4 script/block cases aligned\n";
        }
        else if (scriptProbe)
        {
            ClassInfo effectInfo;
            if (findAudioClassNamed(factory, "MicroPython Effect",
                                    effectInfo) == nullptr)
            {
                std::cerr << "HOOK effect.scan FAIL\n";
                return 5;
            }
            if (!effectScriptProbe(factory, effectInfo, host, modeArgument))
            {
                std::cerr << "HOOK effect.script FAIL\n";
                return 5;
            }
            std::cout << "HOOK effect.script OK\n";
        }
        else if (instrumentProbe)
        {
            if (!instrumentScriptProbe(factory, classInfo, host, modeArgument))
            {
                std::cerr << "HOOK instrument.script FAIL\n";
                return 5;
            }
            std::cout << "HOOK instrument.script OK\n";
        }
        else if (patchSelectMode)
        {
            if (!patchSelectDeliversProgramChange(factory, classInfo, host))
            {
                std::cerr << "HOOK patch.select FAIL\n";
                return 5;
            }
            std::cout << "HOOK patch.select OK\n";
        }
        else if (transportMode)
        {
            if (!transportDiscontinuityGatesVoices(factory, classInfo, host))
            {
                std::cerr << "HOOK transport.discontinuity FAIL\n";
                return 5;
            }
            std::cout << "HOOK transport.discontinuity OK: locate closed the gate\n";
        }
        else if (macroResync)
        {
            if (!macroResyncAppliesRestoredState(factory, classInfo, host))
            {
                std::cerr << "HOOK macro.resync FAIL\n";
                return 5;
            }
            std::cout << "HOOK macro.resync OK: restored_macro=1.0 gate=0.25\n";
        }
        else if (reloadFade)
        {
            if (!reloadFadeLifecycle(factory, classInfo, host))
            {
                std::cerr << "HOOK reload.fade FAIL\n";
                return 5;
            }
            std::cout << "HOOK reload.fade OK: out=128 hold=640 in=128\n";
        }
        else if (embeddedState)
        {
            if (!embeddedStateSurvivesMissingSource(factory, classInfo, host))
            {
                std::cerr << "HOOK state.embedded_script FAIL\n";
                return 5;
            }
            std::cout << "HOOK state.embedded_script OK: source_removed=1\n";
        }
        else if (!stateRoundTrip(factory, classInfo, host))
        {
            std::cerr << "HOOK state.roundtrip FAIL\n";
            return 5;
        }
        const bool defaultSuite = !embeddedState && !reloadFade &&
                                  !macroResync && !transportMode &&
                                  !renderMode && !effectMode && !scriptProbe &&
                                  !instrumentProbe && !patchSelectMode;
        if (defaultSuite)
            std::cout << "HOOK state.roundtrip OK: legacy_v1=1 malformed=4\n";

        if (defaultSuite &&
            !processLifecycle(factory, classInfo, host, expectMicroPython))
        {
            std::cerr << "HOOK lifecycle.process FAIL\n";
            return 6;
        }
        if (defaultSuite)
            std::cout << "HOOK lifecycle.process OK\n";
    }

    module.reset();
    std::cout << "HOOK module.unload OK\n";
    return 0;
}
