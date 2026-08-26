#!/usr/bin/env python3
"""Compare the REAPER bounce of Perihelion against the offline preview.

The preview (audioif CPython wheel) and the bounce (real plug-in, real
MicroPython sidecars, real automation) should agree on the shape of the
piece: same sections loud, same sections quiet, sane peaks, no dead air.
Exact PCM equality is not expected - pan law, envelope timing, and event
quantisation all differ slightly.

Usage: verify_song.py <bounce.wav> <preview.wav>
"""

import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from piece import load_piece, piece_arg  # noqa: E402

PIECE, ARGV = piece_arg(sys.argv[1:])
C, _INSTRUMENTS = load_piece(PIECE)

TOLERANCE_DB = 3.5


def load(path):
    with wave.open(str(path)) as handle:
        rate = handle.getframerate()
        width = handle.getsampwidth()
        channels = handle.getnchannels()
        raw = handle.readframes(handle.getnframes())
    if width == 2:
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif width == 3:
        as_bytes = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        value = (as_bytes[:, 0].astype(np.int32)
                 | (as_bytes[:, 1].astype(np.int32) << 8)
                 | (as_bytes[:, 2].astype(np.int32) << 16))
        value = np.where(value & 0x800000, value - 0x1000000, value)
        data = value.astype(np.float32) / 8388608.0
    elif width == 4:
        data = np.frombuffer(raw, dtype=np.float32)
    else:
        raise SystemExit("unsupported sample width %d" % width)
    return rate, data.reshape(-1, channels)


def rms_db(seg):
    return 20 * np.log10(max(float(np.sqrt((seg ** 2).mean())), 1e-9))


def main():
    bounce_path, preview_path = ARGV[0], ARGV[1]
    rate_b, bounce = load(bounce_path)
    rate_p, preview = load(preview_path)
    assert rate_b == C.SAMPLE_RATE, "bounce sample rate %d" % rate_b

    failures = 0

    def check(name, ok, detail):
        nonlocal failures
        if not ok:
            failures += 1
        print("  %-24s %s  %s" % (name, "PASS" if ok else "FAIL", detail))

    peak = float(np.abs(bounce).max())
    check("bounce/peak", 0.05 < peak < 1.0, "peak=%.3f" % peak)

    print("\n  %-14s %10s %10s %8s" % ("section", "bounce", "preview", "diff"))
    for name, b0, b1 in C.SECTIONS:
        s0 = int(C.beats_to_seconds(b0) * C.SAMPLE_RATE)
        s1 = int(C.beats_to_seconds(b1) * C.SAMPLE_RATE)
        db_b = rms_db(bounce[s0:min(s1, len(bounce))])
        db_p = rms_db(preview[s0:min(s1, len(preview))])
        diff = db_b - db_p
        check(name.replace(" ", "_"), abs(diff) < TOLERANCE_DB,
              "%7.1f dB %8.1f dB %+6.1f" % (db_b, db_p, diff))

    # loudest section must be the climax
    levels = {}
    for name, b0, b1 in C.SECTIONS:
        s0 = int(C.beats_to_seconds(b0) * C.SAMPLE_RATE)
        s1 = int(C.beats_to_seconds(b1) * C.SAMPLE_RATE)
        levels[name] = rms_db(bounce[s0:min(s1, len(bounce))])
    loudest = max(levels, key=levels.get)
    expected = getattr(C, "CLIMAX_SECTION", None)
    if expected:
        check("bounce/climax_loudest", loudest == expected,
              "loudest=%s" % loudest)

    # no dead air inside the song
    mono = bounce[:int(C.SONG_SECONDS * C.SAMPLE_RATE)].mean(axis=1)
    win = C.SAMPLE_RATE // 2
    n = len(mono) // win
    blocks = mono[:n * win].reshape(n, win)
    quiet = int((np.sqrt((blocks ** 2).mean(axis=1)) < 1e-4).sum())
    check("bounce/no_dead_air", quiet == 0, "%d silent half-seconds" % quiet)

    print()
    if failures:
        print("SONG VERIFY FAIL: %d check(s) failed" % failures)
        return 1
    print("SONG VERIFY PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
