#!/usr/bin/env python3
"""Run every lib/instruments/*.py script through the real MicroPython
Instrument VST3 class (the packaged engine, real shared-memory protocol),
via the smoke host's --instrument-script probe.

This is the slower, higher-fidelity companion to test-instruments-lib.py
(which runs the same scripts against the audioif CPython wheel directly,
no engine or plug-in involved, in a fraction of the time). Keeping both:
the fast one is what you run while iterating on a script; this one is the
final gate, since it is the only one that also exercises the VST3
processor, the protocol, and macro/state handling around the script.

Usage: test-instruments-plugin.py <smoke_host> <bundle.vst3> [name.py ...]
"""

import re
import subprocess
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
INSTRUMENTS_DIR = REPO_DIR / "lib" / "instruments"


def main():
    smoke, bundle = sys.argv[1], sys.argv[2]
    names = sys.argv[3:]
    scripts = ([INSTRUMENTS_DIR / n for n in names] if names
              else sorted(INSTRUMENTS_DIR.glob("*.py")))

    failures = []
    for script in scripts:
        result = subprocess.run(
            [smoke, bundle, "--instrument-script", str(script)],
            capture_output=True, text=True, timeout=300)
        match = re.search(
            r"INSTRUMENT_PROBE ready=(\d) error=(-?\d+) peak=(\S+)",
            result.stdout)
        if result.returncode != 0 or match is None:
            failures.append(script.name)
            print("%-20s FAIL (probe: rc=%d)\n%s" %
                  (script.name, result.returncode, result.stdout + result.stderr))
            continue
        ready, error, peak = match.group(1), int(match.group(2)), float(match.group(3))
        ok = ready == "1" and error == 0 and peak > 0.0005
        print("%-20s %-4s ready=%s error=%s peak=%.4f" %
              (script.name, "ok" if ok else "FAIL", ready, error, peak))
        if not ok:
            failures.append(script.name)

    if failures:
        print("\n%d/%d scripts failed: %s" %
              (len(failures), len(scripts), ", ".join(failures)))
        return 1
    print("\n%d/%d scripts ok" % (len(scripts), len(scripts)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
