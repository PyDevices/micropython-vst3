#!/usr/bin/env python3
"""Write a 16-bit copy of a rendered piece for everyday playback.

REAPER bounces the soundtrack at 24-bit, which plenty of casual players
and browsers won't open. This writes <name>-16bit.wav next to the
original so the piece can just be double-clicked. Lossless in practice
for listening (dither is not applied - the source is already well below
full scale and this is a convenience copy, not a master).

Usage: make_playable.py <in.wav> [more.wav ...]
       make_playable.py --piece NAME     (converts that piece's bounce)
"""

import sys
import wave
from pathlib import Path

import numpy as np

REPO_DIR = Path(__file__).resolve().parent.parent.parent
SOUNDTRACK = REPO_DIR / "soundtrack"


def to_16bit(src):
    src = Path(src)
    with wave.open(str(src)) as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())

    if width == 2:
        samples = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 3:
        raw = np.frombuffer(frames, dtype=np.uint8).reshape(-1, 3)
        # 24-bit little-endian signed -> int32 via the high 3 bytes, then scale
        packed = np.zeros((raw.shape[0], 4), dtype=np.uint8)
        packed[:, 1:] = raw
        samples = (packed.view("<i4").ravel().astype(np.float32)
                   / float(1 << 31))
    elif width == 4:
        samples = np.frombuffer(frames, dtype="<i4").astype(np.float32) / float(1 << 31)
    else:
        raise SystemExit("%s: unsupported sample width %d" % (src, width))

    clipped = np.clip(samples, -1.0, 1.0)
    out = (clipped * 32767.0).astype("<i2")

    dest = src.with_name(src.stem + "-16bit.wav")
    with wave.open(str(dest), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(out.tobytes())
    print("wrote %s (%d-bit -> 16-bit, %.1fs)"
          % (dest, width * 8, len(out) / channels / rate))
    return dest


def main():
    argv = sys.argv[1:]
    if not argv:
        raise SystemExit(__doc__)
    if argv[0] == "--piece":
        if len(argv) < 2:
            raise SystemExit("--piece needs a name")
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from piece import load_piece
        composition, _ = load_piece(argv[1])
        targets = [SOUNDTRACK / "build" / (composition.TITLE + ".wav")]
    else:
        targets = [Path(a) for a in argv]

    for target in targets:
        if not target.is_file():
            raise SystemExit("no such file: %s" % target)
        to_16bit(target)


if __name__ == "__main__":
    main()
