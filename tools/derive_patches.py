#!/usr/bin/env python3
"""Give every instrument patch 0 describing the sound it already makes.

Every instrument must declare at least one patch: piece.py resolves an
unset macro to the instrument's patch 0 rather than to the middle of its
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
And `create()` ends by applying patch 0, which would make deriving patch 0
circular, so the instrument is built with that step suppressed: what gets
measured is the sound its own code leaves behind.

An instrument that already declares a patch 0 keeps it. Not every patch 0
is derived - minimoog's is one of three designed patches, and create()
applies it so the instrument starts there - so overwriting one has to be
asked for. The report marks a disagreement `~`, sized in the parameter's
own units. A default that sits midway between two settings is a tie, not
a disagreement: the committed setting is kept, so rederiving is stable.

Usage:
    derive_patches.py                    report, write nothing
    derive_patches.py --write            fill in a missing PATCHES block
    derive_patches.py --write --force    rederive patch 0 as well
    derive_patches.py --write minimoog ms20
"""

import ast
import importlib.util
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
# The generated shims in soundtrack/*/instruments/ are three lines that
# delegate to the library through `mpvst_adapter`, which lives in this repo's
# lib/. Without it on the path the first shim this tool reaches raises
# ModuleNotFoundError and the audit stops partway - which is why a full pass
# had never completed. harness.py sets up the same entry (harness.py:32), and
# the two tools load the same scripts, so they need the same path.
sys.path.insert(0, str(REPO / "lib"))

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

#: How much further from its default the committed setting may leave a
#: parameter than the derived one, as a fraction of the default, and still
#: be a tie rather than a disagreement. A default sitting midway between
#: two steps of a logarithmic macro is nearer the lower step by
#: (ln step)^2 / 4 of its value - 0.003% for tr808's SD Tone over two
#: octaves, 0.07% over three decades - so 0.1% covers every tie the grid
#: can produce while staying well under what one step itself moves.
TIE = 0.001

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
    """The instrument as its own code leaves it, before patch 0 is applied.

    create() finishes by applying patch 0 so that a fresh instance and
    patch 0 are the same thing. That is exactly what makes it circular to
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


class Macro:
    """One macro: what it moves, and where each of its settings leaves it.

    The scan in derive() visits all 128 settings anyway. Keeping what it
    saw is what lets a disagreement between the committed and the derived
    setting be sized in the parameter's own units, and a tie be told from
    one. An unbound macro moves nothing and has an empty table.
    """

    def __init__(self, label, keys, targets):
        self.label = label
        self.keys = keys
        self.targets = targets
        self.table = []                            # setting -> {key: value}

    def error(self, setting):
        return error_against(self.table[setting], self.targets, self.keys)

    def distance(self, setting):
        """Relative distance from the defaults - the error, unsquared."""
        return math.sqrt(self.error(setting))

    def worst(self, setting):
        """The parameter this setting leaves furthest from its default."""
        state = self.table[setting]
        return max(self.keys, key=lambda k: abs(state[k] - self.targets[k])
                   / (abs(self.targets[k]) or 1.0))

    def tie(self, committed, derived):
        """Whether the committed setting answers as well as the derived one.

        True when the two bracket the default - one above it, one below,
        for every parameter that differs between them - and the committed
        one is further off by no more than TIE. A default that lands
        between two steps of the grid is served equally by either; which
        of them the scan picks is down to rounding, not to the sound.
        """
        if not 0 <= committed < len(self.table):
            return False
        here, there = self.table[committed], self.table[derived]
        bracket = all((here[k] - self.targets[k])
                      * (there[k] - self.targets[k]) <= 0
                      for k in self.keys if here[k] != there[k])
        return (bracket
                and self.distance(committed) - self.distance(derived) <= TIE)


def derive(path):
    """(values, notes, macros) for one instrument, or (None, reason, None).

    `macros` holds a Macro per value - what drift() needs to say by how
    much a committed value disagrees, rather than only that it does.
    """
    module = load(path)
    labels = getattr(module, "MACRO_LABELS", None)
    if not labels:
        return None, "no MACRO_LABELS", None
    instrument = build(module)
    defaults = scalars(instrument)
    # A committed value that ties the scan's pick is kept, so the committed
    # patch is read before anything is derived.
    _, patches = existing_patches(path)
    committed = list(patches[0][1]) if patches and 0 in patches else []

    # Some of what we can see moves on its own - an LFO's current value, a
    # phase accumulator. Reading twice without touching anything identifies
    # those, so they are never mistaken for something a macro drives.
    volatile = set()
    for _ in range(3):
        before = scalars(instrument)
        after = scalars(instrument)
        volatile |= {k for k in before if before.get(k) != after.get(k)}

    values, notes, macros = [], [], []
    for index in range(min(16, len(labels))):
        instrument.set_macro(index, 0)
        low = scalars(instrument)
        instrument.set_macro(index, 127)
        high = scalars(instrument)
        moved = [k for k in defaults
                 if k not in volatile and k in low and low[k] != high[k]]
        macro = Macro(labels[index], moved, {k: defaults[k] for k in moved})
        macros.append(macro)
        if not moved:
            values.append(64)
            notes.append("%d:%s:unbound" % (index, labels[index]))
            instrument.set_macro(index, 64)
            continue

        best, best_error = 0, None
        for setting in range(128):
            instrument.set_macro(index, setting)
            state = scalars(instrument)
            macro.table.append({k: state.get(k, defaults[k]) for k in moved})
            error = error_against(state, defaults, moved)
            # Ties go to the higher setting, which is round-half-up: a
            # default sitting exactly between two steps of a linear macro
            # is equally far from both, and 64 is the answer everyone
            # expects for the middle of 0-127.
            if best_error is None or error <= best_error:
                best, best_error = setting, error
        # A default that sits midway between two steps is a tie, and a tie
        # goes to the value already committed: the scan's pick is no better
        # for the sound, and rederiving must not move a patch for nothing -
        # which is what --force did to three drum kits before this rule.
        if index < len(committed) and macro.tie(committed[index], best):
            best, best_error = committed[index], macro.error(committed[index])
        instrument.set_macro(index, best)
        values.append(best)

        if best_error > TOLERANCE:
            # Landing on an end stop means the default is outside the range
            # the macro can reach at all, which is a different bug from a
            # macro that can get close but not exactly there.
            kind = "unreachable" if best in (0, 127) else "approx"
            worst = macro.worst(best)
            got, target = macro.table[best][worst], defaults[worst]
            notes.append(
                "%d:%s:%s %s=%.6g wanted %.6g (%.0f%% off%s)"
                % (index, labels[index], kind, worst, got, target,
                   100.0 * abs(got - target) / (abs(target) or 1.0),
                   ", %d params" % len(moved) if len(moved) > 1 else ""))
    return values, notes, macros


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


def drift(path, values, macros):
    """Where the committed patch 0 disagrees with what was just derived.

    Reported, never acted on. A disagreement means one of two things: the
    patch was designed rather than derived, or a default moved and the
    patch never followed. Only a human can say which, and only from a line
    that says by how much in the parameter's own units - a tie between two
    steps reads no differently from a patch 20 steps off otherwise. Ties
    never get this far: derive() keeps the committed value on one.
    """
    _, patches = existing_patches(path)
    if not patches or 0 not in patches:
        return []
    committed = list(patches[0][1])
    if len(committed) != len(values):
        return ["patch 0 has %d values, the instrument has %d macros"
                % (len(committed), len(values))]
    moved = []
    for index, (was, now, macro) in enumerate(zip(committed, values, macros)):
        if was == now:
            continue
        head = "macro %d (%s): %d -> %d" % (index, macro.label, was, now)
        if not macro.keys or not 0 <= was < len(macro.table):
            moved.append(head)                     # unbound, or off the grid
            continue
        worst = macro.worst(was)
        worse = 100.0 * (macro.distance(was) - macro.distance(now))
        moved.append(
            "%s, %s=%.6g vs %.6g, wanted %.6g (committed is %s%% worse%s)"
            % (head, worst, macro.table[was][worst], macro.table[now][worst],
               macro.targets[worst],
               ("%.0f" if worse >= 10 else "%.2g") % worse,
               ", %d params" % len(macro.keys) if len(macro.keys) > 1 else ""))
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
        values, notes, macros = derive(path)
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
        for note in drift(path, values, macros):
            print("        ~ %s" % note)
    print("\n%d files, %d written, %d skipped, %d macros needing attention"
          % (len(paths), done, skipped, issues))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
