#include "public.sdk/source/common/memorystream.h"
#include "base/source/fobject.h"
#include "base/source/fstreamer.h"
#include "public.sdk/source/vst/hosting/eventlist.h"
#include "public.sdk/source/vst/hosting/hostclasses.h"
#include "public.sdk/source/vst/hosting/module.h"
#include "public.sdk/source/vst/hosting/parameterchanges.h"

#include "pluginterfaces/vst/ivstaudioprocessor.h"
#include "pluginterfaces/vst/ivstcomponent.h"
#include "pluginterfaces/vst/ivsteditcontroller.h"
#include "pluginterfaces/vst/ivstmessage.h"
#include "pluginterfaces/base/ustring.h"
#include "pluginterfaces/gui/iplugview.h"

#include "editor_message.h"
#include "mpvst/atomic.h"
#include "mpvst/shared_memory.h"
#include "mpvst/ui.h"

#include <algorithm>
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
#include <tuple>
#include <vector>

#if defined(_WIN32)
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#endif

namespace {

using namespace Steinberg;
using namespace Steinberg::Vst;
using namespace PyDevices::MicroPythonVST3;
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
                      FUnknown* host)
{
#if defined(_WIN32)
    (void)_putenv_s("MPVST_NATIVE_TEST_TONE", "");
#else
    (void)unsetenv("MPVST_NATIVE_TEST_TONE");
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
    const auto midiChannel = 0;
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
    const auto blockCount = 96;
    for (int block = 0; block < blockCount; ++block)
    {
        if (block == 6)
        {
            inputEvents.clear();
            (void)inputEvents.addEvent(noteOff);
            data.inputEvents = &inputEvents;
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
            if (block == 4 && frame < 64U && sample != 0.0F)
            {
                std::cerr << "HOOK midi.sample_offset FAIL: early sample="
                          << frame << '\n';
                return false;
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
    // The note-on at offset 64 must emerge at 512 + 64 after the fixed
    // pipeline, so audible 220 Hz output also proves the event reached the
    // Python synthio graph.
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
//------------------------------------------------------------------------
// The editor, driven through shared memory exactly as the view drives it.
//
// No window is opened. That is deliberate: what has to hold is the protocol -
// the engine paints when the editor is open and stops when it is not, input
// injected into the ring reaches the panel, and the gestures it produces come
// back as parameter edits pointing the right way. A window would add a display
// dependency to a test whose subject is not drawing, and the REAPER matrix
// already exercises the real one.
//------------------------------------------------------------------------

// Relays IConnectionPoint traffic between the component and the controller,
// which is how the controller learns where the editor's mapping is. Hosts do
// this for real; the test does it so the same code path runs here.
class ConnectionRelay : public FObject, public IConnectionPoint
{
public:
    void setPeer(IConnectionPoint* peer) { peer_ = peer; }
    const std::string& mappingName() const { return mappingName_; }
    std::uint32_t generation() const { return generation_; }

    tresult PLUGIN_API connect(IConnectionPoint*) SMTG_OVERRIDE { return kResultOk; }
    tresult PLUGIN_API disconnect(IConnectionPoint*) SMTG_OVERRIDE { return kResultOk; }

    tresult PLUGIN_API notify(IMessage* message) SMTG_OVERRIDE
    {
        if (message != nullptr && message->getMessageID() != nullptr &&
            std::strcmp(message->getMessageID(), kUiMappingMessageId) == 0)
        {
            const void* data = nullptr;
            uint32 size = 0U;
            int64 value = 0;
            if (auto* attributes = message->getAttributes())
            {
                if (attributes->getBinary(kUiMappingNameAttribute, data, size) !=
                    kResultOk)
                {
                    data = nullptr;
                    size = 0U;
                }
                (void)attributes->getInt(kUiMappingGenerationAttribute, value);
            }
            mappingName_.assign(static_cast<const char*>(data),
                                data != nullptr ? size : 0U);
            generation_ = static_cast<std::uint32_t>(value);
        }
        return peer_ != nullptr ? peer_->notify(message) : kResultOk;
    }

    OBJ_METHODS(ConnectionRelay, FObject)
    DEFINE_INTERFACES
        DEF_INTERFACE(IConnectionPoint)
    END_DEFINE_INTERFACES(FObject)
    REFCOUNT_METHODS(FObject)

private:
    IConnectionPoint* peer_ = nullptr;
    std::string mappingName_;
    std::uint32_t generation_ = 0U;
};

struct UiView
{
    mpvst::SharedMemory mapping;
    mpvst_ui_state* state = nullptr;

    bool open(const std::string& name)
    {
        close();
        const auto bytes = mpvst_ui_mapping_bytes();
        if (name.empty() || !mapping.open(name, bytes) ||
            !mpvst_ui_validate(mapping.data(), bytes))
        {
            mapping.close();
            return false;
        }
        state = static_cast<mpvst_ui_state*>(mapping.data());
        return true;
    }

    void close()
    {
        state = nullptr;
        mapping.close();
    }

    void setOpen(bool value)
    {
        mpvst::release_store_u32(&state->editor_open, value ? 1U : 0U);
    }

    std::uint64_t frames() const
    {
        return mpvst::acquire_load_u64(&state->frame_sequence);
    }

    void push(std::uint32_t type, std::uint32_t buttons, std::int32_t x,
              std::int32_t y, std::int32_t wheelVertical,
              std::int32_t wheelHorizontal)
    {
        auto* inputs = mpvst_ui_inputs(mapping.data());
        const auto head = mpvst::acquire_load_u64(&state->input_head);
        auto& record = inputs[head % MPVST_UI_INPUT_CAPACITY];
        record.type = type;
        record.buttons = buttons;
        record.x = x;
        record.y = y;
        record.wheel_vertical = wheelVertical;
        record.wheel_horizontal = wheelHorizontal;
        record.sequence = head + 1U;
        mpvst::release_store_u64(&state->input_head, head + 1U);
    }

    // Everything the engine has published since the last call, as
    // (kind, parameter, value).
    std::vector<std::tuple<std::uint32_t, std::uint32_t, float>> drainEdits()
    {
        std::vector<std::tuple<std::uint32_t, std::uint32_t, float>> out;
        const auto* edits = mpvst_ui_edits(mapping.data());
        auto tail = mpvst::acquire_load_u64(&state->edit_tail);
        const auto head = mpvst::acquire_load_u64(&state->edit_head);
        for (; tail != head; ++tail)
        {
            const auto& record = edits[tail % MPVST_UI_EDIT_CAPACITY];
            out.emplace_back(record.kind, record.parameter_id, record.value);
        }
        mpvst::release_store_u64(&state->edit_tail, head);
        return out;
    }
};

// GDI expands a BI_BITFIELDS RGB565 channel by replicating its high bits into
// the low ones. Matching that exactly is what lets a window capture and a
// framebuffer dump be compared without a tolerance, and a tolerance is the
// last thing this comparison should have: the bug it exists to catch is a
// whole-frame shift that a tolerance would happily accept.
std::uint8_t expand5(std::uint32_t value)
{
    return static_cast<std::uint8_t>((value << 3) | (value >> 2));
}

std::uint8_t expand6(std::uint32_t value)
{
    return static_cast<std::uint8_t>((value << 2) | (value >> 4));
}

void expandPixel(std::uint16_t pixel, char* rgb)
{
    rgb[0] = static_cast<char>(expand5((pixel >> 11) & 0x1FU));
    rgb[1] = static_cast<char>(expand6((pixel >> 5) & 0x3FU));
    rgb[2] = static_cast<char>(expand5(pixel & 0x1FU));
}

// Write the shared framebuffer out as a PPM, exactly as the engine left it.
// The view is a long way downstream of the pixels, so when an editor looks
// wrong on screen this is what says whether the engine drew it wrong or
// something after it did.
bool writeFramePpm(const UiView& view, const std::filesystem::path& path)
{
    const auto width = mpvst::acquire_load_u32(&view.state->width);
    const auto height = mpvst::acquire_load_u32(&view.state->height);
    const auto* pixels = mpvst_ui_framebuffer(view.mapping.data());
    const auto stride = mpvst_ui_stride_bytes();
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    if (!out)
        return false;
    out << "P6\n" << width << ' ' << height << "\n255\n";
    for (std::uint32_t y = 0; y < height; ++y)
    {
        const auto* row = reinterpret_cast<const std::uint16_t*>(
            pixels + static_cast<std::size_t>(y) * stride);
        for (std::uint32_t x = 0; x < width; ++x)
        {
            char rgb[3];
            expandPixel(row[x], rgb);
            out.write(rgb, 3);
        }
    }
    return out.good();
}

#if defined(_WIN32)
// Open the plug-in's real view in a real window and photograph it.
//
// The editor shipped with a blit that took the wrong rows out of the
// framebuffer, and nothing caught it: the engine's pixels were right, the
// protocol was right, and the audio was right. The only thing that would have
// caught it is looking at the window, so this looks at the window.
bool captureEditorWindow(const PluginFactory& factory,
                         const ClassInfo& classInfo, FUnknown* host,
                         const std::string& outputPath, bool& skipped)
{
    skipped = false;
    auto component = createComponent(factory, classInfo, host);
    auto processor = getProcessor(component);
    if (!component || !processor)
        return false;

    TUID controllerCID {};
    if (!ok(component->getControllerClassId(controllerCID)))
        return false;
    auto controller =
        factory.createInstance<IEditController>(VST3::UID(controllerCID));
    if (!controller || !ok(controller->initialize(host)))
        return false;

    // The view learns where the framebuffer is from the processor, over the
    // connection a host would wire. Without it there is nothing to paint.
    IConnectionPoint* componentConnection = nullptr;
    IConnectionPoint* controllerConnection = nullptr;
    if (!ok(component->queryInterface(IConnectionPoint::iid,
                                      reinterpret_cast<void**>(
                                          &componentConnection))) ||
        !ok(controller->queryInterface(IConnectionPoint::iid,
                                       reinterpret_cast<void**>(
                                           &controllerConnection))))
        return false;
    auto ownedComponentConnection = owned(componentConnection);
    auto ownedControllerConnection = owned(controllerConnection);
    auto relay = owned(new ConnectionRelay);
    relay->setPeer(controllerConnection);
    if (!ok(componentConnection->connect(relay)))
        return false;

    SpeakerArrangement stereo = SpeakerArr::kStereo;
    ProcessSetup setup {};
    setup.processMode = kRealtime;
    setup.symbolicSampleSize = kSample32;
    setup.maxSamplesPerBlock = 256;
    setup.sampleRate = 48000.0;
    if (!ok(processor->setBusArrangements(nullptr, 0, &stereo, 1)) ||
        !ok(component->activateBus(kAudio, kOutput, 0, true)) ||
        !ok(processor->setupProcessing(setup)) ||
        !ok(component->setActive(true)) ||
        !ok(processor->setProcessing(true)))
        return false;

    auto* view = controller->createView(ViewType::kEditor);
    if (view == nullptr)
    {
        std::cerr << "HOOK editor.capture FAIL: no view\n";
        return false;
    }
    ViewRect size {};
    if (!ok(view->getSize(&size)))
        return false;
    const auto width = size.right - size.left;
    const auto height = size.bottom - size.top;

    // A plain top-level window standing in for the host's frame. The view is
    // a child of whatever it is handed, so this is the same path a DAW takes.
    WNDCLASSEXW frameClass {};
    frameClass.cbSize = sizeof(frameClass);
    frameClass.lpfnWndProc = DefWindowProcW;
    frameClass.hInstance = GetModuleHandleW(nullptr);
    frameClass.lpszClassName = L"MpvstSmokeHostFrame";
    RegisterClassExW(&frameClass);
    // Parked offscreen and never activated. The editor answers
    // WM_PRINTCLIENT, so the capture does not need the window to be visible -
    // which keeps this from stealing focus, and keeps a stray click from
    // spoiling the picture.
    HWND frame = CreateWindowExW(WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
                                 L"MpvstSmokeHostFrame", L"mpvst", WS_POPUP,
                                 -32000, -32000, width, height, nullptr,
                                 nullptr, GetModuleHandleW(nullptr), nullptr);
    if (frame == nullptr)
    {
        std::cout << "SKIP editor.capture: no window station\n";
        skipped = true;
        return true;
    }
    ShowWindow(frame, SW_SHOWNOACTIVATE);

    if (!ok(view->attached(frame, kPlatformTypeHWND)))
    {
        std::cerr << "HOOK editor.capture FAIL: attach refused\n";
        return false;
    }

    std::array<float, 256> left {};
    std::array<float, 256> right {};
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

    // Turn the audio pipeline and the window's message queue together: the
    // engine only paints when it has slack, and the view only presents from
    // its own WM_TIMER.
    for (int block = 0; block < 400; ++block)
    {
        (void)processor->process(data);
        MSG message;
        while (PeekMessageW(&message, nullptr, 0, 0, PM_REMOVE))
        {
            TranslateMessage(&message);
            DispatchMessageW(&message);
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
    }

    HWND child = GetWindow(frame, GW_CHILD);
    if (child == nullptr)
    {
        std::cerr << "HOOK editor.capture FAIL: the view made no window\n";
        return false;
    }

    BITMAPINFO shot {};
    shot.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
    shot.bmiHeader.biWidth = width;
    shot.bmiHeader.biHeight = -height;
    shot.bmiHeader.biPlanes = 1;
    shot.bmiHeader.biBitCount = 32;
    shot.bmiHeader.biCompression = BI_RGB;
    void* bits = nullptr;
    HDC childDc = GetDC(child);
    HDC memory = CreateCompatibleDC(childDc);
    HBITMAP bitmap =
        CreateDIBSection(memory, &shot, DIB_RGB_COLORS, &bits, nullptr, 0);
    HGDIOBJ previous = SelectObject(memory, bitmap);
    // PrintWindow asks the window to draw itself, which is what reaches the
    // editor's own WM_PAINT rather than whatever happens to be on screen.
    if (PrintWindow(child, memory, PW_CLIENTONLY) == 0)
        BitBlt(memory, 0, 0, width, height, childDc, 0, 0, SRCCOPY);
    GdiFlush();

    // The whole point. What the window shows must be what the engine drew -
    // not merely something plausible, and not merely the right pixels in the
    // wrong place, which is exactly how this shipped broken.
    UiView surface;
    if (!surface.open(relay->mappingName()))
    {
        std::cerr << "HOOK editor.capture FAIL: cannot open the mapping\n";
        return false;
    }
    const auto* framebuffer = mpvst_ui_framebuffer(surface.mapping.data());
    const auto stride = mpvst_ui_stride_bytes();
    const auto* captured = static_cast<const std::uint32_t*>(bits);
    int firstBadRow = -1;
    for (int32 y = 0; y < height && firstBadRow < 0; ++y)
    {
        const auto* row = reinterpret_cast<const std::uint16_t*>(
            framebuffer + static_cast<std::size_t>(y) * stride);
        for (int32 x = 0; x < width; ++x)
        {
            char expected[3];
            expandPixel(row[x], expected);
            const auto pixel = captured[static_cast<std::size_t>(y) * width + x];
            if (static_cast<char>((pixel >> 16) & 0xFFU) != expected[0] ||
                static_cast<char>((pixel >> 8) & 0xFFU) != expected[1] ||
                static_cast<char>(pixel & 0xFFU) != expected[2])
            {
                firstBadRow = y;
                break;
            }
        }
    }

    std::ofstream out(outputPath, std::ios::binary | std::ios::trunc);
    if (!out)
        return false;
    out << "P6\n" << width << ' ' << height << "\n255\n";
    const auto* pixels = static_cast<const std::uint32_t*>(bits);
    for (int32 y = 0; y < height; ++y)
    {
        for (int32 x = 0; x < width; ++x)
        {
            const auto pixel = pixels[static_cast<std::size_t>(y) * width + x];
            const char rgb[3] = {static_cast<char>((pixel >> 16) & 0xFFU),
                                 static_cast<char>((pixel >> 8) & 0xFFU),
                                 static_cast<char>(pixel & 0xFFU)};
            out.write(rgb, 3);
        }
    }
    out.close();

    SelectObject(memory, previous);
    DeleteObject(bitmap);
    DeleteDC(memory);
    ReleaseDC(child, childDc);
    (void)view->removed();
    view->release();
    DestroyWindow(frame);
    (void)processor->setProcessing(false);
    (void)component->setActive(false);
    (void)componentConnection->disconnect(relay);
    (void)controller->terminate();
    (void)component->terminate();
    if (firstBadRow >= 0)
    {
        std::cerr << "HOOK editor.capture FAIL: the window and the framebuffer "
                     "first differ at row " << firstBadRow << "; see "
                  << outputPath << '\n';
        return false;
    }
    std::cout << "HOOK editor.capture OK: the window matches the framebuffer "
                 "exactly (" << width << 'x' << height << "), " << outputPath
              << '\n';
    return true;
}
#endif

bool editorDrivesParameters(const PluginFactory& factory,
                            const ClassInfo& classInfo, FUnknown* host,
                            const std::string& framePath)
{
    const auto sourcePath = std::filesystem::temp_directory_path() /
        "mpvst-editor-probe.py";
    // Sixteen macros with names of their own, so the panel has real labels to
    // draw and the test is exercising the same metadata path a shipped
    // instrument uses.
    constexpr const char* source =
        "# mpvst-macro-labels: Alpha | Bravo | Charlie | Delta | Echo | "
        "Foxtrot | Golf | Hotel | India | Juliett | Kilo | Lima | Mike | "
        "November | Oscar | Papa\n"
        "import synthio\n"
        "import vstaudio\n"
        "synth = synthio.Synthesizer(sample_rate=vstaudio.sample_rate(), "
        "channel_count=2)\n"
        "vstaudio.output(synth)\n";
    {
        std::ofstream out(sourcePath, std::ios::binary | std::ios::trunc);
        if (!out || !out.write(source, static_cast<std::streamsize>(
                                           std::strlen(source))))
            return false;
    }
    setScriptPath(sourcePath.string());
    struct Cleanup
    {
        ~Cleanup() { setScriptPath({}); }
    } cleanup;

    auto component = createComponent(factory, classInfo, host);
    auto processor = getProcessor(component);
    if (!component || !processor)
        return false;

    IConnectionPoint* componentConnection = nullptr;
    if (!ok(component->queryInterface(IConnectionPoint::iid,
                                      reinterpret_cast<void**>(
                                          &componentConnection))))
        return false;
    auto ownedConnection = owned(componentConnection);
    auto relay = owned(new ConnectionRelay);
    if (!ok(componentConnection->connect(relay)))
        return false;

    SpeakerArrangement stereo = SpeakerArr::kStereo;
    ProcessSetup setup {};
    setup.processMode = kRealtime;
    setup.symbolicSampleSize = kSample32;
    setup.maxSamplesPerBlock = 256;
    setup.sampleRate = 48000.0;
    if (!ok(processor->setBusArrangements(nullptr, 0, &stereo, 1)) ||
        !ok(component->activateBus(kAudio, kOutput, 0, true)) ||
        !ok(processor->setupProcessing(setup)) ||
        !ok(component->setActive(true)) ||
        !ok(processor->setProcessing(true)))
        return false;

    std::array<float, 256> left {};
    std::array<float, 256> right {};
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

    // Keeps the pipeline turning at roughly real time, which is what leaves
    // the engine idle enough to run its housekeeping step at all.
    const auto pump = [&](int blocks) {
        for (int block = 0; block < blocks; ++block)
        {
            if (!ok(processor->process(data)))
                return false;
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
        }
        return true;
    };

    if (relay->mappingName().empty())
    {
        std::cerr << "HOOK editor.mapping FAIL: no mapping reported\n";
        return false;
    }
    UiView view;
    if (!view.open(relay->mappingName()))
    {
        std::cerr << "HOOK editor.mapping FAIL: cannot open "
                  << relay->mappingName() << '\n';
        return false;
    }

    // Closed: the engine must not paint at all.
    if (!pump(20))
        return false;
    if (view.frames() != 0U)
    {
        std::cerr << "HOOK editor.closed FAIL: painted with no editor open\n";
        return false;
    }
    std::cout << "HOOK editor.closed OK: no frames published\n";

    view.setOpen(true);
    for (int attempt = 0; attempt < 60 && view.frames() == 0U; ++attempt)
    {
        if (!pump(10))
            return false;
    }
    if (view.frames() == 0U)
    {
        std::cerr << "HOOK editor.open FAIL: no frames after opening\n";
        return false;
    }
    std::cout << "HOOK editor.open OK: frames=" << view.frames() << '\n';
    if (!framePath.empty())
    {
        if (!writeFramePpm(view, framePath))
        {
            std::cerr << "HOOK editor.frame FAIL: cannot write " << framePath
                      << '\n';
            return false;
        }
        std::cout << "HOOK editor.frame OK: " << framePath << '\n';
    }
    (void)view.drainEdits();

    // Click the first macro slider, then swipe right along it. Both signs are
    // asserted, because a sign is a fact about this input path and nothing
    // else in the build would notice if it flipped.
    constexpr std::int32_t kSliderX = 250;
    constexpr std::int32_t kSliderY = 101;
    view.push(MPVST_UI_INPUT_POINTER_MOVE, 0U, kSliderX, kSliderY, 0, 0);
    view.push(MPVST_UI_INPUT_POINTER_DOWN, 1U, kSliderX, kSliderY, 0, 0);
    view.push(MPVST_UI_INPUT_POINTER_UP, 0U, kSliderX, kSliderY, 0, 0);
    if (!pump(30))
        return false;
    auto edits = view.drainEdits();
    if (edits.empty() || std::get<1>(edits.front()) != 100U)
    {
        std::cerr << "HOOK editor.click FAIL: no edit on the first macro\n";
        return false;
    }
    const auto afterClick = std::get<2>(edits.back());
    std::cout << "HOOK editor.click OK: macro 100 = " << afterClick << '\n';

    for (int notch = 0; notch < 5; ++notch)
        view.push(MPVST_UI_INPUT_WHEEL, 0U, 0, 0, 0, MPVST_UI_WHEEL_NOTCH);
    if (!pump(40))
        return false;
    edits = view.drainEdits();
    float highest = afterClick;
    bool sawMacro = false;
    bool sawEnd = false;
    for (const auto& edit : edits)
    {
        if (std::get<1>(edit) != 100U)
            continue;
        sawMacro = true;
        highest = std::max(highest, std::get<2>(edit));
        sawEnd = sawEnd || std::get<0>(edit) == MPVST_UI_EDIT_END;
    }
    if (!sawMacro || highest <= afterClick)
    {
        std::cerr << "HOOK editor.adjust FAIL: a rightward swipe did not raise "
                     "the focused macro\n";
        return false;
    }
    if (!sawEnd)
    {
        std::cerr << "HOOK editor.adjust FAIL: the wheel gesture never ended\n";
        return false;
    }
    std::cout << "HOOK editor.adjust OK: macro 100 rose to " << highest
              << " and the gesture closed\n";

    // A downward swipe moves to the next control; adjusting then lands on the
    // second macro rather than the first.
    view.push(MPVST_UI_INPUT_WHEEL, 0U, 0, 0, -MPVST_UI_WHEEL_NOTCH, 0);
    if (!pump(20))
        return false;
    (void)view.drainEdits();
    for (int notch = 0; notch < 3; ++notch)
        view.push(MPVST_UI_INPUT_WHEEL, 0U, 0, 0, 0, MPVST_UI_WHEEL_NOTCH);
    if (!pump(40))
        return false;
    edits = view.drainEdits();
    bool sawNextMacro = false;
    for (const auto& edit : edits)
        sawNextMacro = sawNextMacro || std::get<1>(edit) == 101U;
    if (!sawNextMacro)
    {
        std::cerr << "HOOK editor.navigate FAIL: a downward swipe did not "
                     "reach the next control\n";
        return false;
    }
    std::cout << "HOOK editor.navigate OK: focus moved to macro 101\n";

    // Closing stops the painting and nothing else.
    view.setOpen(false);
    if (!pump(20))
        return false;
    const auto quiesced = view.frames();
    if (!pump(20))
        return false;
    if (view.frames() != quiesced)
    {
        std::cerr << "HOOK editor.close FAIL: still painting after close\n";
        return false;
    }
    std::cout << "HOOK editor.close OK: painting stopped\n";

    // Reopening is where the editor went black. A view starts with an empty
    // copy of the framebuffer and fills it from the dirty-rectangle ring, but
    // rectangles say what *changed* - and a reopened editor showing a panel
    // nobody has touched changes nothing, so a rectangle-only view waits
    // forever on a ring that stays empty. These two assertions are the shape
    // of that: the ring really does stay quiet, and the framebuffer really
    // does still hold the frame, which is what a reopened view reads instead.
    const auto quietRects = mpvst::acquire_load_u64(&view.state->rect_head);
    view.setOpen(true);
    if (!pump(40))
        return false;
    if (mpvst::acquire_load_u64(&view.state->rect_head) != quietRects)
    {
        std::cerr << "HOOK editor.reopen FAIL: expected a static panel to "
                     "publish no rectangles\n";
        return false;
    }
    bool anyPixel = false;
    {
        const auto width = mpvst::acquire_load_u32(&view.state->width);
        const auto height = mpvst::acquire_load_u32(&view.state->height);
        const auto* pixels = mpvst_ui_framebuffer(view.mapping.data());
        const auto stride = mpvst_ui_stride_bytes();
        for (std::uint32_t y = 0; y < height && !anyPixel; ++y)
        {
            const auto* row = reinterpret_cast<const std::uint16_t*>(
                pixels + static_cast<std::size_t>(y) * stride);
            for (std::uint32_t x = 0; x < width; ++x)
            {
                if (row[x] != 0U)
                {
                    anyPixel = true;
                    break;
                }
            }
        }
    }
    if (!anyPixel)
    {
        std::cerr << "HOOK editor.reopen FAIL: the framebuffer lost the frame, "
                     "so a reopened view has nothing to show\n";
        return false;
    }
    std::cout << "HOOK editor.reopen OK: no new rectangles, frame still in "
                 "the buffer\n";
    view.setOpen(false);

    // A deactivate/activate cycle is an engine restart as far as the editor is
    // concerned: a new mapping, a new generation, and no stale input replayed
    // into it.
    const auto firstName = relay->mappingName();
    const auto firstGeneration = relay->generation();
    view.close();
    if (!ok(processor->setProcessing(false)) || !ok(component->setActive(false)))
        return false;
    if (!ok(component->setActive(true)) || !ok(processor->setProcessing(true)))
        return false;
    if (relay->mappingName().empty() ||
        (relay->mappingName() == firstName &&
         relay->generation() == firstGeneration))
    {
        std::cerr << "HOOK editor.restart FAIL: the editor was not told the "
                     "mapping changed\n";
        return false;
    }
    if (!view.open(relay->mappingName()))
    {
        std::cerr << "HOOK editor.restart FAIL: cannot open the new mapping\n";
        return false;
    }
    if (mpvst::acquire_load_u64(&view.state->input_head) != 0U ||
        mpvst::acquire_load_u64(&view.state->edit_head) != 0U)
    {
        std::cerr << "HOOK editor.restart FAIL: cursors carried over\n";
        return false;
    }
    view.setOpen(true);
    for (int attempt = 0; attempt < 60 && view.frames() == 0U; ++attempt)
    {
        if (!pump(10))
            return false;
    }
    if (view.frames() == 0U)
    {
        std::cerr << "HOOK editor.restart FAIL: no frames after restarting\n";
        return false;
    }
    std::cout << "HOOK editor.restart OK: generation "
              << relay->generation() << " painting again\n";

    view.setOpen(false);
    view.close();
    (void)processor->setProcessing(false);
    (void)component->setActive(false);
    (void)componentConnection->disconnect(relay);
    (void)component->terminate();
    return true;
}

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

} // namespace

int main(int argc, char** argv)
{
    const std::string mode = argc >= 3 ? argv[2] : "";
    const std::string modeArgument = argc >= 4 ? argv[3] : "";
    const bool renderMode = mode == "--render-reference";
    const bool frameDump = mode == "--dump-editor-frame";
    const bool windowCapture = mode == "--capture-editor-window";
    const bool scriptProbe = mode == "--effect-script";
    const bool instrumentProbe = mode == "--instrument-script";
    if (argc < 2 || argc > 4 ||
        ((renderMode || scriptProbe || instrumentProbe || frameDump ||
          windowCapture) && modeArgument.empty()) ||
        (!renderMode && !scriptProbe && !instrumentProbe && !frameDump &&
         !windowCapture && argc > 3) ||
        (!mode.empty() && mode != "--expect-micropython" &&
         mode != "--expect-embedded-state" &&
         mode != "--expect-effect-audio" && mode != "--expect-patch-select" &&
         mode != "--expect-editor" && mode != "--dump-editor-frame" &&
         mode != "--capture-editor-window" &&
         mode != "--effect-script" && mode != "--instrument-script" &&
         !renderMode))
    {
        std::cerr << "usage: mpvst_smoke_host <plugin.vst3> "
                     "[--expect-micropython|--expect-embedded-state|"
                     "--expect-effect-audio|"
                     "--expect-patch-select|"
                     "--expect-editor|"
                     "--dump-editor-frame <out.ppm>|"
                     "--capture-editor-window <out.ppm>|"
                     "--effect-script <script.py>|"
                     "--instrument-script <script.py>|"
                     "--render-reference <out.pcm>]\n";
        return 2;
    }
    const bool embeddedState = mode == "--expect-embedded-state";
    const bool effectMode = mode == "--expect-effect-audio";
    const bool patchSelectMode = mode == "--expect-patch-select";
    const bool editorMode = mode == "--expect-editor" || frameDump;

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
        else if (windowCapture)
        {
#if defined(_WIN32)
            bool skipped = false;
            if (!captureEditorWindow(factory, classInfo, host, modeArgument,
                                     skipped))
            {
                std::cerr << "HOOK editor.capture FAIL\n";
                return 5;
            }
            if (skipped)
                return 77; // ctest SKIP_RETURN_CODE
#else
            std::cerr << "HOOK editor.capture FAIL: Windows only\n";
            return 5;
#endif
        }
        else if (editorMode)
        {
            if (!editorDrivesParameters(factory, classInfo, host,
                                        frameDump ? modeArgument : std::string {}))
            {
                std::cerr << "HOOK editor FAIL\n";
                return 5;
            }
            std::cout << "HOOK editor OK\n";
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
        const bool defaultSuite = !embeddedState &&
                                  !renderMode && !effectMode && !scriptProbe &&
                                  !instrumentProbe && !patchSelectMode &&
                                  !editorMode && !windowCapture;
        if (defaultSuite)
            std::cout << "HOOK state.roundtrip OK: legacy_v1=1 malformed=4\n";

        if (defaultSuite &&
            !processLifecycle(factory, classInfo, host))
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
