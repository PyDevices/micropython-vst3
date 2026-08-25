#include "cids.h"
#include "controller.h"
#include "processor.h"
#include "version.h"

#include "public.sdk/source/main/pluginfactory.h"
#include "pluginterfaces/vst/ivstaudioprocessor.h"

#define stringPluginName "MicroPython Instrument"
#define stringEffectName "MicroPython Effect"

using namespace Steinberg;
using namespace Steinberg::Vst;

BEGIN_FACTORY_DEF (stringCompanyName, stringCompanyWeb, stringCompanyEmail)

DEF_CLASS2 (
    INLINE_UID_FROM_FUID (PyDevices::MicroPythonVST3::kProcessorUID),
    PClassInfo::kManyInstances,
    kVstAudioEffectClass,
    stringPluginName,
    0,
    Vst::PlugType::kInstrumentSynth,
    FULL_VERSION_STR,
    kVstVersionString,
    PyDevices::MicroPythonVST3::Processor::createInstance)

DEF_CLASS2 (
    INLINE_UID_FROM_FUID (PyDevices::MicroPythonVST3::kControllerUID),
    PClassInfo::kManyInstances,
    kVstComponentControllerClass,
    stringPluginName " Controller",
    0,
    "",
    FULL_VERSION_STR,
    kVstVersionString,
    PyDevices::MicroPythonVST3::Controller::createInstance)

DEF_CLASS2 (
    INLINE_UID_FROM_FUID (PyDevices::MicroPythonVST3::kEffectProcessorUID),
    PClassInfo::kManyInstances,
    kVstAudioEffectClass,
    stringEffectName,
    0,
    Vst::PlugType::kFx,
    FULL_VERSION_STR,
    kVstVersionString,
    PyDevices::MicroPythonVST3::Processor::createEffectInstance)

DEF_CLASS2 (
    INLINE_UID_FROM_FUID (PyDevices::MicroPythonVST3::kEffectControllerUID),
    PClassInfo::kManyInstances,
    kVstComponentControllerClass,
    stringEffectName " Controller",
    0,
    "",
    FULL_VERSION_STR,
    kVstVersionString,
    PyDevices::MicroPythonVST3::Controller::createInstance)

END_FACTORY

