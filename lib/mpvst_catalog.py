"""Write `catalog.json`: everything a tool needs to build a project by hand.

Run it with the engine, from the folder it lives in, the same way as the
scanner and right after it:

    mpvst-engine.exe -X heapsize=64M mpvst_catalog.py

The heap flag is not optional. The engine defaults to about 2 MB free, and
reading 98 modules' declarations runs out of it - on Windows, four of the
drum machines failed to allocate even when each module is released before the
next is read. This is a build-time tool with no audio deadline, so it is
given room rather than made clever.

`moduleinfo.json` next door is Steinberg's file and answers to Steinberg's
reader, which accepts no field we invent - not inside a class, not even at the
top level. So the only place our own metadata could go was JSON5 comments,
which is why the scanner writes them, and why a tool wanting patches has had
to scrape comments with a regex or import the libraries itself.

This file is the alternative: ours, plain JSON, no constraints. One read gives
a project generator the class ID to name in a `.RPP`, the macro layout to fill
in, and the patches to choose from.

Where the two files differ in method: the scanner reads the library sources as
*text*, so a module that will not import cannot break the list a host depends
on. Patches cannot be had that way - `PATCHES` is a dict of tuples and parsing
it out of source is the kind of agreement that breaks quietly. So this script
imports for real, and is allowed to fail: the class list and the class IDs
still come from the scanner's text pass, so they cannot disagree with
`moduleinfo.json`, and a module that will not import loses its patches rather
than taking the file down.
"""

import gc
import json
import sys

import mpvst_scan_plugins as scan

CATALOG = "../Resources/catalog.json"
FORMAT = 1


def forget(package, file_stem):
    """Drop a module again once its declarations have been read.

    98 modules imported into one interpreter is more than the engine's heap
    holds - tr808 and tr909 failed to allocate at the tail of the first run
    that tried it. Nothing here needs two modules live at once, so each is
    released before the next is loaded and peak memory stays flat.
    """
    for key in (package + "." + file_stem, file_stem):
        if key in sys.modules:
            del sys.modules[key]
    gc.collect()


def imported(package, file_stem, class_name):
    """The live class or module an entry names, or None if it will not load."""
    try:
        module = __import__(package + "." + file_stem, None, None, (file_stem,))
    except Exception as error:            # noqa: BLE001 - any import failure
        sys.stderr.write("catalog: %s/%s did not import: %s\n"
                         % (package, file_stem, error))
        return None
    if class_name:
        return getattr(module, class_name, None)
    return module


def declared(obj, name, default):
    value = getattr(obj, name, default)
    return default if value is None else value


def patches(obj):
    """`{index: (label, values)}` as `[{index, name, macros}]`, in order."""
    out = []
    for index in sorted(declared(obj, "PATCHES", {})):
        entry = obj.PATCHES[index]
        label, values = (entry[0], entry[1]) if isinstance(entry, tuple) \
            else (str(entry), ())
        out.append({"index": index, "name": label, "macros": list(values)})
    return out


def note_map(obj):
    """`NOTE_MAP` as [[midi, label], ...] - which key plays which drum.

    Percussion declares it and a generator needs it to write notes at all;
    dropping it makes a drum machine unplayable from a generated project.
    """
    return [[int(note), str(label)]
            for note, label in declared(obj, "NOTE_MAP", ())]


def ranges(obj):
    """Macro ranges where a class publishes them, as [low, high] or null."""
    published = declared(obj, "_MACRO_RANGES", ())
    out = []
    for item in published:
        out.append([item[0], item[1]] if len(item) >= 2 else None)
    return out


def entry_for(record):
    package = record["package"]
    obj = imported(package, record["file"].rsplit(".", 1)[0], record["class"])
    built = {
        "name": record["name"],
        "cid": record["cid"],
        "kind": "effect" if package == "audioeffects" else "instrument",
        "source": "%s/%s%s" % (package, record["file"],
                               "#" + record["class"] if record["class"] else ""),
        "categories": list(record["categories"]),
        "vendor": record["vendor"],
        "version": record["version"],
        "macro_labels": list(record["macros"]),
    }
    if obj is None:
        built["imported"] = False
        return built
    built["imported"] = True
    built["display_name"] = declared(obj, "DISPLAY_NAME", record["name"])
    built["macro_ranges"] = ranges(obj)
    built["patches"] = patches(obj)
    mapped = note_map(obj)
    if mapped:
        built["note_map"] = mapped
    forget(package, record["file"].rsplit(".", 1)[0])
    return built


def main():
    root = scan.here()
    records = scan.plugins(root)
    for record in records:
        path = record["package"] + "/" + record["file"]
        record["cid"] = scan.cid(path, record["name"], "processor")

    catalog = {
        "format": FORMAT,
        "generated_from": "mpvst_scan_plugins.py + a live import",
        "classes": [entry_for(record) for record in records],
    }
    with open(root + "/" + CATALOG, "w") as handle:
        json.dump(catalog, handle)
    missing = [item["name"] for item in catalog["classes"]
               if not item["imported"]]
    print("%d classes: wrote %s" % (len(catalog["classes"]), CATALOG))
    if missing:
        # Not fatal - the file is still useful - but a class we ship that will
        # not import is a real defect, so it leaves in the exit code for a
        # caller that cares. The installers do not; the test does.
        print("%d did not import: %s" % (len(missing), ", ".join(missing)))
        # Exit 0 unless asked otherwise: the build and both installers run
        # this, and a tools file that cannot be written is not a reason to
        # fail an install. --strict is for the test, which should care.
        if "--strict" in sys.argv:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
