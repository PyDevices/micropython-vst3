# mpvst-macro-labels: Space | Echo | Tone
"""A scripted send-style effect built from the shared effects library:
the host audio runs through a swept tone filter, a wobbling tape delay,
and a hall. Macro 1 is the reverb mix, macro 2 the echo send, macro 3
the tone."""

import vstaudio
from audioeffects import configure, LowPass, Reverb, TapeDelay

configure(vstaudio.sample_rate())

tone = LowPass(vstaudio.input(), frequency=4200.0)
tape = TapeDelay(tone.output, time_ms=375.0, feedback=0.4, mix=0.25)
hall = Reverb(tape.output, preset="hall", mix=0.3)


def logmap(value, lo, hi):
    return lo * ((hi / lo) ** value)


def handle_event(event_type, channel, note_id, data0, value0, value1,
                 sample_position):
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
