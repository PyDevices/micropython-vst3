#!/usr/bin/env python3
"""Verify the PCM that REAPER rendered during the DAW matrix.

The matrix instrument emits a constant level while a note is held:

    level = 0.125 + 0.125 * macro01

The note runs from 1.0 s to 2.0 s of a 3 s render, so every render is checked
as three regions: silent lead-in, a held plateau, and a silent tail. Reporting
the measured plateau rather than only a pass/fail keeps the evidence useful
when a step legitimately changes the level.
"""

from __future__ import annotations

import struct
import sys
import wave
from pathlib import Path

NOTE_START = 1.0
NOTE_END = 2.0
# Ignore a short window around each edge: the instrument applies its gate at the
# event's sample position and the host renders a release tail.
EDGE_GUARD = 0.05


def read_wave(path: Path):
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        frames = handle.getnframes()
        raw = handle.readframes(frames)
    return channels, width, rate, frames, raw


def to_float(raw: bytes, width: int, channels: int):
    """Return channel 0 as floats in -1.0..1.0."""
    if width == 2:
        count = len(raw) // 2
        values = struct.unpack("<%dh" % count, raw[: count * 2])
        scale = 32768.0
    elif width == 3:
        values = []
        for offset in range(0, len(raw) - 2, 3):
            value = raw[offset] | (raw[offset + 1] << 8) | (raw[offset + 2] << 16)
            if value & 0x800000:
                value -= 0x1000000
            values.append(value)
        scale = 8388608.0
    elif width == 4:
        count = len(raw) // 4
        values = struct.unpack("<%df" % count, raw[: count * 4])
        scale = 1.0
    else:
        raise ValueError("unsupported sample width %d" % width)
    return [values[i] / scale for i in range(0, len(values), channels)]


def region_stats(samples, rate, start, end):
    lo = max(0, int(start * rate))
    hi = min(len(samples), int(end * rate))
    if hi <= lo:
        return 0.0, 0.0, 0
    window = samples[lo:hi]
    peak = max(abs(value) for value in window)
    mean = sum(window) / len(window)
    return peak, mean, len(window)


def analyse(path: Path):
    channels, width, rate, frames, raw = read_wave(path)
    samples = to_float(raw, width, channels)
    duration = frames / float(rate)

    lead_peak, _, lead_n = region_stats(samples, rate, 0.0, NOTE_START - EDGE_GUARD)
    hold_peak, hold_mean, hold_n = region_stats(
        samples, rate, NOTE_START + EDGE_GUARD, NOTE_END - EDGE_GUARD
    )
    tail_peak, _, tail_n = region_stats(
        samples, rate, NOTE_END + EDGE_GUARD * 4, duration
    )

    # The plateau should be a constant, so peak and mean agree when the gate is
    # steady. Report both to expose any drift or discontinuity.
    return {
        "file": path.name,
        "rate": rate,
        "width_bits": width * 8,
        "channels": channels,
        "duration": duration,
        "lead_peak": lead_peak,
        "hold_peak": hold_peak,
        "hold_mean": hold_mean,
        "tail_peak": tail_peak,
        "lead_n": lead_n,
        "hold_n": hold_n,
        "tail_n": tail_n,
    }


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: verify_renders.py <render-dir>", file=sys.stderr)
        return 2
    directory = Path(sys.argv[1])
    # edge_*.wav are the short renders that only exist to let the plug-in
    # observe a Reload Script transition; they carry no note to measure.
    files = [p for p in sorted(directory.glob("*.wav"))
             if not p.name.startswith("edge_")
             and p.stem not in ("extra_status", "startup_status")]
    if not files:
        print("VERIFY FAIL: no rendered WAV files in %s" % directory)
        return 1

    print("=== render analysis ===")
    results = {}
    for path in files:
        try:
            stats = analyse(path)
        except Exception as exc:  # noqa: BLE001 - report and continue
            print("  %-16s ERROR %s" % (path.name, exc))
            continue
        results[path.stem] = stats
        print(
            "  %-16s %5d Hz %2d-bit ch=%d dur=%.3fs  lead_peak=%.6f "
            "hold_mean=%.6f hold_peak=%.6f tail_peak=%.6f"
            % (
                stats["file"],
                stats["rate"],
                stats["width_bits"],
                stats["channels"],
                stats["duration"],
                stats["lead_peak"],
                stats["hold_mean"],
                stats["hold_peak"],
                stats["tail_peak"],
            )
        )

    print()
    print("=== checks ===")
    failures = 0

    def check(name: str, ok: bool, detail: str) -> None:
        nonlocal failures
        if not ok:
            failures += 1
        print("  %-28s %s  %s" % (name, "PASS" if ok else "FAIL", detail))

    tolerance = 1.0 / 32768.0 * 2

    def plateau(name: str, expected: float) -> None:
        if name not in results:
            check("%s/present" % name, False, "render missing")
            return
        stats = results[name]
        check(
            "%s/gate-level-%.4g" % (name, expected),
            abs(stats["hold_mean"] - expected) < tolerance,
            "mean=%.8f expected=%.8f" % (stats["hold_mean"], expected),
        )
        check(
            "%s/plateau-is-constant" % name,
            abs(stats["hold_peak"] - stats["hold_mean"]) < tolerance,
            "peak-mean=%.8f" % abs(stats["hold_peak"] - stats["hold_mean"]),
        )
        check(
            "%s/silent-lead-in" % name,
            stats["lead_peak"] < tolerance,
            "peak=%.8f" % stats["lead_peak"],
        )
        check(
            "%s/silent-tail" % name,
            stats["tail_peak"] < tolerance,
            "peak=%.8f" % stats["tail_peak"],
        )

    # Macro 01 at zero gives 0.125 and at full scale gives 0.25.
    plateau("macro_zero", 0.125)
    plateau("macro_full", 0.25)

    # The edited source ignores the macro and holds a fixed 0.375, so hearing
    # that level proves the reload picked up the file as it is on disk now.
    plateau("edited", 0.375)

    # Restoring the original file and reloading returns to the macro-driven
    # level, which is still at full scale here.
    plateau("restored", 0.25)

    # A reopened project restores the macro and must sound like the saved one.
    plateau("reopened", 0.25)

    # ...and must keep using its embedded source even after the original file
    # on disk is replaced.
    plateau("reopened_after_edit", 0.25)

    if "malformed" in results:
        stats = results["malformed"]
        check(
            "malformed/renders-silence",
            max(stats["hold_peak"], stats["lead_peak"]) < tolerance,
            "hold_peak=%.8f" % stats["hold_peak"],
        )

    # After recovery the matrix sets Macro 01 back to zero.
    plateau("recovered", 0.125)

    print()
    if failures:
        print("VERIFY FAIL: %d check(s) failed" % failures)
        return 1
    print("VERIFY PASS: all render checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
