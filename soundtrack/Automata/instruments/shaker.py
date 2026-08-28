# mpvst-macro-labels: Color
"""Shaker: a short band-passed noise chick. Groove comes entirely from
velocity accents in the pattern. Macro 1 moves the band.
"""

MACRO_LABELS = (
    "Color",
)

# Patch 0 is the sound this instrument's defaults describe, so a fresh
# instance and patch 0 are the same thing - create() applies it. A macro
# a caller does not set resolves here rather than to the middle of its
# range.
PATCHES = {
    0: ('Init', (70,)),
}

import synthio

from audioinstruments._support import (
    EVENT_NOTE_ON, EVENT_NOTE_OFF, EVENT_PARAMETER, key_of, logmap,
    noise_table,
)
from audioinstruments._support import Instrument
from audioinstruments import _support

NOISE = noise_table(seed=1111999)


def create(sample_rate, transport=None):
    SR = sample_rate
    NOISE_HZ = SR / 8192.0
    synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
    color = synthio.Math(synthio.MathOperation.SUM, 6400.0, 0.0, 0.0)
    bp = synthio.Biquad(synthio.FilterMode.BAND_PASS, color, Q=1.0)
    env = synthio.Envelope(attack_time=0.012, decay_time=0.05,
                           release_time=0.03, attack_level=1.0,
                           sustain_level=0.0)

    voices = {}
    serial = 0




    def release_voice(k):
        _support.release_voice(voices, synth, k)


    def steal_oldest():
        _support.steal_oldest(voices, release_voice)

    MAX_VOICES = 3


    def handle_event(event_type, channel, note_id, data0, value0, value1,
                     sample_position):
        nonlocal serial
        k = key_of(channel, note_id, data0)
        if event_type == EVENT_NOTE_ON and value0 > 0.0:
            release_voice(k)
            if len(voices) >= MAX_VOICES:
                steal_oldest()
            amp = 0.12 + 0.4 * value0
            note = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env,
                                filter=bp, amplitude=amp, panning=-0.2)
            serial += 1
            voices[k] = ((note,), serial)
            synth.press(note)
        elif event_type in (EVENT_NOTE_OFF, EVENT_NOTE_ON):
            release_voice(k)
        elif event_type == EVENT_PARAMETER:
            if data0 == 0:
                color.a = logmap(value0, 4200.0, 9000.0)

    instrument = Instrument(synth, handle_event, PATCHES, MACRO_LABELS,
                            transport=transport)
    instrument.program_change(0)
    return instrument


if __name__ == "__main__":
    import mpvst_adapter

    mpvst_adapter.attach(create)
