"""Offline runner for MicroPython VST3 instrument/effect scripts.

Runs a script against the vstaudio shim on top of the audioif CPython
wheel - the same DSP code (synthio, audiocore, ...) the real MicroPython
sidecar runs - and pulls PCM block by block. No compiled engine and no
VST3 host involved, so a script loads and runs in milliseconds instead of
the seconds a full plug-in load takes; that's what makes it useful for
iterating across many scripts (see tools/test-instruments-lib.py) or one
script at a time while developing it.

This is a fast correctness check, not a substitute for the real plug-in:
it shares the DSP but not the VST3 processor, the shared-memory protocol,
or macro/state handling. The REAPER render through the real plug-in stays
authoritative for anything the script's audio behavior alone doesn't
cover.
"""

import struct
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
REPO_DIR = TOOLS_DIR.parent

# audioif is a dependency, imported from wherever it is installed --
# pydevices-audioif, from TestPyPI or as an editable install of a sibling
# checkout. It used to be put on sys.path from a sibling directory instead,
# which silently won over the installed wheel and, because this ran at
# sys.path[0], over PYTHONPATH as well: an A/B done by pointing PYTHONPATH at
# another checkout rendered current code twice and came out bit-identical.
sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(REPO_DIR / "lib"))

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


class EffectRun:
    """One effect script fed by a finite stereo int16 host stream."""

    def __init__(self, script_source, input_pcm, sample_rate=48000,
                 name="<effect>"):
        self.sample_rate = sample_rate
        vstaudio._reset(sample_rate)
        vstaudio._set_input(input_pcm)
        namespace = {"__name__": "__main__", "__file__": name}
        exec(compile(script_source, name, "exec"), namespace, namespace)
        self.handler = vstaudio._handler
        self.output = vstaudio._current_output()
        if self.output is None:
            raise RuntimeError("%s registered no output" % name)
        self._pending = b""

    def deliver(self, event_type, channel, note_id, data0, value0, value1,
                sample_position):
        if self.handler is not None:
            self.handler(event_type, channel, note_id, data0, value0, value1,
                         sample_position)

    def pull_frames(self, frames):
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
