"""The empty slot: a complete instrument that deliberately makes no sound.

Every event path below is real and is the working reference for writing a
script - voices tracked by VST note ID, velocity to amplitude, poly and
channel pressure, pitch bend, an explicit release. The one thing it does not
do is press a note, unless MPVST_DEFAULT_INSTRUMENT_AUDIBLE is set.

Why: this script is what the two generic Script Host classes load when
nothing else is chosen, so a project wired to a Script Host CID instead of a
named instrument's CID gets *this* on every track. When it played, that
mistake sounded like a plausible synth on every track at once, and whoever
rendered it had no way to notice. Silence is the alarm - a dead-air check, a
LUFS read or a glance at a waveform all catch it immediately, and none of
them catch "all sixteen tracks are the same polyphonic synth".

If you actually want the empty slot to sound, set the variable. The test that
proves MIDI reaches synthio does exactly that.
"""

import os
import synthio
import vstaudio

# Set to anything non-empty to let the empty slot press notes.
AUDIBLE = bool(os.getenv("MPVST_DEFAULT_INSTRUMENT_AUDIBLE"))

# What the editor calls this instance. Every script may declare one, and this
# one says what it is so nobody wonders which instrument they are looking at:
# an empty slot, not something they chose.
NAME = "default_instrument"
DISPLAY_NAME = "DEFAULT - empty slot, silent"
MACRO_LABELS = ()
MACRO_MODES = {}
PATCHES = {0: ("Default", ())}


synth = synthio.Synthesizer(sample_rate=vstaudio.sample_rate(), channel_count=2)
notes = {}
voice_envelope = synthio.Envelope(attack_time=0.0,
                                  decay_time=0.0,
                                  release_time=0.05,
                                  attack_level=1.0,
                                  sustain_level=1.0)
if os.getenv("MPVST_NATIVE_TEST_TONE"):
    synth.press(synthio.Note(220.0))


_warned = False


def _warn_once():
    """Say it on the first note, not on every one."""
    global _warned
    if not _warned:
        _warned = True
        print("MPVST: the default instrument is silent - this slot is running"
              " no script. A project wired to a Script Host class ID rather"
              " than a named instrument's will render nothing. Set"
              " MPVST_DEFAULT_INSTRUMENT_AUDIBLE to hear it anyway.")


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
            if AUDIBLE:
                synth.press(note)
            else:
                _warn_once()
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
