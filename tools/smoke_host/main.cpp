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

bool selectBundledEngine(const std::filesystem::path& bundle,
                         bool expectMicroPython)
{
#if defined(_WIN32)
    const auto wanted = expectMicroPython ? "micropython-vst-engine.exe"
                                          : "micropython-vst-native-engine.exe";
#else
    const auto wanted = expectMicroPython ? "micropython-vst-engine"
                                          : "micropython-vst-native-engine";
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
    if (argc < 2 || argc > 4 || (renderMode && modeArgument.empty()) ||
        (!renderMode && argc > 3) ||
        (!mode.empty() && mode != "--expect-micropython" &&
         mode != "--expect-embedded-state" && mode != "--expect-reload-fade" &&
         mode != "--expect-macro-resync" && mode != "--expect-transport" &&
         !renderMode))
    {
        std::cerr << "usage: mpvst_smoke_host <plugin.vst3> "
                     "[--expect-micropython|--expect-embedded-state|"
                     "--expect-reload-fade|--expect-macro-resync|"
                     "--expect-transport|--render-reference <out.pcm>]\n";
        return 2;
    }
    const bool embeddedState = mode == "--expect-embedded-state";
    const bool reloadFade = mode == "--expect-reload-fade";
    const bool macroResync = mode == "--expect-macro-resync";
    const bool transportMode = mode == "--expect-transport";
    const bool expectMicroPython = mode == "--expect-micropython" ||
                                   embeddedState || renderMode;

    std::string error;
    const auto modulePath = std::filesystem::weakly_canonical(argv[1]).string();
    if (!selectBundledEngine(modulePath, expectMicroPython))
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
                                  !macroResync && !transportMode && !renderMode;
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
