import os
import synthio
import vstaudio


synth = synthio.Synthesizer(sample_rate=vstaudio.sample_rate(), channel_count=2)
notes = {}
voice_envelope = synthio.Envelope(attack_time=0.0,
                                  decay_time=0.0,
                                  release_time=0.05,
                                  attack_level=1.0,
                                  sustain_level=1.0)
if os.getenv("MPVST_NATIVE_TEST_TONE"):
    synth.press(synthio.Note(220.0))


def note_key(channel, note_id, pitch):
    if note_id >= 0:
        return (channel, note_id)
    return (channel, pitch)


def release_note(channel, note_id, pitch):
    voice = notes.pop(note_key(channel, note_id, pitch), None)
    if voice is not None:
        synth.release(voice[0])


def update_channel(channel, update):
    for key, voice in notes.items():
        if key[0] == channel:
            update(voice)


def handle_event(event_type, channel, note_id, data0, value0, value1, sample_position):
    del sample_position
    if event_type == vstaudio.EVENT_NOTE_ON:
        release_note(channel, note_id, data0)
        if value0 > 0.0:
            velocity = min(value0, 1.0)
            note = synthio.Note(synthio.midi_to_hz(data0 + value1),
                                amplitude=velocity,
                                envelope=voice_envelope)
            notes[note_key(channel, note_id, data0)] = (note, velocity)
            synth.press(note)
    elif event_type == vstaudio.EVENT_NOTE_OFF:
        release_note(channel, note_id, data0)
    elif event_type == vstaudio.EVENT_POLY_PRESSURE:
        voice = notes.get(note_key(channel, note_id, data0))
        if voice is not None:
            voice[0].amplitude = voice[1] * min(max(value0, 0.0), 1.0)
    elif event_type == vstaudio.EVENT_PITCH_BEND:
        bend = value1 * 2.0
        update_channel(channel, lambda voice: setattr(voice[0], "bend", bend))
    elif event_type == vstaudio.EVENT_CHANNEL_PRESSURE:
        pressure = min(max(value0, 0.0), 1.0)
        update_channel(channel,
                       lambda voice: setattr(voice[0], "amplitude",
                                              voice[1] * pressure))


vstaudio.on_event(handle_event)
vstaudio.output(synth)
