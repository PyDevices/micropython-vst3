#include "controller.h"

#include "base/source/fstreamer.h"
#include "parameters.h"
#include "script_metadata.h"
#include "pluginterfaces/base/ustring.h"
#include "pluginterfaces/vst/ivstmidicontrollers.h"

#include <algorithm>
#include <array>
#include <cstdio>

namespace PyDevices::MicroPythonVST3 {

using namespace Steinberg;
using namespace Steinberg::Vst;

FUnknown* Controller::createInstance (void*)
{
    return static_cast<IEditController*> (new Controller ());
}

tresult PLUGIN_API Controller::initialize (FUnknown* context)
{
    const auto result = EditControllerEx1::initialize (context);
    if (result != kResultOk)
        return result;

    parameters.addParameter (
        STR16 ("Bypass"), nullptr, 1, 0.0,
        ParameterInfo::kCanAutomate | ParameterInfo::kIsBypass,
        kBypassParameter);
    parameters.addParameter (
        STR16 ("Reload Script"), nullptr, 1, 0.0,
        ParameterInfo::kCanAutomate, kReloadParameter);
    parameters.addParameter (
        STR16 ("Engine Ready"), nullptr, 1, 0.0,
        ParameterInfo::kIsReadOnly, kEngineReadyParameter);
    parameters.addParameter (new RangeParameter (
        STR16 ("Engine Error"), kEngineErrorParameter, nullptr,
        0.0, 255.0, 0.0, 255, ParameterInfo::kIsReadOnly));

    for (std::size_t index = 0; index < kMacroParameterCount; ++index)
    {
        std::array<char, 32> ascii {};
        std::snprintf (ascii.data (), ascii.size (), "Macro %02u",
                       static_cast<unsigned> (index + 1));
        UString128 title (ascii.data ());
        parameters.addParameter (
            title, nullptr, 0, 0.5, ParameterInfo::kCanAutomate,
            kFirstMacroParameter + static_cast<ParamID> (index));
    }

    for (std::size_t channel = 0; channel < kMidiChannelCount; ++channel)
    {
        for (std::size_t controller = 0; controller < kMidiControllerCount;
             ++controller)
        {
            std::array<char, 48> ascii {};
            std::snprintf (ascii.data (), ascii.size (), "MIDI Ch %02u Ctrl %03u",
                           static_cast<unsigned> (channel + 1U),
                           static_cast<unsigned> (controller));
            UString128 title (ascii.data ());
            parameters.addParameter (
                title, nullptr, 0, 0.0,
                ParameterInfo::kCanAutomate | ParameterInfo::kIsHidden,
                midiParameterId (channel, controller));
        }
    }

    return kResultOk;
}

tresult PLUGIN_API Controller::getMidiControllerAssignment (
    int32 busIndex, int16 channel, CtrlNumber midiControllerNumber, ParamID& id)
{
    if (busIndex != 0 || channel < 0 ||
        static_cast<std::size_t> (channel) >= kMidiChannelCount ||
        midiControllerNumber < 0 ||
        static_cast<std::size_t> (midiControllerNumber) >= kMidiControllerCount)
        return kResultFalse;

    id = midiParameterId (static_cast<std::size_t> (channel),
                          static_cast<std::size_t> (midiControllerNumber));
    return kResultTrue;
}

tresult PLUGIN_API Controller::setComponentState (IBStream* state)
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

    std::string scriptSource;
    if (version >= kStateVersion)
    {
        int32 pipelineBlocks = 0;
        int32 scriptBytes = 0;
        if (!stream.readInt32 (pipelineBlocks) ||
            pipelineBlocks < 1 || pipelineBlocks > kMaximumPipelineBlocks ||
            !stream.readInt32 (scriptBytes) || scriptBytes < 0 ||
            scriptBytes > kMaximumEmbeddedScriptBytes)
            return kResultFalse;
        scriptSource.resize (static_cast<std::size_t> (scriptBytes));
        if (scriptBytes != 0 &&
            stream.readRaw (scriptSource.data (), scriptBytes) != scriptBytes)
            return kResultFalse;
    }

    setParamNormalized (kBypassParameter, bypass != 0 ? 1.0 : 0.0);
    for (std::size_t index = 0; index < values.size (); ++index)
    {
        const auto bounded = std::max (0.0f, std::min (1.0f, values[index]));
        setParamNormalized (
            kFirstMacroParameter + static_cast<ParamID> (index), bounded);
    }
    std::array<std::string, kMacroParameterCount> labels {};
    (void)parseMacroLabels (scriptSource, labels);
    for (std::size_t index = 0; index < labels.size (); ++index)
    {
        if (labels[index].empty ())
        {
            std::array<char, 32> ascii {};
            std::snprintf (ascii.data (), ascii.size (), "Macro %02u",
                           static_cast<unsigned> (index + 1U));
            labels[index] = ascii.data ();
        }
        auto* parameter = parameters.getParameter (
            kFirstMacroParameter + static_cast<ParamID> (index));
        if (parameter == nullptr)
            continue;
        UString128 title (labels[index].c_str ());
        UString (parameter->getInfo ().title,
                 str16BufferSize (parameter->getInfo ().title)).assign (title);
    }
    if (componentHandler != nullptr)
        (void)componentHandler->restartComponent (kParamTitlesChanged);
    return kResultOk;
}

} // namespace PyDevices::MicroPythonVST3
