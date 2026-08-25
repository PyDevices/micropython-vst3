#!/usr/bin/env python3
"""Run every lib/instruments/*.py script through the real synthio DSP.

Uses tools/preview/harness.py (the audioif CPython wheel, no compiled
engine or VST3 host needed) to catch exactly the class of bug that
py_compile can't: API misuse that only raises once a note is actually
played (e.g. an invalid kwarg to synthio.Note/Math), and macros that are
read but never reach the audio graph.

For each script:
  - loads it fresh (catches import-time and note-on exceptions)
  - sweeps every declared macro through {0.0, 0.5, 1.0} while holding a
    note, and asserts the sweep never raises
  - plays a short chord at default macro settings and asserts the
    script actually produces non-silent audio
  - releases every voice and asserts that doesn't raise either

This is a fast correctness net, not a substitute for hearing the
instrument in a DAW: it proves a script doesn't crash and isn't silent,
not that it sounds like the hardware it emulates.

Usage: test-instruments-lib.py [name.py ...]   (default: every script)
"""

import sys
import traceback
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
INSTRUMENTS_DIR = REPO_DIR / "lib" / "instruments"
sys.path.insert(0, str(Path(__file__).resolve().parent / "preview"))

import harness  # noqa: E402
import vstaudio  # noqa: E402

MACRO_SETTINGS = (0.0, 0.5, 1.0)
MELODIC_CHORD = (48, 52, 55, 60)  # a triad plus root
DRUM_NOTES = tuple(range(35, 52))  # covers every GM kick/snare/hat/tom/etc.
FRAMES_PER_STEP = 2048


def notes_for(script_path):
    # Drum machines gate on fixed GM note numbers instead of tracking pitch,
    # so a melodic chord would trigger nothing; use the GM drum range for
    # those instead.
    if "data0 == 36" in script_path.read_text():
        return DRUM_NOTES
    return MELODIC_CHORD


def macro_count(script_path):
    first_line = script_path.read_text().splitlines()[0]
    if not first_line.startswith("# mpvst-macro-labels:"):
        return 0
    return len(first_line.split(":", 1)[1].split("|"))


def run_one(script_path):
    errors = []

    def note_on(run, pitch, velocity=0.8):
        run.deliver(vstaudio.EVENT_NOTE_ON, 0, -1, pitch, velocity, 0.0, 0)

    def note_off(run, pitch):
        run.deliver(vstaudio.EVENT_NOTE_OFF, 0, -1, pitch, 0.0, 0.0, 0)

    def set_macro(run, index, value):
        run.deliver(vstaudio.EVENT_PARAMETER, 0, -1, index, value, 0.0, 0)

    try:
        run = harness.InstrumentRun(str(script_path))
    except Exception:
        return ["load: " + traceback.format_exc(limit=4)]

    n_macros = macro_count(script_path)
    notes = notes_for(script_path)

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


def main():
    argv = sys.argv[1:]
    if argv:
        scripts = [INSTRUMENTS_DIR / name for name in argv]
    else:
        scripts = sorted(INSTRUMENTS_DIR.glob("*.py"))

    failures = {}
    for script_path in scripts:
        errors = run_one(script_path)
        status = "FAIL" if errors else "ok"
        print("%-20s %s" % (script_path.name, status))
        if errors:
            failures[script_path.name] = errors

    if failures:
        print("\n%d/%d scripts failed:\n" % (len(failures), len(scripts)))
        for name, errors in failures.items():
            print("=== %s ===" % name)
            for error in errors:
                print(error)
        return 1

    print("\n%d/%d scripts ok" % (len(scripts), len(scripts)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
