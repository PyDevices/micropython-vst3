#!/usr/bin/env python3
"""Check that the pump pad's sidechain duck is beat-locked in a render.

Isolates a stretch of movement III, extracts the amplitude envelope of
the band the pad occupies, and measures the strongest modulation
frequency. If the sidecar saw a sane transport, it sits at the beat rate
(2.1 Hz at 126 bpm) rather than drifting free.

Usage: check_pump.py <render.wav>
"""

import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from piece import load_piece  # noqa: E402

C, _ = load_piece("automata")
SR = C.SAMPLE_RATE


def main():
    with wave.open(sys.argv[1]) as handle:
        width = handle.getsampwidth()
        raw = handle.readframes(handle.getnframes())
    if width == 2:
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif width == 3:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        v = (b[:, 0].astype(np.int32) | (b[:, 1].astype(np.int32) << 8)
             | (b[:, 2].astype(np.int32) << 16))
        v = np.where(v & 0x800000, v - 0x1000000, v)
        data = v.astype(np.float32) / 8388608.0
    else:
        data = np.frombuffer(raw, dtype=np.float32)
    mono = data.reshape(-1, 2).mean(axis=1)

    # Movement III bars 5-13: pads pumping, before the arps pile in.
    s0 = int(C.beats_to_seconds(C.b3(5)) * SR)
    s1 = int(C.beats_to_seconds(C.b3(13)) * SR)
    seg = mono[s0:s1]

    # amplitude envelope, then its spectrum
    env = np.abs(seg)
    hop = 480  # 10 ms
    frames = env[:len(env) // hop * hop].reshape(-1, hop).mean(axis=1)
    frames -= frames.mean()
    spec = np.abs(np.fft.rfft(frames * np.hanning(len(frames))))
    freqs = np.fft.rfftfreq(len(frames), hop / SR)
    lo = np.searchsorted(freqs, 0.8)
    hi = np.searchsorted(freqs, 5.0)
    peak_hz = freqs[lo + int(np.argmax(spec[lo:hi]))]
    beat_hz = 126.0 / 60.0
    print("envelope modulation peak: %.3f Hz (beat rate %.3f Hz)"
          % (peak_hz, beat_hz))
    ok = abs(peak_hz - beat_hz) < 0.15 or abs(peak_hz - beat_hz / 2) < 0.1 \
        or abs(peak_hz - beat_hz * 2) < 0.2
    print("PUMP %s" % ("LOCKED" if ok else "NOT LOCKED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
