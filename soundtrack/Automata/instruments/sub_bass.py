# mpvst-macro-labels: Level
"""Clean sine sub. Dry, tight, monophonic-ish. Macro 1 trims the level."""

MACRO_LABELS = (
    "Level",
)

# Patch 0 is the sound this instrument's defaults describe, so a fresh
# instance and patch 0 are the same thing - create() applies it. A macro
# a caller does not set resolves here rather than to the middle of its
# range.
PATCHES = {
    0: ('Init', (82,)),
}

import synthio

from audioinstruments._support import (
    EVENT_NOTE_ON, EVENT_NOTE_OFF, EVENT_PARAMETER, key_of, make_table,
)
from audioinstruments._support import Instrument
from audioinstruments._support import static_transport
from audioinstruments import _support

SINE = make_table(((1, 1.0),), fast=False)


def create(sample_rate, transport=None):
    SR = sample_rate
    if transport is None:
        transport = static_transport
    def beat_clock():
        info = transport()
        bpm = info[2] if info[2] and info[2] > 1.0 else 120.0
        return bpm, info[1] * bpm / 60.0
    synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
    env = synthio.Envelope(attack_time=0.005, decay_time=0.1,
                           release_time=0.07, attack_level=1.0,
                           sustain_level=0.88)
    level = 0.75

    voices = {}
    serial = 0




    def release_voice(k):
        _support.release_voice(voices, synth, k)


    def steal_oldest():
        _support.steal_oldest(voices, release_voice)

    MAX_VOICES = 2


    def handle_event(event_type, channel, note_id, data0, value0, value1,
                     sample_position):
        nonlocal serial, level
        k = key_of(channel, note_id, data0)
        if event_type == EVENT_NOTE_ON and value0 > 0.0:
            release_voice(k)
            if len(voices) >= MAX_VOICES:
                steal_oldest()
            amp = (0.3 + 0.5 * value0) * level
            note = synthio.Note(synthio.midi_to_hz(data0 + value1),
                                waveform=SINE, envelope=env, amplitude=amp)
            serial += 1
            voices[k] = ((note,), serial)
            synth.press(note)
        elif event_type in (EVENT_NOTE_OFF, EVENT_NOTE_ON):
            release_voice(k)
        elif event_type == EVENT_PARAMETER:
            if data0 == 0:
                level = 0.3 + 0.7 * value0

    instrument = Instrument(synth, handle_event, PATCHES, MACRO_LABELS,
                            transport=transport)
    instrument.program_change(0)
    return instrument


if __name__ == "__main__":
    import mpvst_adapter

    mpvst_adapter.attach(create)
