#!/usr/bin/env python3
"""Render a piece offline through the audioif CPython wheel.

Every track's instrument script runs against the vstaudio shim - the same
DSP the sidecar uses - while this harness delivers the composition's note
and macro events and mixes the tracks with the same gains, swells, and pans
the REAPER project uses. Writes a stereo master WAV plus an analysis report
(peaks, RMS per section, simultaneous-track counts).

Usage: render_preview.py [--piece NAME] [out.wav] [--stems DIR]
"""

import sys
import time
import wave
from pathlib import Path

SCORE = Path(__file__).resolve().parent
sys.path.insert(0, str(SCORE))
sys.path.insert(0, str(SCORE / "preview"))

import numpy as np  # noqa: E402

from piece import load_piece, piece_arg  # noqa: E402
from harness import InstrumentRun  # noqa: E402
import vstaudio as shim  # noqa: E402

PIECE, ARGV = piece_arg(sys.argv[1:])
C, INSTRUMENTS = load_piece(PIECE)

BLOCK = 256
SR = C.SAMPLE_RATE


def tempo_rows():
    return [(row[0], row[1]) for row in C.TEMPO_MAP]


def beat_at_sample(sample):
    """Inverse of beats_to_seconds, piecewise exact."""
    seconds = sample / SR
    rows = tempo_rows()
    acc = 0.0
    for i, (start, bpm) in enumerate(rows):
        end = rows[i + 1][0] if i + 1 < len(rows) else None
        span = None if end is None else (end - start) * 60.0 / bpm
        if span is None or seconds <= acc + span:
            return start + (seconds - acc) * bpm / 60.0
        acc += span
    return C.TOTAL_BEATS


def bpm_at_beat(beat):
    rows = tempo_rows()
    current = rows[0][1]
    for start, bpm in rows:
        if beat >= start:
            current = bpm
    return current


def timesig_at_beat(beat):
    num, den = 4, 4
    for row in C.TEMPO_MAP:
        if beat >= row[0] and len(row) >= 4:
            num, den = row[2], row[3]
    return num, den


def build_events(track):
    """(sample_position, type, data0, value0) for one track, sorted."""
    events = []
    for index in range(16):
        value = C.macro_value(track, index, 0.0)
        events.append((0, 6, index, value))
    for start, dur, pitch, vel in track["notes"]:
        s0 = int(C.beats_to_seconds(start) * SR)
        s1 = int(C.beats_to_seconds(start + dur) * SR)
        events.append((s0, 1, pitch, vel))
        events.append((max(s0 + 1, s1), 0, pitch, 0.0))
    # macro automation, sampled per block while it changes
    for index, env in track["macro_env"].items():
        if not env:
            continue
        s = int(C.beats_to_seconds(env[0][0]) * SR)
        s_end = int(C.beats_to_seconds(env[-1][0]) * SR)
        prev = None
        while s <= s_end:
            beat = beat_at_sample(s)
            value = C.macro_value(track, index, beat)
            if prev is None or abs(value - prev) > 0.002:
                events.append((s, 6, index, value))
                prev = value
            s += BLOCK
    events.sort(key=lambda e: (e[0], e[1]))
    return events


def render_track(track, total_frames):
    run = InstrumentRun(INSTRUMENTS / track["script"], SR)
    events = build_events(track)
    data = np.zeros((total_frames, 2), dtype=np.float32)
    cursor = 0
    ei = 0
    while cursor < total_frames:
        frames = min(BLOCK, total_frames - cursor)
        beat = beat_at_sample(cursor)
        num, den = timesig_at_beat(beat)
        shim._transport = (True, cursor / SR, bpm_at_beat(beat), num, den)
        while ei < len(events) and events[ei][0] < cursor + frames:
            _, etype, data0, value0 = events[ei]
            if etype == 1:
                run.deliver(1, 0, -1, data0, value0, 0.0, cursor)
            elif etype == 0:
                run.deliver(2, 0, -1, data0, 0.0, 0.0, cursor)
            else:
                run.deliver(6, 0, -1, data0, value0, 0.0, cursor)
            ei += 1
        raw = run.pull_frames(frames)
        block = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
        block = block.reshape(-1, 2) / 32768.0
        data[cursor:cursor + frames] = block
        cursor += frames
    return data


def apply_mix(track, data, total_frames):
    beats = np.array([beat_at_sample(s)
                      for s in range(0, total_frames, BLOCK)])
    gains = np.array([C.track_gain(track, b) for b in beats],
                     dtype=np.float32)
    gain_per_sample = np.repeat(gains, BLOCK)[:total_frames]
    data *= gain_per_sample[:, None]
    pan = track["pan"]
    if pan:
        data[:, 0] *= min(1.0, 1.0 - pan)
        data[:, 1] *= min(1.0, 1.0 + pan)
    return data


def main():
    out_path = SCORE / "build" / ("%s_preview.wav" % PIECE)
    argv = list(ARGV)
    stems_dir = None
    if "--stems" in argv:
        stems_dir = Path(argv[argv.index("--stems") + 1])
        argv.remove("--stems")
        argv.remove(str(stems_dir))
        stems_dir.mkdir(parents=True, exist_ok=True)
    if argv:
        out_path = Path(argv[0])
    out_path.parent.mkdir(parents=True, exist_ok=True)

    total_frames = int(C.RENDER_SECONDS * SR)
    master = np.zeros((total_frames, 2), dtype=np.float32)
    print("%s: %.1f s song, %.1f s render, %d tracks"
          % (C.TITLE, C.SONG_SECONDS, C.RENDER_SECONDS, len(C.TRACKS)))

    bounds = [(int(C.beats_to_seconds(b0) * SR),
               int(C.beats_to_seconds(b1) * SR))
              for _, b0, b1 in C.SECTIONS]

    section_rms = {}
    for track in C.TRACKS:
        t0 = time.time()
        data = render_track(track, total_frames)
        raw_peak = float(np.abs(data).max())
        data = apply_mix(track, data, total_frames)
        mixed_peak = float(np.abs(data).max())
        section_rms[track["name"]] = [
            float(np.sqrt((data[s0:s1] ** 2).mean())) for s0, s1 in bounds]
        master += data
        elapsed = time.time() - t0
        print("  %-14s raw_peak=%.3f mixed_peak=%.3f (%.1fs)"
              % (track["name"], raw_peak, mixed_peak, elapsed))
        if stems_dir is not None:
            write_wav(stems_dir / (track["script"][:-3] + ".wav"), data)

    print("\nper-track section RMS (dBFS):")
    print("  %-14s " % "track"
          + " ".join("%8s" % name.split()[0] for name, _, _ in C.SECTIONS))
    for track in C.TRACKS:
        vals = section_rms[track["name"]]
        cells = " ".join("%8.1f" % (20 * np.log10(max(v, 1e-9)))
                         if v > 1e-6 else "       ." for v in vals)
        print("  %-14s %s" % (track["name"], cells))

    master *= 10.0 ** (C.MASTER_GAIN_DB / 20.0)
    peak = float(np.abs(master).max())
    print("\nmaster peak %.3f (%.1f dBFS)" % (peak, 20 * np.log10(max(peak, 1e-9))))

    # Section profile. The hp150 column measures only energy above 150 Hz
    # (via FFT band energy) so sub bass doesn't dominate the numbers the
    # way it doesn't dominate the ear.
    mono = master.mean(axis=1)
    print("\nsection profile:")
    for (name, _b0, _b1), (s0, s1) in zip(C.SECTIONS, bounds):
        seg = master[s0:s1]
        rms = float(np.sqrt((seg ** 2).mean()))
        spec = np.fft.rfft(mono[s0:s1])
        freqs = np.fft.rfftfreq(s1 - s0, 1.0 / SR)
        spec[freqs < 150.0] = 0.0
        band = np.fft.irfft(spec, n=s1 - s0)
        wrms = float(np.sqrt((band ** 2).mean()))
        pk = float(np.abs(seg).max())
        print("  %-14s rms=%6.1f dBFS  hp150=%6.1f dBFS  peak=%6.1f dBFS"
              % (name, 20 * np.log10(max(rms, 1e-9)),
                 20 * np.log10(max(wrms, 1e-9)),
                 20 * np.log10(max(pk, 1e-9))))

    worst = 0
    worst_beat = 0.0
    b = 0.0
    while b < C.TOTAL_BEATS:
        n = C.active_track_count(b)
        if n > worst:
            worst, worst_beat = n, b
        b += 0.5
    limit = getattr(C, "ACTIVE_LIMIT", None)
    print("\nmax simultaneous tracks: %d (at beat %.1f)%s"
          % (worst, worst_beat,
             " - limit %d" % limit if limit else " - no limit"))

    write_wav(out_path, master)
    print("\nwrote %s" % out_path)
    ok = peak < 1.0 and (limit is None or worst <= limit)
    return 0 if ok else 1


def write_wav(path, data):
    clipped = np.clip(data, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(SR)
        handle.writeframes(pcm.tobytes())


if __name__ == "__main__":
    raise SystemExit(main())
