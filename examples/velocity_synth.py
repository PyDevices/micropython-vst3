# mpvst-macro-labels: Level | Bend Range

import synthio
import vstaudio


synth = synthio.Synthesizer(sample_rate=vstaudio.sample_rate(), channel_count=2)
envelope = synthio.Envelope(attack_time=0.005, decay_time=0.08,
                            release_time=0.15, attack_level=1.0,
                            sustain_level=0.75)
voices = {}
level = 0.8
bend_range = 2.0


def key(channel, note_id, pitch):
    return (channel, note_id if note_id >= 0 else pitch)


def handle_event(event_type, channel, note_id, data0, value0, value1,
                 sample_position):
    global level, bend_range
    del sample_position
    voice_key = key(channel, note_id, data0)
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        old = voices.pop(voice_key, None)
        if old is not None:
            synth.release(old[0])
        velocity = min(max(value0, 0.0), 1.0)
        note = synthio.Note(synthio.midi_to_hz(data0 + value1),
                            amplitude=velocity * level, envelope=envelope)
        voices[voice_key] = (note, velocity)
        synth.press(note)
    elif event_type == vstaudio.EVENT_NOTE_OFF:
        voice = voices.pop(voice_key, None)
        if voice is not None:
            synth.release(voice[0])
    elif event_type == vstaudio.EVENT_PITCH_BEND:
        for active_key, voice in voices.items():
            if active_key[0] == channel:
                voice[0].bend = value1 * bend_range
    elif event_type == vstaudio.EVENT_PARAMETER and data0 == 0:
        level = value0
        for voice in voices.values():
            voice[0].amplitude = voice[1] * level
    elif event_type == vstaudio.EVENT_PARAMETER and data0 == 1:
        bend_range = 1.0 + value0 * 11.0


vstaudio.on_event(handle_event)
vstaudio.output(synth)
