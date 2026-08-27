#include "controller.h"

#include "base/source/fstreamer.h"
#include "editor.h"
#include "editor_message.h"
#include "parameters.h"
#include "script_metadata.h"
#include "pluginterfaces/base/ustring.h"
#include "pluginterfaces/vst/ivstaudioprocessor.h"
#include "pluginterfaces/vst/ivstmidicontrollers.h"

#include <algorithm>
#include <array>
#include <cstdio>
#include <cstring>

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

    // Patch program list: hosts translate an incoming MIDI Program Change
    // message into a change of this kIsProgramChange-flagged parameter,
    // since VST3's IEventList has no native program-change event type.
    addUnit (new Unit (STR16 ("Root"), kRootUnitId, kNoParentUnitId,
                       kPatchParameter));
    auto* patchList = new ProgramList (STR16 ("Patches"), kPatchParameter,
                                       kRootUnitId);
    addProgramList (patchList);
    for (std::size_t index = 0; index < kPatchCount; ++index)
    {
        std::array<char, 16> ascii {};
        std::snprintf (ascii.data (), ascii.size (), "Patch %03u",
                       static_cast<unsigned> (index + 1));
        UString128 title (ascii.data ());
        patchList->addProgram (title);
    }
    parameters.addParameter (patchList->getParameter ());

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

tresult PLUGIN_API Controller::terminate ()
{
    // The host normally releases its views first, but a controller torn down
    // with one still alive must not leave it holding a dangling owner - it
    // calls back on destruction.
    for (auto* editor : editors_)
        editor->mappingChanged ({}, 0U);
    editors_.clear ();
    return EditControllerEx1::terminate ();
}

IPlugView* PLUGIN_API Controller::createView (FIDString name)
{
    if (name == nullptr || std::strcmp (name, ViewType::kEditor) != 0)
        return nullptr;
    // Always hand out a fresh view. This used to refuse a second one while
    // the first was alive, on the theory that two readers would race over the
    // input ring - and that theory cost the editor its reopen: REAPER builds
    // the replacement view before releasing the one it is replacing, got a
    // null back, and showed a black rectangle from then on.
    //
    // The race it guarded against is not one. Only an attached view runs a
    // timer, only the visible window receives mouse messages, and an edit
    // drained by either view reaches this controller exactly once either way,
    // so a brief overlap costs nothing. The most that can happen is that a
    // detaching view clears editor_open a moment before the arriving one sets
    // it again, which skips a single frame.
    auto* editor = new Editor (this, uiMappingName_, uiGeneration_);
    editors_.push_back (editor);
    return editor;
}

void Controller::editorClosed (Editor* editor)
{
    for (auto candidate = editors_.begin (); candidate != editors_.end ();
         ++candidate)
    {
        if (*candidate == editor)
        {
            editors_.erase (candidate);
            return;
        }
    }
}

tresult PLUGIN_API Controller::notify (IMessage* message)
{
    if (message != nullptr && message->getMessageID () != nullptr &&
        std::strcmp (message->getMessageID (), kUiMappingMessageId) == 0)
    {
        const void* data = nullptr;
        uint32 size = 0U;
        int64 generation = 0;
        auto* attributes = message->getAttributes ();
        if (attributes != nullptr)
        {
            if (attributes->getBinary (kUiMappingNameAttribute, data, size) !=
                kResultOk)
            {
                data = nullptr;
                size = 0U;
            }
            (void)attributes->getInt (kUiMappingGenerationAttribute, generation);
        }
        uiMappingName_.assign (static_cast<const char*> (data),
                               data != nullptr ? size : 0U);
        uiGeneration_ = static_cast<std::uint32_t> (generation);
        for (auto* editor : editors_)
            editor->mappingChanged (uiMappingName_, uiGeneration_);
        return kResultOk;
    }
    return EditControllerEx1::notify (message);
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

tresult PLUGIN_API Controller::getUnitByBus (MediaType type, BusDirection dir,
                                             int32 busIndex, int32 channel,
                                             UnitID& unitId)
{
    // Associates the event input bus with the root unit, which owns the
    // patch program list: this is what tells a host it may translate an
    // incoming MIDI Program Change message into kPatchParameter.
    if (type == kEvent && dir == kInput && busIndex == 0 && channel == 0)
    {
        unitId = kRootUnitId;
        return kResultTrue;
    }
    return kResultFalse;
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
