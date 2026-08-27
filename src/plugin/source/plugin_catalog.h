#pragma once

// The list of plug-ins this binary offers, read at load time from the
// moduleinfo.json beside it rather than compiled in.
//
// That file is what a host reads to enumerate classes without loading the
// binary, so it already has to describe every plug-in exactly. Reading the
// same file here rather than keeping a second list of our own is what makes
// the two impossible to disagree - they were two files once, and they did.
//
// What VST3 has no field for - which script a class runs, and what its macro
// parameters are called - rides in `// mpvst-` comments above each class.
// moduleinfo.json is JSON5, whose parser reads past a comment but rejects an
// unknown key outright, so a comment is not a shortcut here; it is the only
// place the file can carry anything of ours.
//
// The file is written by lib/scan_plugins.py, which the engine itself runs -
// so adding an instrument is editing a script and re-scanning, never
// rebuilding. That is the whole point: a user who writes their own instrument
// gets it into their DAW without a compiler.
//
// A missing or unreadable file is not an error. The factory then offers only
// its built-in classes, which is exactly what it offered before any of this
// existed.

#include "pluginterfaces/base/funknown.h"

#include <string>
#include <vector>

namespace PyDevices::MicroPythonVST3 {

struct CatalogEntry
{
    Steinberg::FUID processorId;
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

// Every plug-in the moduleinfo beside this binary declares. Empty when there
// is none, which is the un-scanned state and not a failure.
const std::vector<CatalogEntry>& catalogPlugins ();

} // namespace PyDevices::MicroPythonVST3
