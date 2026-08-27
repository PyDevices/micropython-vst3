#include "plugin_catalog.h"

#include "public.sdk/source/vst/moduleinfo/moduleinfoparser.h"

#include <cctype>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <map>
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

// Relative to the folder holding this binary, which inside a VST3 bundle is
// Contents/<architecture>.
constexpr const char* kModuleInfoRelative = "../Resources/moduleinfo.json";

constexpr const char* kSourceComment = "// mpvst-source:";
constexpr const char* kMacrosComment = "// mpvst-macros:";

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

std::string upper (std::string text)
{
    for (auto& character : text)
        character = static_cast<char> (std::toupper (
            static_cast<unsigned char> (character)));
    return text;
}

// The value of the first quoted string after `from`, which for our purposes
// is always the CID that a comment was written above.
std::string quotedAfter (const std::string& text, const std::string& key,
                         std::size_t from)
{
    const auto at = text.find (key, from);
    if (at == std::string::npos)
        return {};
    const auto open = text.find ('"', text.find (':', at));
    if (open == std::string::npos)
        return {};
    const auto close = text.find ('"', open + 1U);
    if (close == std::string::npos)
        return {};
    return text.substr (open + 1U, close - open - 1U);
}

// Which CID each `// mpvst-` comment belongs to.
//
// The comments are discarded by any JSON parser, so this reads the raw text
// alongside the parsed classes rather than through them. A comment belongs to
// the class it sits above, which is the next "CID" in the file - association
// by position, so it survives whatever the writer does about indentation.
std::map<std::string, std::string> commentValues (const std::string& text,
                                                  const std::string& marker)
{
    std::map<std::string, std::string> values;
    std::size_t at = text.find (marker);
    while (at != std::string::npos)
    {
        const auto end = text.find ('\n', at);
        auto value = text.substr (at + marker.size (),
                                  end == std::string::npos
                                      ? std::string::npos
                                      : end - at - marker.size ());
        while (!value.empty () && (value.front () == ' ' || value.front () == '\t'))
            value.erase (value.begin ());
        while (!value.empty () &&
               (value.back () == ' ' || value.back () == '\r' || value.back () == '\t'))
            value.pop_back ();
        const auto cid = upper (quotedAfter (text, "\"CID\"", at));
        if (!cid.empty () && !value.empty ())
            values.emplace (cid, std::move (value));
        at = text.find (marker, at + marker.size ());
    }
    return values;
}

std::vector<CatalogEntry> readCatalog ()
{
    std::vector<CatalogEntry> entries;
    const auto directory = moduleDirectory ();
    if (directory.empty ())
        return entries;
    std::ifstream input (directory / kModuleInfoRelative);
    if (!input)
        return entries; // not scanned yet

    std::stringstream buffer;
    buffer << input.rdbuf ();
    const auto text = buffer.str ();

    // Nothing is printed on a parse failure: this runs inside the host's
    // process during a scan, where there is nowhere to print to and the
    // right answer is the same as having no file at all.
    const auto info = Steinberg::ModuleInfoLib::parseJson (text, nullptr);
    if (!info)
        return entries;

    const auto sources = commentValues (text, kSourceComment);
    const auto macros = commentValues (text, kMacrosComment);

    for (const auto& classInfo : info->classes)
    {
        const auto cid = upper (classInfo.cid);
        const auto source = sources.find (cid);
        // A class with no source comment is one of the compiled-in ones,
        // already registered by the factory itself. Skipping it here is what
        // keeps the two from colliding.
        if (source == sources.end ())
            continue;

        CatalogEntry entry;
        if (!parseUid (cid, entry.processorId) || classInfo.name.empty ())
            continue;
        entry.name = classInfo.name;
        entry.vendor = classInfo.vendor;
        entry.version = classInfo.version;
        for (const auto& category : classInfo.subCategories)
        {
            if (!entry.subCategories.empty ())
                entry.subCategories += "|";
            entry.subCategories += category;
            if (category == "Fx")
                entry.effect = true;
        }

        // "audioeffects/delays.py#TapeDelay", or an instrument without the
        // class half because its module is the whole plug-in.
        auto path = source->second;
        const auto hash = path.find ('#');
        if (hash != std::string::npos)
        {
            entry.className = path.substr (hash + 1U);
            path.resize (hash);
        }
        const auto slash = path.find ('/');
        if (slash == std::string::npos)
            continue;
        entry.package = path.substr (0, slash);
        entry.module = path.substr (slash + 1U);
        if (entry.module.size () > 3U &&
            entry.module.compare (entry.module.size () - 3U, 3U, ".py") == 0)
            entry.module.resize (entry.module.size () - 3U);
        if (entry.package.empty () || entry.module.empty ())
            continue;

        const auto labels = macros.find (cid);
        if (labels != macros.end ())
            entry.macroLabels = labels->second;

        entries.push_back (std::move (entry));
    }
    return entries;
}

} // namespace

std::string CatalogEntry::scriptSource () const
{
    std::string source;
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
        source += "# mpvst-module: " + package + "." + module + "\n";
        source += "import mpvst_adapter\n";
        source += "mpvst_adapter.run(\"" + package + "." + module + "\")\n";
    }
    return source;
}

const std::vector<CatalogEntry>& catalogPlugins ()
{
    // Read once, on first use, and kept for the life of the process: the
    // factory hands out a pointer to an entry as a class's context, so the
    // vector has to outlive every instance created from it.
    static const std::vector<CatalogEntry> entries = readCatalog ();
    return entries;
}

} // namespace PyDevices::MicroPythonVST3
