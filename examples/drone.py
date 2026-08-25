# mpvst-macro-labels: Level | Pitch

import synthio
import vstaudio


synth = synthio.Synthesizer(sample_rate=vstaudio.sample_rate(), channel_count=2)
note = synthio.Note(110.0, amplitude=0.25)
synth.press(note)


def handle_event(event_type, channel, note_id, data0, value0, value1,
                 sample_position):
    del channel, note_id, value1, sample_position
    if event_type == vstaudio.EVENT_PARAMETER and data0 == 0:
        note.amplitude = value0
    elif event_type == vstaudio.EVENT_PARAMETER and data0 == 1:
        note.frequency = 55.0 * (2.0 ** (value0 * 4.0))


vstaudio.on_event(handle_event)
vstaudio.output(synth)
