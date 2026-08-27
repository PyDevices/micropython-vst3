#include "plugin_manifest.h"

#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <sstream>

#if defined(_WIN32)
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#else
#include <dlfcn.h>
#endif

namespace PyDevices::MicroPythonVST3 {

namespace {

constexpr const char* kManifestName = "plugins.manifest";
constexpr const char* kManifestHeader = "mpvst-plugins 1";

// Where this binary lives. The same trick SidecarTransport::enginePath uses,
// and for the same reason: a plug-in is loaded by absolute path and cannot
// assume anything about the working directory.
std::filesystem::path moduleDirectory ()
{
#if defined(_WIN32)
    HMODULE module = nullptr;
    if (!GetModuleHandleExA (GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                                 GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                             reinterpret_cast<LPCSTR> (&moduleDirectory),
                             &module))
        return {};
    std::string path (32768U, '\0');
    const auto length =
        GetModuleFileNameA (module, path.data (), static_cast<DWORD> (path.size ()));
    if (length == 0U || length >= path.size ())
        return {};
    path.resize (length);
    return std::filesystem::path (path).parent_path ();
#else
    Dl_info information {};
    if (dladdr (reinterpret_cast<const void*> (&moduleDirectory), &information) == 0 ||
        information.dli_fname == nullptr)
        return {};
    return std::filesystem::path (information.dli_fname).parent_path ();
#endif
}

// 32 hex characters to an FUID, in the same four-word form the static class
// IDs use - so a generated ID and a hand-written one mean the same thing to
// the SDK, and the string in moduleinfo.json matches what gets registered.
bool parseUid (const std::string& text, Steinberg::FUID& out)
{
    if (text.size () != 32U)
        return false;
    Steinberg::uint32 words[4] {};
    for (int index = 0; index < 4; ++index)
    {
        const auto piece = text.substr (static_cast<std::size_t> (index) * 8U, 8U);
        char* end = nullptr;
        const auto value = std::strtoul (piece.c_str (), &end, 16);
        if (end == nullptr || *end != '\0')
            return false;
        words[index] = static_cast<Steinberg::uint32> (value);
    }
    out = Steinberg::FUID (words[0], words[1], words[2], words[3]);
    return true;
}

std::vector<PluginEntry> readManifest ()
{
    std::vector<PluginEntry> entries;
    const auto directory = moduleDirectory ();
    if (directory.empty ())
        return entries;
    std::ifstream input (directory / kManifestName);
    if (!input)
        return entries; // not scanned yet

    std::string line;
    if (!std::getline (input, line))
        return entries;
    if (!line.empty () && line.back () == '\r')
        line.pop_back ();
    if (line != kManifestHeader)
        return entries; // a manifest from another version: offer nothing

    while (std::getline (input, line))
    {
        if (!line.empty () && line.back () == '\r')
            line.pop_back ();
        if (line.empty ())
            continue;

        std::vector<std::string> fields;
        std::string field;
        std::istringstream stream (line);
        while (std::getline (stream, field, '\t'))
            fields.push_back (field);
        // Ten, not eleven: getline yields nothing for a trailing empty field,
        // so a plug-in whose macro labels are empty - which is most of the
        // effects until they grow a patch surface - arrives one field short.
        // Padding is right anyway, since a later version may append fields
        // this build should ignore rather than choke on.
        if (fields.size () < 10U)
            continue; // a line this build does not understand
        fields.resize (11U);

        PluginEntry entry;
        if (!parseUid (fields[0], entry.processorId) ||
            !parseUid (fields[1], entry.controllerId))
            continue;
        entry.effect = fields[2] == "effect";
        entry.name = fields[3];
        entry.subCategories = fields[4];
        entry.vendor = fields[5];
        entry.version = fields[6];
        entry.package = fields[7];
        entry.module = fields[8];
        entry.className = fields[9];
        entry.macroLabels = fields[10];
        if (entry.name.empty ())
            continue;
        entries.push_back (std::move (entry));
    }
    return entries;
}

} // namespace

std::string PluginEntry::scriptSource () const
{
    std::string source;
    // The controller reads macro names straight out of the embedded source,
    // so the comment has to be here as well as in the library module.
    if (!macroLabels.empty ())
        source += "# mpvst-macro-labels: " + macroLabels + "\n";
    if (effect)
    {
        source += "# mpvst-class: " + package + "." + className + "\n";
        source += "import mpvst_effect_adapter\n";
        source += "mpvst_effect_adapter.run(\"" + className + "\")\n";
    }
    else
    {
        // The tooling in tools/ reads this to find the library module a
        // script stands for, so the synthesised source carries it too - the
        // text a plug-in runs and the text the sweeps run are then the same.
        source += "# mpvst-module: " + package + "." + module + "\n";
        source += "import mpvst_adapter\n";
        source += "mpvst_adapter.run(\"" + package + "." + module + "\")\n";
    }
    return source;
}

const std::vector<PluginEntry>& manifestPlugins ()
{
    // Read once, at first use, which is while the host is building the
    // factory - never on an audio thread.
    static const std::vector<PluginEntry> entries = readManifest ();
    return entries;
}

} // namespace PyDevices::MicroPythonVST3
