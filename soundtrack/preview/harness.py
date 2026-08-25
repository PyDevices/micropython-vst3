"""Offline renderer for the soundtrack instrument scripts.

Runs an instrument file against the vstaudio shim on top of the audioif
CPython wheel - the same DSP code the MicroPython sidecar runs - and pulls
PCM block by block while delivering the composition's events. The REAPER
render through the real plug-in stays authoritative; this exists so the
piece can be iterated and measured quickly.
"""

import struct
import sys
from pathlib import Path

SCORE_DIR = Path(__file__).resolve().parent.parent
AUDIOIF_DIR = SCORE_DIR.parent.parent / "audioif"

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(AUDIOIF_DIR))

import audiocore  # noqa: E402
import vstaudio  # noqa: E402


class InstrumentRun:
    """One loaded instrument script plus its pull-state."""

    def __init__(self, script_path, sample_rate=48000):
        self.sample_rate = sample_rate
        vstaudio._reset(sample_rate)
        source = Path(script_path).read_text()
        namespace = {"__name__": "__main__", "__file__": str(script_path)}
        exec(compile(source, str(script_path), "exec"), namespace, namespace)
        self.handler = vstaudio._handler
        self.output = vstaudio._current_output()
        if self.output is None:
            raise RuntimeError("%s registered no output" % script_path)
        self._pending = b""

    def deliver(self, event_type, channel, note_id, data0, value0, value1,
                sample_position):
        if self.handler is not None:
            self.handler(event_type, channel, note_id, data0, value0, value1,
                         sample_position)

    def pull_frames(self, frames):
        """Return `frames` stereo frames as interleaved int16 bytes."""
        need = frames * 4
        while len(self._pending) < need:
            _, view = audiocore.get_buffer(self.output)
            chunk = bytes(view)
            if not chunk:
                chunk = b"\x00" * 1024
            self._pending += chunk
        out = self._pending[:need]
        self._pending = self._pending[need:]
        return out


def peak_rms(pcm_bytes):
    count = len(pcm_bytes) // 2
    if count == 0:
        return 0.0, 0.0
    values = struct.unpack("<%dh" % count, pcm_bytes[: count * 2])
    peak = max(abs(v) for v in values) / 32768.0
    acc = 0.0
    for v in values:
        acc += (v / 32768.0) ** 2
    return peak, (acc / count) ** 0.5
