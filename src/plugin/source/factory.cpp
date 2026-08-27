#include "cids.h"
#include "controller.h"
#include "plugin_catalog.h"
#include "processor.h"
#include "version.h"

#include "public.sdk/source/main/pluginfactory.h"
#include "pluginterfaces/vst/ivstaudioprocessor.h"

#define stringPluginName "MicroPython Script Host"
#define stringEffectName "MicroPython Script Host (Fx)"

using namespace Steinberg;
using namespace Steinberg::Vst;

BEGIN_FACTORY_DEF (stringCompanyName, stringCompanyWeb, stringCompanyEmail)

// The two built-in classes. These load whatever script MPVST_SCRIPT_PATH or
// project state gives them, which is the developer loop and what every
// existing project uses; the named plug-ins below are the product.
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

// Everything the moduleinfo beside this binary declares. Registered here, at
// load, rather than compiled in - which is what lets an instrument be added
// by writing a script and re-running the scanner, with no build involved.
//
// DEF_CLASS2 cannot express this: it has no way to pass a context, and one
// create function has to serve every entry. registerClass takes both, and it
// copies the PClassInfo2, so only the entry itself has to outlive this loop -
// and it does, because catalogPlugins() owns a function-static vector.
//
// No controller class is registered here. Every one of these names a
// controller compiled in above, so the classes this loop adds are exactly
// the plug-ins the catalog lists and nothing else.
for (const auto& entry : PyDevices::MicroPythonVST3::catalogPlugins ())
{
    TUID processorId;
    entry.processorId.toTUID (processorId);
    PClassInfo2 processorClass (
        processorId, PClassInfo::kManyInstances, kVstAudioEffectClass,
        entry.name.c_str (), 0, entry.subCategories.c_str (),
        entry.vendor.c_str (), entry.version.c_str (), kVstVersionString);
    gPluginFactory->registerClass (
        &processorClass, PyDevices::MicroPythonVST3::Processor::createFromCatalog,
        const_cast<PyDevices::MicroPythonVST3::CatalogEntry*> (&entry));
}

END_FACTORY
