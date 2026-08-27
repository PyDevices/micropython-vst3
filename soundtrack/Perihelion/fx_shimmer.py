# mpvst-macro-labels: Shimmer | Echo | Space | Tone
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

import vstaudio
from audioeffects import configure, Octaver, Reverb, TapeDelay

configure(vstaudio.sample_rate())

octave = Octaver(vstaudio.input(), down=0.0, up=0.55)
tape = TapeDelay(octave.output, time_ms=420.0, feedback=0.5, mix=0.4,
                 wow=0.3, tone_hz=5600.0, drive=0.2)
hall = Reverb(tape.output, preset="hall", mix=0.45)


def logmap(value, lo, hi):
    return lo * ((hi / lo) ** value)


def handle_event(event_type, channel, note_id, data0, value0, value1,
                 sample_position):
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
