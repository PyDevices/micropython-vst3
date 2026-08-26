#!/usr/bin/env python3
"""Give every instrument a Patch 1 describing the sound it already makes.

Every instrument must declare at least one patch: piece.py resolves an
unset macro to the instrument's Patch 1 rather than to the middle of its
range, and the middle of a range is not "off" and not what the author
intended. That contract is only safe if the patch is genuinely the
instrument's designed sound, so this derives it rather than inventing it.

An instrument's own defaults already are that sound - volume = 0.8,
cutoff_base = 2000.0. For each macro this:

  1. builds the instrument and snapshots every number it can reach,
  2. feeds the macro 0 then 127 to see which of them it moves, which
     discovers the macro -> parameter binding without parsing anything,
  3. scans all 128 settings and keeps the one that puts those parameters
     closest to the snapshot.

Patch values are MIDI integers, so a scan is exact where a search would
only approach: there are 128 settings and it tries all of them. Anything
unbound, ambiguous or unreachable is reported and never guessed - an
unreachable default means the macro cannot restore the designed sound,
which is a bug in the instrument, not something to paper over.

Two things make this different from probing a module's globals, which is
what it used to do. An instrument's parameters live in the closure that
`create()` builds, so they are read through `handle_event`'s free
variables - the same per-instance state, reached the only way it can be.
And `create()` ends by applying Patch 1, which would make deriving Patch 1
circular, so the instrument is built with that step suppressed: what gets
measured is the sound its own code leaves behind.

An instrument that already declares a patch 0 keeps it. Not every patch 0
is derived - minimoog's is one of three designed patches, and create()
applies it so the instrument starts there - so overwriting one has to be
asked for. `--check` reports the difference either way, marked `~`.

Usage:
    derive_patches.py                    report, write nothing
    derive_patches.py --write            fill in a missing PATCHES block
    derive_patches.py --write --force    rederive patch 0 as well
    derive_patches.py --write minimoog ms20
"""

import ast
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

from piece import AUDIOIF_LIB  # noqa: E402

# The packages, and the CPython twins of the native modules they import
# (synthio, audiocore, ...) beside them. Same sibling-checkout rule as
# harness.py, which is where every other tool gets its audioif from.
sys.path.insert(0, str(AUDIOIF_LIB))
sys.path.insert(0, str(AUDIOIF_LIB.parent))

from audioinstruments._support import Instrument, static_transport  # noqa: E402

SAMPLE_RATE = 48000

#: Summed squared relative error above which a macro is worth reporting.
#: There are only 128 settings, so a macro whose parameter is mapped
#: logarithmically over a wide range lands up to half a step away from its
#: default however well it is derived - 10% of a step on a decade-wide
#: sweep. That is the grid's resolution, not a defect. What this catches is
#: a macro that misses by a lot: a default outside the range it can reach,
#: or several parameters it cannot satisfy at once.
TOLERANCE = 0.01

#: Where the instruments that own patches live. The shims in
#: lib/instruments declare none of their own - they load these.
DIRS = [AUDIOIF_LIB / "audioinstruments",
        REPO / "soundtrack" / "Automata" / "instruments",
        REPO / "soundtrack" / "Perihelion" / "instruments"]


def load(path):
    """Import an instrument module without running any __main__ guard."""
    spec = importlib.util.spec_from_file_location("derive_" + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(module):
    """The instrument as its own code leaves it, before Patch 1 is applied.

    create() finishes by applying Patch 1 so that a fresh instance and
    Patch 1 are the same thing. That is exactly what makes it circular to
    measure here, so the step is suppressed for the length of the call.
    """
    original = Instrument.program_change
    Instrument.program_change = lambda self, *args, **kwargs: None
    try:
        return module.create(SAMPLE_RATE, transport=static_transport)
    finally:
        Instrument.program_change = original


def scalars(instrument):
    """Every number a macro could plausibly be holding.

    The instrument's parameters are the free variables of its event
    handler - that is what `create()` closed over. Several instruments
    park their parameters on synthio objects instead (cut_base.a,
    verb.mix), so walk one level into those as well. Attribute reads on
    them can raise or be computed properties, hence the guards.
    """
    handler = instrument._handle
    out = {}
    cells = handler.__closure__ or ()
    for key, cell in zip(handler.__code__.co_freevars, cells):
        try:
            value = cell.cell_contents
        except ValueError:                                 # not yet bound
            continue
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            out[key] = value
            continue
        if isinstance(value, (str, bytes, list, tuple, dict, set)):
            continue
        if isinstance(value, type) or callable(value):
            continue
        for attr in dir(value):
            if attr.startswith("_"):
                continue
            try:
                inner = getattr(value, attr)
            except Exception:                              # noqa: BLE001
                continue
            if isinstance(inner, (int, float)) and not isinstance(inner, bool):
                out["%s.%s" % (key, attr)] = inner
    return out


def error_against(state, defaults, keys):
    """Summed relative distance from the instrument's own defaults."""
    total = 0.0
    for key in keys:
        target = defaults[key]
        total += ((state.get(key, target) - target)
                  / (abs(target) if target else 1.0)) ** 2
    return total


def derive(path):
    """(values, notes) for one instrument, or (None, reason)."""
    module = load(path)
    labels = getattr(module, "MACRO_LABELS", None)
    if not labels:
        return None, "no MACRO_LABELS"
    instrument = build(module)
    defaults = scalars(instrument)

    # Some of what we can see moves on its own - an LFO's current value, a
    # phase accumulator. Reading twice without touching anything identifies
    # those, so they are never mistaken for something a macro drives.
    volatile = set()
    for _ in range(3):
        before = scalars(instrument)
        after = scalars(instrument)
        volatile |= {k for k in before if before.get(k) != after.get(k)}

    values, notes = [], []
    for index in range(min(16, len(labels))):
        instrument.set_macro(index, 0)
        low = scalars(instrument)
        instrument.set_macro(index, 127)
        high = scalars(instrument)
        moved = [k for k in defaults
                 if k not in volatile and k in low and low[k] != high[k]]
        if not moved:
            values.append(64)
            notes.append("%d:%s:unbound" % (index, labels[index]))
            instrument.set_macro(index, 64)
            continue

        best, best_error = 0, None
        for setting in range(128):
            instrument.set_macro(index, setting)
            error = error_against(scalars(instrument), defaults, moved)
            # Ties go to the higher setting, which is round-half-up: a
            # default sitting exactly between two steps of a linear macro
            # is equally far from both, and 64 is the answer everyone
            # expects for the middle of 0-127.
            if best_error is None or error <= best_error:
                best, best_error = setting, error
        instrument.set_macro(index, best)
        values.append(best)

        if best_error > TOLERANCE:
            # Landing on an end stop means the default is outside the range
            # the macro can reach at all, which is a different bug from a
            # macro that can get close but not exactly there.
            kind = "unreachable" if best in (0, 127) else "approx"
            state = scalars(instrument)
            worst = max(moved, key=lambda k: abs(state.get(k, defaults[k])
                                                 - defaults[k])
                        / (abs(defaults[k]) or 1.0))
            target = defaults[worst]
            notes.append(
                "%d:%s:%s %s=%.6g wanted %.6g (%.0f%% off%s)"
                % (index, labels[index], kind, worst,
                   state.get(worst, target), target,
                   100.0 * abs(state.get(worst, target) - target)
                   / (abs(target) or 1.0),
                   ", %d params" % len(moved) if len(moved) > 1 else ""))
    return values, notes


def render(patches, values):
    """The PATCHES block, with patch 0's values replaced by `values`.

    Every other patch is carried through unchanged: this derives the sound
    an instrument makes by default, and says nothing about the ones
    someone designed on top of it.
    """
    lines = ["# Patch 0 is the sound this instrument's defaults describe, so"
             " a fresh",
             "# instance and patch 0 are the same thing - create() applies"
             " it. A macro",
             "# a caller does not set resolves here rather than to the middle"
             " of its",
             "# range.",
             "PATCHES = {"]
    for key in sorted(patches):
        name, existing = patches[key]
        numbers = list(values) if key == 0 else list(existing)
        opening = "    %d: (%r, (" % (key, name)
        pad = " " * (len(opening) - 4 + 4)
        chunk = opening
        for position, value in enumerate(numbers):
            piece = ("%d," % value) if position == 0 else (" %d," % value)
            if len(chunk) + len(piece) > 76:
                lines.append(chunk)
                chunk = pad + ("%d," % value)
            else:
                chunk += piece
        # A one-macro instrument keeps its trailing comma, or ("Init", (56))
        # is a bare int rather than a tuple of one.
        lines.append((chunk if len(numbers) == 1 else chunk.rstrip(",")) + ")),")
    lines.append("}")
    return "\n".join(lines)


def existing_patches(path):
    """((start line, end line), {index: (name, values)}) for PATCHES."""
    text = path.read_text()
    tree = ast.parse(text, str(path))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "PATCHES"
                   for t in node.targets):
            continue
        start = node.lineno
        while start > 1 and text.split("\n")[start - 2].startswith("#"):
            start -= 1
        return (start, node.end_lineno), ast.literal_eval(node.value)
    return None, None


def write_into(path, values, force=False):
    span, patches = existing_patches(path)
    if span is None:
        return "declares no PATCHES"
    if patches.get(0) and not force:
        # Patch 0 is not always derived. minimoog's is one of three
        # designed patches, and create() applies it so the instrument
        # starts there - deriving it back from the module's own defaults
        # would replace a patch someone wrote with an approximation of
        # something else. --check reports the difference; overwriting one
        # takes --force.
        return "already has a patch 0"
    lines = path.read_text().split("\n")
    start, end = span
    replacement = render(patches, values).split("\n")
    path.write_text("\n".join(lines[:start - 1] + replacement + lines[end:]))
    return None


def drift(path, values):
    """Where the committed patch 0 disagrees with what was just derived.

    Reported, never acted on. A disagreement means one of two things: the
    patch was designed rather than derived, or a default moved and the
    patch never followed. Only a human can say which.
    """
    _, patches = existing_patches(path)
    if not patches or 0 not in patches:
        return []
    committed = list(patches[0][1])
    if len(committed) != len(values):
        return ["patch 0 has %d values, the instrument has %d macros"
                % (len(committed), len(values))]
    moved = ["macro %d: %d, derived %d" % (index, was, now)
             for index, (was, now) in enumerate(zip(committed, values))
             if was != now]
    return moved[:4] + (["... and %d more" % (len(moved) - 4)]
                        if len(moved) > 4 else [])


def main():
    argv = sys.argv[1:]
    write = "--write" in argv
    force = "--force" in argv
    wanted = {a[:-3] if a.endswith(".py") else a
              for a in argv if not a.startswith("--")}

    paths = [p for directory in DIRS for p in sorted(directory.glob("*.py"))
             if not p.name.startswith("_")
             and (not wanted or p.stem in wanted)]
    if wanted and not paths:
        raise SystemExit("no such instrument: %s" % ", ".join(sorted(wanted)))

    issues = done = skipped = 0
    for path in paths:
        values, notes = derive(path)
        try:
            label = path.relative_to(REPO)
        except ValueError:
            label = "audioif/lib/%s" % path.relative_to(AUDIOIF_LIB)
        if values is None:
            print("%-52s SKIP %s" % (label, notes))
            skipped += 1
            continue
        status = ""
        if write:
            error = write_into(path, values, force)
            if error:
                status = "  (%s)" % error
                skipped += 1
            else:
                done += 1
        print("%-52s %2d macros%s" % (label, len(values), status))
        for note in notes:
            print("        ! %s" % note)
            issues += 1
        for note in drift(path, values):
            print("        ~ %s" % note)
    print("\n%d files, %d written, %d skipped, %d macros needing attention"
          % (len(paths), done, skipped, issues))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
