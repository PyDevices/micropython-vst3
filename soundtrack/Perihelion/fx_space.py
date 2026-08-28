"""A scripted send-style effect built from the shared effects library:
the host audio runs through a swept tone filter, a wobbling tape delay,
and a hall. Macro 1 is the reverb mix, macro 2 the echo send, macro 3
the tone."""

NAME = "fx_space"
DISPLAY_NAME = "Air Space"
CATEGORIES = ("Effect Rack", "Reverb")
VERSION = "0.0.1"
VENDOR = "PyDevices"
MACRO_LABELS = ("Space", "Echo", "Tone")
MACRO_MODES = {0: "UNIPOLAR", 1: "UNIPOLAR", 2: "UNIPOLAR"}
PATCHES = {0: ("Air Space", (64, 53, 85))}

import vstaudio
import audioeffects

RATE = vstaudio.sample_rate()

tone = audioeffects.create("LowPass", vstaudio.input(), RATE, frequency=4200.0)
tape = audioeffects.create("TapeDelay", tone.output, RATE, time_ms=375.0,
                           feedback=0.4, mix=0.25)
hall = audioeffects.create("Reverb", tape.output, RATE, preset="hall",
                           mix=0.3)


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
        hall.set_mix(0.6 * value0)
    elif data0 == 1:
        tape.set_mix(0.6 * value0)
    elif data0 == 2:
        tone.set_frequency(logmap(value0, 500.0, 12000.0))


vstaudio.on_event(handle_event)
vstaudio.output(hall.output)
