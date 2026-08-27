#pragma once

#include "public.sdk/source/vst/vsteditcontroller.h"

#include <cstdint>
#include <string>

namespace PyDevices::MicroPythonVST3 {

class Editor;

class Controller final : public Steinberg::Vst::EditControllerEx1,
                         public Steinberg::Vst::IMidiMapping
{
public:
    static Steinberg::FUnknown* createInstance (void*);

    Steinberg::tresult PLUGIN_API initialize (Steinberg::FUnknown* context) override;
    Steinberg::tresult PLUGIN_API terminate () override;
    Steinberg::IPlugView* PLUGIN_API createView (Steinberg::FIDString name) override;
    Steinberg::tresult PLUGIN_API notify (Steinberg::Vst::IMessage* message) override;
    Steinberg::tresult PLUGIN_API setComponentState (Steinberg::IBStream* state) override;
    Steinberg::tresult PLUGIN_API getMidiControllerAssignment (
        Steinberg::int32 busIndex, Steinberg::int16 channel,
        Steinberg::Vst::CtrlNumber midiControllerNumber,
        Steinberg::Vst::ParamID& id) override;
    Steinberg::tresult PLUGIN_API getUnitByBus (
        Steinberg::Vst::MediaType type, Steinberg::Vst::BusDirection dir,
        Steinberg::int32 busIndex, Steinberg::int32 channel,
        Steinberg::Vst::UnitID& unitId) override;

    void editorClosed (Editor* editor);

private:
    // The mapping the processor reported. Held whether or not a view exists,
    // because the report and the host's decision to open an editor arrive in
    // whichever order the host feels like.
    std::string uiMappingName_;
    std::uint32_t uiGeneration_ = 0U;
    Editor* editor_ = nullptr;

public:
    OBJ_METHODS (Controller, Steinberg::Vst::EditControllerEx1)
    DEFINE_INTERFACES
        DEF_INTERFACE (Steinberg::Vst::IMidiMapping)
    END_DEFINE_INTERFACES (Steinberg::Vst::EditControllerEx1)
    REFCOUNT_METHODS (Steinberg::Vst::EditControllerEx1)
};

} // namespace PyDevices::MicroPythonVST3
