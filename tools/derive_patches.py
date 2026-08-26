#!/usr/bin/env python3
"""Give every instrument a Patch 1 describing the sound it already makes.

Every instrument must declare at least one patch: piece.py resolves an
unset macro to the instrument's Patch 1 rather than to 0.5, and 0.5 is the
middle of a range, not "off" and not what the author intended. That
contract is only safe if the patch is genuinely the instrument's designed
sound, so this derives it rather than inventing it.

An instrument's module-level globals already are that sound - volume = 0.8,
cutoff_base = 2000.0. For each macro this:

  1. imports the script and snapshots every global,
  2. feeds the macro 0.0 then 1.0 to see which global it moves, which
     discovers the macro -> parameter binding without parsing anything,
  3. bisects the normalised value until that global returns to its
     snapshot, giving the macro setting that reproduces the default.

Monotonic mappings solve exactly; quantised ones land on the right step.
Anything unbound, ambiguous or unreachable is reported and never guessed -
an unreachable default means the macro cannot restore the designed sound,
which is a bug in the instrument, not something to paper over.

Usage:
    derive_patches.py --check            report, write nothing
    derive_patches.py --write            insert PATCHES into every file
    derive_patches.py --write minimoog.py juno106.py
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import vstaudio  # noqa: E402

DIRS = [REPO / "lib" / "instruments",
        REPO / "soundtrack" / "Automata" / "instruments",
        REPO / "soundtrack" / "Perihelion" / "instruments"]

EVENT_PARAMETER = 6
ANCHOR = "vstaudio.on_event(handle_event)"

BLOCK = '''
# Patch 1 (Program Change 0) is the sound this script's module-level
# defaults describe, so a fresh instance and Patch 1 are the same thing.
# piece.py also reads it: a macro a composition does not set resolves here
# rather than to 0.5. Derived by tools/derive_patches.py - see that file
# before editing these numbers by hand.
PATCHES = {
%s}


def _apply_patch(index, channel=0, note_id=-1, sample_position=0):
    patch = PATCHES.get(index)
    if patch is None:
        return
    for macro_index, macro_value in enumerate(patch[1]):
        handle_event(EVENT_PARAMETER_TYPE, channel, note_id,
                     macro_index, macro_value, 0.0, sample_position)


def _dispatch(event_type, channel, note_id, data0, value0, value1,
              sample_position):
    if event_type == vstaudio.EVENT_PROGRAM_CHANGE:
        _apply_patch(data0, channel, note_id, sample_position)
        return
    handle_event(event_type, channel, note_id, data0, value0, value1,
                 sample_position)


vstaudio.on_event(_dispatch)
'''


def load(path):
    vstaudio._reset(48000)
    ns = {"__name__": "__main__", "__file__": str(path)}
    exec(compile(path.read_text(), str(path), "exec"), ns, ns)
    return ns, vstaudio._handler


def scalars(ns):
    """Every number a macro could plausibly be holding.

    Module globals are the easy case. Several instruments instead park
    their parameters on synthio objects - cut_base.a, verb.mix - so walk
    one level into module-level objects as well. Attribute reads on those
    can raise or be computed properties, hence the guards.
    """
    out = {}
    for key, value in ns.items():
        if key.startswith("__"):
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


def labels_of(path):
    head = path.read_text().split("\n", 1)[0]
    if "mpvst-macro-labels" not in head:
        return []
    return [x.strip() for x in head.split(":", 1)[1].split("|")]


def derive(path):
    labels = labels_of(path)
    if not labels:
        return None, "no macro labels"
    ns, handler = load(path)
    if handler is None:
        return None, "no handler registered"
    defaults = scalars(ns)

    # Some of what we can see moves on its own - an LFO's current value,
    # a phase accumulator. Probing the same macro value twice identifies
    # those, so they are never mistaken for something the macro drives.
    volatile = set()
    for _ in range(3):
        before = scalars(ns)
        after = scalars(ns)
        volatile |= {k for k in before if before.get(k) != after.get(k)}

    values, notes = [], []
    for index in range(min(16, len(labels))):
        handler(EVENT_PARAMETER, 0, -1, index, 0.0, 0.0, 0)
        scalars(ns)
        lo_state = scalars(ns)
        handler(EVENT_PARAMETER, 0, -1, index, 1.0, 0.0, 0)
        scalars(ns)
        hi_state = scalars(ns)
        moved = [k for k in defaults
                 if k not in volatile and k in lo_state
                 and lo_state[k] != hi_state[k]]
        if not moved:
            values.append(0.5)
            notes.append("%d:%s:unbound" % (index, labels[index]))
            continue
        if len(moved) > 1:
            # One macro driving several parameters at once - a vowel morph
            # moving every formant, say. There is no single target to
            # bisect, so scan and take the setting that puts all of them
            # closest to their defaults together.
            best_x, best_err = 0.5, None
            for step in range(1001):
                x = step / 1000.0
                handler(EVENT_PARAMETER, 0, -1, index, x, 0.0, 0)
                state = scalars(ns)
                err = 0.0
                for k in moved:
                    t = defaults[k]
                    err += ((state[k] - t) / (abs(t) if t else 1.0)) ** 2
                if best_err is None or err < best_err:
                    best_x, best_err = x, err
            handler(EVENT_PARAMETER, 0, -1, index, best_x, 0.0, 0)
            values.append(round(best_x, 6))
            if best_err is not None and best_err > 1e-6:
                notes.append("%d:%s:multi(%d params, err %.3g)"
                             % (index, labels[index], len(moved), best_err))
            continue
        key = moved[0]
        target, lo_v, hi_v = defaults[key], lo_state[key], hi_state[key]
        if not (min(lo_v, hi_v) <= target <= max(lo_v, hi_v)):
            x = 0.0 if abs(lo_v - target) <= abs(hi_v - target) else 1.0
            handler(EVENT_PARAMETER, 0, -1, index, x, 0.0, 0)
            values.append(x)
            notes.append("%d:%s:unreachable(%s=%g)" % (index, labels[index],
                                                       key, target))
            continue
        ascending = hi_v > lo_v
        lo, hi = 0.0, 1.0
        for _ in range(60):
            mid = (lo + hi) / 2.0
            handler(EVENT_PARAMETER, 0, -1, index, mid, 0.0, 0)
            if (scalars(ns)[key] < target) == ascending:
                lo = mid
            else:
                hi = mid
        x = round((lo + hi) / 2.0, 6)
        handler(EVENT_PARAMETER, 0, -1, index, x, 0.0, 0)
        got = scalars(ns)[key]
        # 1e-4 relative: bisection noise on a cutoff in Hz is inaudible,
        # and flagging it would bury the real failures.
        if abs(got - target) > 1e-4 * max(1.0, abs(target)):
            notes.append("%d:%s:approx(%g!=%g)" % (index, labels[index],
                                                   got, target))
        values.append(x)
    return values, notes


def render_block(values):
    body = "    0: (\"Init\", (\n"
    line = "        "
    for i, v in enumerate(values):
        piece = ("%g" % v) + ("," if i < len(values) - 1 else "")
        if len(line) + len(piece) + 1 > 72:
            body += line.rstrip() + "\n"
            line = "        "
        line += piece + " "
    # A one-macro instrument needs the trailing comma, or ("Init", (0.8))
    # is a bare float rather than a tuple.
    tail = ",)" if len(values) == 1 else ")"
    body += line.rstrip() + tail + "),\n"
    return BLOCK % body


def write_into(path, values):
    text = path.read_text()
    if "\nPATCHES" in text:
        return "already has PATCHES"
    if text.count(ANCHOR) != 1:
        return "anchor not unique"
    block = render_block(values).replace("EVENT_PARAMETER_TYPE",
                                         "vstaudio.EVENT_PARAMETER")
    path.write_text(text.replace(ANCHOR, block.lstrip("\n")))
    return None


def main():
    argv = sys.argv[1:]
    write = "--write" in argv
    argv = [a for a in argv if not a.startswith("--")]
    paths = []
    for d in DIRS:
        for p in sorted(d.glob("*.py")):
            if not argv or p.name in argv:
                paths.append(p)

    issues = done = skipped = 0
    for p in paths:
        values, notes = derive(p)
        rel = p.relative_to(REPO)
        if values is None:
            print("%-52s SKIP %s" % (rel, notes))
            skipped += 1
            continue
        status = ""
        if write:
            err = write_into(p, values)
            if err:
                status = "  (%s)" % err
                skipped += 1
            else:
                done += 1
        print("%-52s %2d macros%s" % (rel, len(values), status))
        for n in notes:
            print("        ! %s" % n)
            issues += 1
    print("\n%d files, %d written, %d skipped, %d macros needing attention"
          % (len(paths), done, skipped, issues))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
