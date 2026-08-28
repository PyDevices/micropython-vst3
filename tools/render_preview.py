#!/usr/bin/env python3
"""Render a piece offline through the audioif CPython wheel.

The render loop, the tempo math, the mixing and the level report all live
in audioif's `audiorender`. What stays here is the part that is about this
plug-in: instruments are loaded the way the sidecar loads them - a script
exec'd against the vstaudio shim - rather than imported as
`audioinstruments` modules. That keeps the preview a check on the same
path the bounce takes. The shim drives the same adapter as the sidecar, so
normalized host values cross the same MIDI-unit boundary in both paths.

Writes a stereo master WAV plus an analysis report (peaks, RMS per
section, simultaneous-track counts).

Usage: render_preview.py [--piece NAME] [out.wav] [--stems DIR]
"""

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SOUNDTRACK = SCRIPT_DIR.parent / "soundtrack"
# piece.py and harness.py are both siblings now, so one entry covers both.
# harness puts audioif's lib/ on the path, which is where audiorender is.
sys.path.insert(0, str(SCRIPT_DIR))

from harness import EffectRun, InstrumentRun  # noqa: E402
from piece import load_piece, patch_macros, piece_arg  # noqa: E402
import vstaudio as shim  # noqa: E402

import audiorender  # noqa: E402

PIECE, ARGV = piece_arg(sys.argv[1:])
C, INSTRUMENTS = load_piece(PIECE)

SR = C.SAMPLE_RATE

#: audiorender's event kinds, as the vstaudio event values a script reads.
#: Both sets are historical wire values and neither may be renumbered, so
#: the translation is a table rather than an assumption that they match.
EVENT_OF = {
    audiorender.NOTE_ON: shim.EVENT_NOTE_ON,
    audiorender.NOTE_OFF: shim.EVENT_NOTE_OFF,
    audiorender.MACRO: shim.EVENT_PARAMETER,
    audiorender.PROGRAM: shim.EVENT_PROGRAM_CHANGE,
}


class ScriptVoice:
    """One instrument script, driven through the sidecar's own API.

    Values cross the same normalized-host-to-MIDI-provider conversion as the
    plug-in. That keeps this preview's contract check honest: the script sees
    the units the real sidecar sends, including MIDI's 128-step quantization.
    """

    def __init__(self, script_path):
        self.run = InstrumentRun(script_path, SR)

    def deliver(self, event, sample_position):
        _position, kind, data, value = event
        self.run.deliver(EVENT_OF[kind], 0, -1, data, value, 0.0,
                         sample_position)

    def pull_frames(self, frames):
        return self.run.pull_frames(frames)


class ShimClock(audiorender.Clock):
    """A transport the scripts can read, published where the shim keeps it."""

    def move_to(self, sample):
        audiorender.Clock.move_to(self, sample)
        shim._transport = self.reading


def voice_for(track, _clock):
    return ScriptVoice(INSTRUMENTS / track["script"])


def patch_for(track):
    """Patch 0's macros - what a macro the composition does not set means.

    Read the same way generate_project.py reads it. If these two disagree
    the preview stops being a usable check on the bounce.
    """
    patch, _name = patch_macros(INSTRUMENTS / track["script"])
    return patch


def effects_for(track):
    for effect in track.get("effects", ()):
        name = "<%s: %s>" % (track["name"], effect["name"])

        def stage(pcm, effect=effect, name=name):
            run = EffectRun(effect["source"], pcm, SR, name)
            # All sixteen, including the ones the rack does not set, because
            # that is what the plug-in does: a VST parameter always has a
            # value, and generate_project.py writes all sixteen into the
            # project. Delivering only the named ones would leave this
            # preview disagreeing with the bounce it exists to check - which
            # it did, silently, until now. Only Perihelion's fx_space reads
            # them; every other rack in the soundtrack is static.
            for index in range(16):
                run.deliver(shim.EVENT_PARAMETER, 0, -1, index,
                            C.macro_value(effect, index, 0.0), 0.0, 0)
            return run

        yield stage


def main():
    out_path = SOUNDTRACK / "build" / ("%s_preview.wav" % PIECE)
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

    master = audiorender.render(
        C, voice_for, patch_for=patch_for, effects_for=effects_for,
        clock=ShimClock(audiorender.TempoMap.of(C)), out=print,
        stems=stems_dir)
    ok = audiorender.report(master)

    audiorender.write_wav(out_path, master.data, master.sample_rate)
    print("\nwrote %s" % out_path)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
