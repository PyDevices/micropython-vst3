"""Find every plug-in declared in audioinstruments and audioeffects.

Run it with the engine, from the folder it lives in:

    micropython-vst-engine.exe scan_plugins.py --write

That needs no Python installed and behaves the same on Windows and Linux,
which is the whole reason it is written for the engine rather than for a
system interpreter. Run it after installing, and again after adding or
editing a script; the DAW picks up the result on its next rescan.

It writes one file, `../Resources/moduleinfo.json`: the list a host reads to
enumerate classes without loading the binary, and the same list the plug-in
binary reads at load to decide which classes it offers. One file, so there is
nothing for a second one to disagree with.

Reads the files as text rather than importing them - what is wanted is what
each module *declares*, and text gives the same answer without paying for a
synth's import or caring whether one is importable at all.

Where the fields live differs by package, and that is deliberate: an
instrument is one plug-in per file, so its fields sit at module level; an
effect file holds several classes, so each class carries its own. VENDOR is
always module level, because a file comes from one author.

NAME is the only required field. Everything else defaults, and anything
without a NAME is not a plug-in and is skipped - which is also how a helper
class or a base class stays out of the list without needing to be excluded
by name.
"""

import binascii
import hashlib
import json
import os
import sys

# The package a file came from decides whether it is an instrument or an
# effect. Nothing inside the file gets a say, because this is what sets the
# bus layout - an effect has an audio input and an instrument does not - and
# a plug-in that disagrees with its own buses does not load.
PACKAGES = (
    ("audioinstruments", "Instrument", "module"),
    ("audioeffects", "Fx", "class"),
)

DEFAULT_VENDOR = "PyDevices"
DEFAULT_VERSION = "0.0.1"

# Fields of the module itself rather than of any one plug-in. These describe
# the binary, not the scripts, so they are read back out of the moduleinfo the
# build already wrote rather than restated here - a version bump then reaches
# this file without anyone remembering to edit it. The values below are only
# the fallback for when there is nothing to read.
MODULE_DEFAULTS = {
    "Name": "MicroPythonVST3",
    "Version": "0.0.1",
    "Vendor": "PyDevices",
    "URL": "https://pydevices.github.io/",
    "E-Mail": "",
    "SDKVersion": "VST 3.8.1",
    "Unicode": True,
    "Classes Discardable": False,
    "Component Non Discardable": False,
}

# Where the generated file goes, relative to this script. Hosts read it from
# the bundle's Resources folder to enumerate classes without loading the
# binary.
MODULE_INFO = "../Resources/moduleinfo.json"

# Which file and class a plug-in came from, written beside its class entry.
#
# It is a comment because moduleinfo.json is JSON5 and the Steinberg
# validator takes a closed set of keys - an added one fails with "Unexpected
# key", and every standard field it would fit in is cross-checked against the
# live factory, so bending one would put the path in front of the user. A
# comment validates and stays invisible. The path is always forward-slashed:
# it is a key something else looks up, and it has to read the same on both
# platforms.
SOURCE_COMMENT = "// mpvst-source:"

# The macro names the plug-in's parameters carry, written the same way and
# for the same reason. These are wanted in the host's process, where a class
# is registered and its parameters are named, and there is no sidecar there
# to ask - so they travel with the class rather than being fetched later.
MACROS_COMMENT = "// mpvst-macros:"

# A class ID is 128 fixed bits and a plug-in is identified by arbitrary-length
# text, so something has to compress one into the other deterministically -
# which is all the hash is for. The seed is the file's path plus its NAME:
# the path because the filesystem already guarantees it unique, so a user who
# copies one of ours and edits it gets a distinct plug-in for free; the NAME
# because one effect file declares several.
#
# Renaming a file therefore makes a different plug-in and orphans projects
# that used the old one. That is the documented rule, and it is the price of
# not having to hand out identifiers.
CID_NAMESPACE = "PyDevices/micropython-vst3/plugin/1"

# The classes compiled into the binary. The scan cannot discover them - they
# come from no script - and a moduleinfo that omits them is not merely
# incomplete: a host that trusts the file never sees them at all, which is
# how the developer-loop plug-in went missing from projects that used it.
#
# The two controller classes here are also the ones every discovered plug-in
# names. One controller implementation serves all of them and learns which
# instrument it is from the component state, never from its own class, so
# there is nothing for a per-plug-in controller class to be.
#
# Held as identity only. Vendor, version and SDK version come from the module
# fields like everything else, so the only thing that can go stale is a CID
# or a name, and `moduleinfotool -validate` fails loudly when one does. The
# CIDs are src/plugin/source/cids.h and the names are factory.cpp.
BUILTIN_CLASSES = (
    ("60A40168727C4E7DAAF808B790961DAA",
     "MicroPython Script Host", ["Instrument", "Synth"]),
    ("04B27009082444D48FE82CB5A7C810FD",
     "MicroPython Script Host Controller", None),
    ("910677E28594410985AD7A76CA68106C",
     "MicroPython Script Host (Fx)", ["Fx"]),
    ("16695D06FA2F4F9585FE0B7165515F68",
     "MicroPython Script Host (Fx) Controller", None),
)

FIELDS = ("NAME", "DISPLAY_NAME", "CATEGORIES", "VERSION", "VENDOR",
          "MACRO_LABELS")


def here():
    """The directory this script was run from, whatever the CWD is."""
    path = sys.argv[0].replace("\\", "/")
    slash = path.rfind("/")
    return path[:slash] if slash >= 0 else "."


def quoted(text):
    """Every single- or double-quoted string in `text`, in order."""
    out = []
    index = 0
    while index < len(text):
        char = text[index]
        if char in "'\"":
            end = text.find(char, index + 1)
            if end < 0:
                break
            out.append(text[index + 1:end])
            index = end + 1
        else:
            index += 1
    return out


def read_metadata(path):
    """(module fields, {class name: fields}) declared in one file.

    Scope comes from indentation: an assignment in column zero belongs to the
    module, an indented one to the class above it. A value is taken as the
    strings it quotes, so a name and a tuple of categories are read the same
    way and a wrapped tuple is read whole.
    """
    module = {}
    classes = {}
    owner = None
    collecting = None
    field = None
    scope = None

    with open(path) as handle:
        for line in handle:
            stripped = line.strip()
            if collecting is None:
                indent = len(line) - len(line.lstrip())
                if stripped.startswith("class ") and indent == 0:
                    owner = stripped[6:].split("(")[0].split(":")[0].strip()
                    classes.setdefault(owner, {})
                    continue
                name = stripped.split("=")[0].strip()
                if name not in FIELDS or "=" not in stripped:
                    continue
                field = name
                scope = module if indent == 0 else classes.get(owner)
                if scope is None:
                    continue
                collecting = stripped.split("=", 1)[1]
            else:
                collecting += " " + stripped
            # Keep taking lines until the brackets close, so a wrapped tuple
            # is read whole rather than truncated at the first newline.
            depth = collecting.count("(") + collecting.count("[")
            depth -= collecting.count(")") + collecting.count("]")
            if depth <= 0:
                scope[field] = quoted(collecting)
                collecting = None
    return module, classes


def plugins(root):
    """Every declared plug-in, as a flat list of dicts."""
    found = []
    for package, kind, where in PACKAGES:
        directory = root + "/" + package
        try:
            names = sorted(n for n in os.listdir(directory)
                           if n.endswith(".py"))
        except OSError:
            print("%s: not found beside this script" % package)
            continue

        for filename in names:
            module, classes = read_metadata(directory + "/" + filename)
            sources = ([(None, module)] if where == "module"
                       else sorted(classes.items()))
            for owner, fields in sources:
                name = fields.get("NAME")
                if not name:
                    continue  # not a plug-in: a helper, a base, or unlabelled
                found.append({
                    "package": package,
                    "file": filename,
                    "module": filename[:-3],
                    "class": owner,
                    "kind": kind,
                    "name": name[0],
                    "display_name": (fields.get("DISPLAY_NAME") or name)[0],
                    # The package supplies the top-level category; the file
                    # only ever says which kind of instrument or effect.
                    "categories": [kind] + fields.get("CATEGORIES", []),
                    "version": (fields.get("VERSION")
                                or module.get("VERSION")
                                or [DEFAULT_VERSION])[0],
                    "vendor": (module.get("VENDOR") or [DEFAULT_VENDOR])[0],
                    "macros": fields.get("MACRO_LABELS", []),
                })
    return found


def strip_trailing_commas(text):
    """JSON5 allows a comma before a closing bracket; `json` does not.

    The SDK's own writer emits them, so anything reading a moduleinfo the
    build produced has to take them out first. Quoted text is stepped over,
    because a comma inside a string is data.
    """
    out = []
    index = 0
    while index < len(text):
        char = text[index]
        if char == '"':
            end = index + 1
            while end < len(text) and text[end] != '"':
                end += 2 if text[end] == "\\" else 1
            out.append(text[index:end + 1])
            index = end + 1
            continue
        if char == ",":
            look = index + 1
            while look < len(text) and text[look] in " \t\r\n":
                look += 1
            if look < len(text) and text[look] in "}]":
                index += 1
                continue
        out.append(char)
        index += 1
    return "".join(out)


def header_object(text):
    """Everything before the class list, as a dict.

    Only the header is parsed. The class array is the large part of the file
    and none of it is wanted here, so cutting before it keeps a hundred
    kilobytes of JSON out of the engine's heap.
    """
    cut = text.find('"Classes"')
    if cut < 0:
        return None
    head = text[:cut].rstrip()
    if head.endswith(","):
        head = head[:-1]
    try:
        return json.loads(strip_trailing_commas(head) + "}")
    except ValueError:
        return None


def module_fields(path):
    """The binary's own identity, read from the moduleinfo the build wrote.

    A version bump then reaches this file without anyone remembering to edit
    it, and reading our own previous output yields the same answers, so
    re-running this is idempotent. MODULE_DEFAULTS is only the fallback for
    when there is nothing to read.
    """
    fields = dict(MODULE_DEFAULTS)
    try:
        with open(path) as handle:
            text = handle.read()
    except OSError:
        return fields  # nothing written yet, or generation turned off

    header = header_object(text) or {}
    factory = header.get("Factory Info") or {}
    flags = factory.get("Flags") or {}
    for source, keys in ((header, ("Name", "Version")),
                         (factory, ("Vendor", "URL", "E-Mail")),
                         (flags, ("Unicode", "Classes Discardable",
                                  "Component Non Discardable"))):
        for key in keys:
            if key in source:
                fields[key] = source[key]

    # SDKVersion belongs to a class rather than to the header, so it is the
    # one value that has to be found in the body.
    marker = text.find('"SDKVersion"')
    if marker >= 0:
        line = text[marker:text.find("\n", marker)]
        found = quoted(line[len('"SDKVersion"'):])
        if found:
            fields["SDKVersion"] = found[0]
    return fields


def cid(path, name, role):
    seed = "%s\0%s\0%s\0%s" % (CID_NAMESPACE, path, name, role)
    digest = hashlib.sha256(seed.encode("utf-8")).digest()[:16]
    return binascii.hexlify(digest).decode("ascii").upper()


def comment_lines(entry):
    """The comments that go above a class entry, one per line."""
    where = entry["package"] + "/" + entry["file"]
    if entry["class"]:
        where += "#" + entry["class"]
    lines = SOURCE_COMMENT + " " + where + "\n"
    if entry["macros"]:
        lines += MACROS_COMMENT + " " + " | ".join(entry["macros"]) + "\n"
    return lines


def class_object(identifier, name, categories, vendor, version, module):
    """One entry of the "Classes" array.

    `categories` is None for a controller class, which is both what makes it
    a controller here and why it carries no sub-categories: a controller is
    not something a host files under Synth or Delay.
    """
    fields = {
        "CID": identifier,
        "Category": ("Audio Module Class" if categories is not None
                     else "Component Controller Class"),
        "Name": name,
        "Vendor": vendor,
        "Version": version,
        "SDKVersion": module["SDKVersion"],
        "Class Flags": 0,
        "Cardinality": 2147483647,
        "Snapshots": [],
    }
    if categories is not None:
        fields["Sub Categories"] = categories
    return fields


def module_info(write, entries, module):
    """Write the whole moduleinfo.json.

    Streamed a class at a time rather than dumped in one call: ninety-odd
    plug-ins is a couple of hundred kilobytes of JSON and the engine's heap
    is not sized to hold that twice while dumps assembles it. Every piece
    still goes through json.dumps, so quoting, escaping and the difference
    between True and true are the library's problem and not this file's.
    """
    header = json.dumps({
        "Name": module["Name"],
        "Version": module["Version"],
        "Factory Info": {
            "Vendor": module["Vendor"],
            "URL": module["URL"],
            "E-Mail": module["E-Mail"],
            "Flags": {
                "Unicode": module["Unicode"],
                "Classes Discardable": module["Classes Discardable"],
                "Component Non Discardable":
                    module["Component Non Discardable"],
            },
        },
    })
    # The class list is spliced in rather than dumped with the header, which
    # is what lets it stream and what lets a comment sit between entries.
    # dumps has just closed the object; reopen it.
    write(header[:-1] + ', "Classes": [\n')

    separator = ""
    for identifier, name, categories in BUILTIN_CLASSES:
        write(separator + json.dumps(class_object(
            identifier, name, categories, module["Vendor"],
            module["Version"], module)))
        separator = ",\n"
    for entry in entries:
        write(separator + comment_lines(entry))
        write(json.dumps(class_object(
            entry["cid"], entry["display_name"], entry["categories"],
            entry["vendor"], entry["version"], module)))
        separator = ",\n"
    write("\n]}\n")


def main():
    root = here()
    module = module_fields(root + "/" + MODULE_INFO)
    entries = plugins(root)
    for entry in entries:
        path = entry["package"] + "/" + entry["file"]
        entry["cid"] = cid(path, entry["name"], "processor")

    if "--json" in sys.argv:
        module_info(sys.stdout.write, entries, module)
        return
    if "--write" in sys.argv:
        with open(root + "/" + MODULE_INFO, "w") as handle:
            module_info(handle.write, entries, module)
        print("%d plug-ins: wrote %s (%d classes)"
              % (len(entries), MODULE_INFO,
                 len(entries) + len(BUILTIN_CLASSES)))
        return

    for entry in entries:
        where = entry["file"]
        if entry["class"]:
            where += "  " + entry["class"]
        print("%-28s %-20s %-22s %-8s %-10s %2d macros  %s"
              % (where, entry["name"], "|".join(entry["categories"]),
                 entry["version"], entry["vendor"], len(entry["macros"]),
                 entry["cid"]))
    print()
    print("module: %s %s, %s <%s>"
          % (module["Name"], module["Version"], module["Vendor"],
             module["URL"]))
    print("%d plug-ins declared. --write to save them, --json to see the "
          "file that would be written." % len(entries))


main()
