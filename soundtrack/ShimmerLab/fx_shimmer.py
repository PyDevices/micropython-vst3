"""The classic shimmer: the signal plus a copy of itself an octave up,
smeared through a tape echo and a long hall.

The octave-up is the whole trick. A reverb on its own gets bigger; a reverb
fed something an octave above what went in keeps growing upward, and that
rising quality is what "shimmer" actually names. The tape echo in between
is what stops it arriving all at once - each repeat is a little darker than
the last, so the octave blooms in and decays rather than sitting there.

Macro 1 is how loud the octave sits under the dry, macro 2 the echo, macro 3
the room, macro 4 how bright the repeats stay.
"""

NAME = "fx_shimmer"
DISPLAY_NAME = "Shimmer Hall"
CATEGORIES = ("Effect Rack", "Reverb")
VERSION = "0.0.1"
VENDOR = "PyDevices"
MACRO_LABELS = ("Shimmer", "Echo", "Space", "Tone")
MACRO_MODES = {0: "UNIPOLAR", 1: "UNIPOLAR", 2: "UNIPOLAR", 3: "UNIPOLAR"}
PATCHES = {0: ("Shimmer Hall", (70, 57, 76, 79))}

import vstaudio
import audioeffects

RATE = vstaudio.sample_rate()

octave = audioeffects.create("Octaver", vstaudio.input(), RATE,
                             down=0.0, up=0.55)
tape = audioeffects.create("TapeDelay", octave.output, RATE, time_ms=420.0,
                           feedback=0.5, mix=0.4, wow=0.3,
                           tone_hz=5600.0, drive=0.2)
hall = audioeffects.create("Reverb", tape.output, RATE, preset="hall",
                           mix=0.45)


def logmap(value, lo, hi):
    return lo * ((hi / lo) ** value)


def handle_event(event_type, channel, note_id, data0, value0, value1,
                 sample_position):
    if event_type == vstaudio.EVENT_PROGRAM_CHANGE:
        patch = PATCHES.get(data0)
        if patch is not None:
            for index, value in enumerate(patch[1]):
                handle_event(vstaudio.EVENT_PARAMETER, channel, note_id, index,
                             value / 127.0, 0.0, sample_position)
        return
    if event_type != vstaudio.EVENT_PARAMETER:
        return
    if data0 == 0:
        # voice[0] is the dry; voice[1] is the octave, which is the only
        # branch this Octaver was asked to build.
        octave.mixer.voice[1].level = value0
    elif data0 == 1:
        tape.set_mix(0.8 * value0)
    elif data0 == 2:
        hall.set_mix(0.7 * value0)
    elif data0 == 3:
        tape.set_macro(4, value0 * 127.0)


vstaudio.on_event(handle_event)
vstaudio.output(hall.output)
