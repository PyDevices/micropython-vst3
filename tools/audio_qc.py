"""Measure a rendered WAV: loudness, true peak, and silence.

    python tools/audio_qc.py bounce/piece.wav
    python tools/audio_qc.py *.wav --json

Nothing here knows about MPVST, REAPER or how the file was made. Hand it a
WAV and it answers the questions we keep asking by hand after a render: how
loud is it really, does it clip between samples, and is any of it silent that
should not be.

`verify_song.py` next door checks a render against its own preview and catches
dead air, but it measures RMS and sample peak. RMS is not loudness and sample
peak is not true peak - a signal can sit under 0 dBFS at every sample and
still clip a converter between them. This is the other half.

Needs numpy, soundfile, pyloudnorm and scipy; `scripts/bootstrap.sh` puts them
in the repo venv.

The defaults are streaming-delivery numbers - -14 LUFS, -1 dBTP - because that
is what we have wanted so far. They are arguments, not a house standard: pass
your own if you are cutting for something else.
"""

from __future__ import annotations

import argparse
import json as _json
import math
import os
import sys

import numpy as np
import pyloudnorm as pyln
import soundfile as sf
from scipy.signal import resample_poly


# Defaults, overridable per call - see the module docstring.
TARGET_LUFS = -14.0
LUFS_LO = -15.5
LUFS_HI = -13.0
TRUE_PEAK_CEILING = -1.0
SILENCE_DB = -80.0
MAX_EDGE_SILENCE_S = 0.40


def integrated_lufs(audio: np.ndarray, sr: int) -> tuple[float, float]:
    """Return (integrated LUFS, loudness range LU) via ITU-R BS.1770."""
    meter = pyln.Meter(sr)
    lufs = float(meter.integrated_loudness(audio))
    if not math.isfinite(lufs):
        lufs = -70.0
    # LRA from 3 s short-term windows, 10th–95th percentile
    win = int(sr * 3.0)
    hop = int(sr * 0.1)
    if audio.shape[0] < win:
        return lufs, 0.0
    st = []
    i = 0
    short_meter = pyln.Meter(sr)
    while i + win <= audio.shape[0]:
        sl = audio[i:i + win]
        try:
            val = float(short_meter.integrated_loudness(sl))
        except Exception:
            val = -70.0
        if math.isfinite(val):
            st.append(val)
        i += hop
    if len(st) < 4:
        return lufs, 0.0
    arr = np.array(st)
    arr = arr[arr > -70.0]
    if arr.size < 4:
        return lufs, 0.0
    return lufs, float(np.percentile(arr, 95) - np.percentile(arr, 10))


def true_peak_dbtp(audio: np.ndarray, sr: int) -> float:
    """4x-oversampled sample peak as a true-peak estimate."""
    if audio.size == 0:
        return -120.0
    x = audio if audio.ndim == 2 else audio[:, None]
    peak = 0.0
    for ch in range(x.shape[1]):
        y = resample_poly(x[:, ch], 4, 1)
        peak = max(peak, float(np.max(np.abs(y))))
    if peak <= 1e-12:
        return -120.0
    return 20.0 * math.log10(peak)


def read_wav(path: str) -> tuple[np.ndarray, int]:
    data, sr = sf.read(path, dtype="float64", always_2d=True)
    return data, int(sr)


def silence_edges(audio: np.ndarray, sr: int, thresh_db: float = SILENCE_DB):
    if audio.ndim == 2:
        rms_env = np.sqrt(np.mean(np.square(audio), axis=1) + 1e-16)
    else:
        rms_env = np.abs(audio)
    thresh = 10 ** (thresh_db / 20.0)
    active = np.where(rms_env > thresh)[0]
    if active.size == 0:
        dur = audio.shape[0] / sr
        return dur, dur, True, 0
    lead = active[0] / sr
    trail = (audio.shape[0] - 1 - active[-1]) / sr
    silent = rms_env <= thresh
    mid = silent[active[0]:active[-1] + 1]
    padded = np.concatenate([[False], mid, [False]])
    edges = np.diff(padded.astype(np.int8))
    starts = np.where(edges == 1)[0]
    ends = np.where(edges == -1)[0]
    min_run = int(0.4 * sr)
    dropouts = int(np.sum((ends - starts) >= min_run))
    return lead, trail, False, dropouts


def measure(path: str) -> dict:
    audio, sr = read_wav(path)
    peak = float(np.max(np.abs(audio)))
    sample_peak_db = -120.0 if peak <= 1e-12 else 20.0 * math.log10(peak)
    tp = true_peak_dbtp(audio, sr)
    lufs, lra = integrated_lufs(audio, sr)
    lead, trail, all_silent, dropouts = silence_edges(audio, sr)
    rms = float(np.sqrt(np.mean(np.square(audio))))
    rms_db = -120.0 if rms <= 1e-12 else 20.0 * math.log10(rms)
    duration = audio.shape[0] / sr
    return {
        "path": path,
        "sr": sr,
        "duration_s": duration,
        "lufs": lufs,
        "lra": lra,
        "sample_peak_db": sample_peak_db,
        "true_peak_dbtp": tp,
        "rms_db": rms_db,
        "lead_silence_s": lead,
        "trail_silence_s": trail,
        "all_silent": all_silent,
        "dropouts": dropouts,
        "nframes": int(audio.shape[0]),
        "channels": 1 if audio.ndim == 1 else audio.shape[1],
    }


def qc_report(m: dict, lufs_lo: float = LUFS_LO, lufs_hi: float = LUFS_HI,
              ceiling: float = TRUE_PEAK_CEILING) -> tuple[bool, list[str]]:
    """Judge a measurement. Thresholds are arguments so this is not tied to
    one delivery target."""
    fails = []
    if m["all_silent"] or m["rms_db"] < -80:
        fails.append(f"digital-black / RMS {m['rms_db']:.1f} dBFS")
    if m["true_peak_dbtp"] > ceiling + 0.05:
        fails.append(f"true peak {m['true_peak_dbtp']:.2f} dBTP > {ceiling}")
    if not (lufs_lo <= m["lufs"] <= lufs_hi):
        fails.append(f"integrated {m['lufs']:.2f} LUFS outside {lufs_lo}..{lufs_hi}")
    if m["lead_silence_s"] > MAX_EDGE_SILENCE_S:
        fails.append(f"leading silence {m['lead_silence_s']*1000:.0f} ms")
    if m["trail_silence_s"] > MAX_EDGE_SILENCE_S + 0.6:
        # allow a reverb tail a bit past 400ms; hard fail if multi-second pad
        fails.append(f"trailing silence {m['trail_silence_s']*1000:.0f} ms")
    if m["dropouts"]:
        fails.append(f"{m['dropouts']} mid-file silence dropouts >400ms")
    return (len(fails) == 0), fails


def format_measure(m: dict) -> str:
    return (
        f"{os.path.basename(m['path'])}: {m['duration_s']:.2f}s  "
        f"LUFS {m['lufs']:+.2f}  LRA {m['lra']:.1f}  "
        f"peak {m['sample_peak_db']:+.2f} dBFS  TP {m['true_peak_dbtp']:+.2f} dBTP  "
        f"RMS {m['rms_db']:+.1f}  lead {m['lead_silence_s']*1000:.0f}ms  "
        f"trail {m['trail_silence_s']*1000:.0f}ms"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="+", help="WAV files to measure")
    parser.add_argument("--json", action="store_true",
                        help="machine-readable, one object per file")
    parser.add_argument("--target-lufs", type=float, default=TARGET_LUFS)
    parser.add_argument("--lufs-window", type=float, default=1.5,
                        help="how far either side of the target still passes")
    parser.add_argument("--ceiling", type=float, default=TRUE_PEAK_CEILING,
                        help="true-peak ceiling in dBTP")
    args = parser.parse_args()

    results, failed = [], 0
    for path in args.paths:
        measured = measure(path)
        ok, fails = qc_report(measured,
                              lufs_lo=args.target_lufs - args.lufs_window,
                              lufs_hi=args.target_lufs + args.lufs_window,
                              ceiling=args.ceiling)
        measured["pass"] = ok
        measured["failures"] = fails
        results.append(measured)
        if not ok:
            failed += 1
        if not args.json:
            print(format_measure(measured))
            for reason in fails:
                print("    FAIL " + reason)
    if args.json:
        _json.dump(results, sys.stdout, indent=2)
        sys.stdout.write("\n")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
