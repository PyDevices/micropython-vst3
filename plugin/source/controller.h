#pragma once

#include "public.sdk/source/vst/vsteditcontroller.h"

namespace PyDevices::MicroPythonVST3 {

class Controller final : public Steinberg::Vst::EditControllerEx1,
                         public Steinberg::Vst::IMidiMapping
{
public:
    static Steinberg::FUnknown* createInstance (void*);

    Steinberg::tresult PLUGIN_API initialize (Steinberg::FUnknown* context) override;
    Steinberg::tresult PLUGIN_API setComponentState (Steinberg::IBStream* state) override;
    Steinberg::tresult PLUGIN_API getMidiControllerAssignment (
        Steinberg::int32 busIndex, Steinberg::int16 channel,
        Steinberg::Vst::CtrlNumber midiControllerNumber,
        Steinberg::Vst::ParamID& id) override;
    Steinberg::tresult PLUGIN_API getUnitByBus (
        Steinberg::Vst::MediaType type, Steinberg::Vst::BusDirection dir,
        Steinberg::int32 busIndex, Steinberg::int32 channel,
        Steinberg::Vst::UnitID& unitId) override;

    OBJ_METHODS (Controller, Steinberg::Vst::EditControllerEx1)
    DEFINE_INTERFACES
        DEF_INTERFACE (Steinberg::Vst::IMidiMapping)
    END_DEFINE_INTERFACES (Steinberg::Vst::EditControllerEx1)
    REFCOUNT_METHODS (Steinberg::Vst::EditControllerEx1)
};

} // namespace PyDevices::MicroPythonVST3
