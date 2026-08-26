#!/usr/bin/env python3
"""Run every instrument script through the real synthio DSP.

Uses tools/harness.py (the audioif CPython wheel, no compiled engine or
VST3 host needed) to catch exactly the class of bug that py_compile can't:
API misuse that only raises once a note is actually played (e.g. an
invalid kwarg to synthio.Note/Math), and macros that are read but never
reach the audio graph.

Two sets of scripts, driven the same way. lib/instruments/*.py are
generated loaders, so running them covers the whole sidecar path bar the
engine: shim -> mpvst_adapter -> audioinstruments. That is deliberate.
audioif holds the instruments themselves to byte-exact parity goldens,
which is a far stronger check than anything here; what is untested
without this is the seam - the adapter, the staged import, the generated
label line.

The soundtrack's piece-private instruments are whole scripts rather than
loaders, and they run through the same path because that is how the
plug-in loads them: as `__main__`, ending in a call to the adapter.

For each script:
  - checks its macro-label line against the MACRO_LABELS it declares (a
    shim's are generated, a private instrument's are two literals side by
    side), and loads it fresh, catching import-time and note-on errors
  - sweeps every declared macro through {0.0, 0.5, 1.0} while holding a
    note, and asserts the sweep never raises
  - plays a short chord - or the machine's own mapped voices, for a drum
    machine - at default macro settings, and asserts the script actually
    produces non-silent audio
  - releases every voice and asserts that doesn't raise either

This is a fast correctness net, not a substitute for hearing the
instrument in a DAW: it proves a script doesn't crash and isn't silent,
not that it sounds like the hardware it emulates.

Usage: test-instruments-lib.py [name.py ...]   (default: every script)
"""

import importlib.util
import sys
import traceback
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
INSTRUMENTS_DIR = REPO_DIR / "lib" / "instruments"
SOUNDTRACK_DIR = REPO_DIR / "soundtrack"
sys.path.insert(0, str(Path(__file__).resolve().parent))

import harness  # noqa: E402  (also puts audioif and audioif/lib on the path)
import vstaudio  # noqa: E402
from piece import MODULE_PREFIX, module_of  # noqa: E402

MACRO_SETTINGS = (0.0, 0.5, 1.0)
MELODIC_CHORD = (48, 52, 55, 60)  # a triad plus root
FRAMES_PER_STEP = 2048


def instrument_module(script_path):
    """What the script declares about itself: MACRO_LABELS, NOTE_MAP.

    A shim declares nothing of its own, so the module it loads is
    imported instead. A private instrument is imported from its own path
    - which runs its module body but not its `__main__` guard, so nothing
    is attached to the host.
    """
    name = module_of(script_path)
    if name is not None:
        __import__(name)
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        "instrument_" + script_path.stem, script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def notes_for(module):
    # A drum machine gates on fixed note numbers rather than tracking
    # pitch, so a melodic chord would trigger nothing. It says which
    # numbers it answers; play those.
    note_map = getattr(module, "NOTE_MAP", None)
    if note_map:
        return tuple(entry[0] for entry in note_map)
    return MELODIC_CHORD


def check_label_line(script_path, module):
    """The line the plug-in parses must match the MACRO_LABELS in force.

    The plug-in reads its macro names straight out of the embedded script
    source, so every script carries them as a comment as well as a tuple.
    Two places, one truth - this is what keeps them the same.
    """
    first = script_path.read_text().split("\n", 1)[0]
    expected = "# mpvst-macro-labels: " + " | ".join(module.MACRO_LABELS)
    if first != expected:
        fix = ("run tools/generate_shims.py" if module_of(script_path)
               else "edit the comment or MACRO_LABELS so they agree")
        return ["macro labels disagree - %s\n  file:   %s\n  labels: %s"
                % (fix, first, expected)]
    return []


def run_one(script_path):
    errors = []

    def note_on(run, pitch, velocity=0.8):
        run.deliver(vstaudio.EVENT_NOTE_ON, 0, -1, pitch, velocity, 0.0, 0)

    def note_off(run, pitch):
        run.deliver(vstaudio.EVENT_NOTE_OFF, 0, -1, pitch, 0.0, 0.0, 0)

    def set_macro(run, index, value):
        run.deliver(vstaudio.EVENT_PARAMETER, 0, -1, index, value, 0.0, 0)

    try:
        module = instrument_module(script_path)
    except Exception:
        return ["module: " + traceback.format_exc(limit=4)]

    errors += check_label_line(script_path, module)

    try:
        run = harness.InstrumentRun(str(script_path))
    except Exception:
        return errors + ["load: " + traceback.format_exc(limit=4)]

    n_macros = len(module.MACRO_LABELS)
    notes = notes_for(module)

    # Macro sweep: every macro at every setting, each under active notes,
    # to catch bugs that only fire at a particular knob position.
    try:
        for pitch in notes:
            note_on(run, pitch)
        for setting in MACRO_SETTINGS:
            for index in range(n_macros):
                set_macro(run, index, setting)
                run.pull_frames(FRAMES_PER_STEP)
        for pitch in notes:
            note_off(run, pitch)
        run.pull_frames(FRAMES_PER_STEP)
    except Exception:
        errors.append("macro sweep: " + traceback.format_exc(limit=4))

    # Fresh instance at default settings: must produce audible output.
    try:
        run = harness.InstrumentRun(str(script_path))
        for pitch in notes:
            note_on(run, pitch)
        pcm = run.pull_frames(FRAMES_PER_STEP * 4)
        peak, rms = harness.peak_rms(pcm)
        for pitch in notes:
            note_off(run, pitch)
        run.pull_frames(FRAMES_PER_STEP)
        if peak < 0.001:
            errors.append("silent: peak=%.6f rms=%.6f at default macros" %
                          (peak, rms))
    except Exception:
        errors.append("default chord: " + traceback.format_exc(limit=4))

    return errors


def every_script():
    """Every instrument script, labelled by where it lives."""
    for path in sorted(INSTRUMENTS_DIR.glob("*.py")):
        yield path.stem, path
    for directory in sorted(SOUNDTRACK_DIR.glob("*/instruments")):
        for path in sorted(directory.glob("*.py")):
            yield "%s/%s" % (directory.parent.name, path.stem), path


def main():
    wanted = {name[:-3] if name.endswith(".py") else name
              for name in sys.argv[1:]}
    scripts = [(label, path) for label, path in every_script()
               if not wanted or wanted & {label, path.stem}]
    if wanted and not scripts:
        raise SystemExit("no such instrument: %s" % ", ".join(sorted(wanted)))

    failures = {}
    for label, script_path in scripts:
        errors = run_one(script_path)
        status = "FAIL" if errors else "ok"
        print("%-28s %s" % (label, status))
        if errors:
            failures[label] = errors

    if failures:
        print("\n%d/%d scripts failed:\n" % (len(failures), len(scripts)))
        for label, errors in failures.items():
            print("=== %s ===" % label)
            for error in errors:
                print(error)
        return 1

    print("\n%d/%d scripts ok" % (len(scripts), len(scripts)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
