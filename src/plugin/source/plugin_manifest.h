#pragma once

// The list of plug-ins this binary offers, read at load time from a file
// beside it rather than compiled in.
//
// The file is written by lib/scan_plugins.py, which the engine itself runs -
// so adding an instrument is editing a script and re-scanning, never
// rebuilding. That is the whole point: a user who writes their own instrument
// gets it into their DAW without a compiler.
//
// A missing or unreadable manifest is not an error. The factory then offers
// only its built-in classes, which is exactly what it offered before any of
// this existed.

#include "pluginterfaces/base/funknown.h"

#include <cstdint>
#include <string>
#include <vector>

namespace PyDevices::MicroPythonVST3 {

struct PluginEntry
{
    Steinberg::FUID processorId;
    Steinberg::FUID controllerId;
    bool effect = false;
    std::string name;
    // VST3 sub-categories, already bar-separated the way PClassInfo2 wants
    // them: "Instrument|Drum", "Fx|Delay".
    std::string subCategories;
    std::string vendor;
    std::string version;
    // What the sidecar has to import to become this plug-in.
    std::string package;
    std::string module;
    std::string className;   // empty for an instrument: the module is the unit
    std::string macroLabels; // " | " separated, may be empty

    // The script this plug-in runs, built rather than stored.
    //
    // Every layer below already deals in script source - project state embeds
    // it, reload re-execs it, and the controller reads its macro names out of
    // it - so the cheapest way to add plug-ins was to keep giving those layers
    // a script and simply write it here. That is also what let the generated
    // shim files go: a two-line file on disk and two lines built in memory are
    // the same thing to everything downstream.
    std::string scriptSource () const;
};

// Every plug-in the manifest beside this binary declares. Empty when there is
// no manifest, which is the un-scanned state and not a failure.
const std::vector<PluginEntry>& manifestPlugins ();

} // namespace PyDevices::MicroPythonVST3
