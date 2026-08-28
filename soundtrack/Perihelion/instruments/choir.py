# mpvst-macro-labels: Vowel | Space
"""Choir pad: each voice is three layers - a soft fundamental plus two
band-pass formant layers around 850 and 1250 Hz, which reads as an "ah"
vowel. Macro 1 shifts the formant centers (ooh to ah), macro 2 the hall.
"""

MACRO_LABELS = (
    "Vowel", "Space",
)

# Patch 0 is the sound this instrument's defaults describe, so a fresh
# instance and patch 0 are the same thing - create() applies it. A macro
# a caller does not set resolves here rather than to the middle of its
# range.
PATCHES = {
    0: ('Init', (54, 79)),
}

import audiofreeverb
import synthio

from audioinstruments._support import (
    EVENT_NOTE_ON, EVENT_NOTE_OFF, EVENT_PARAMETER, key_of, make_table,
)
from audioinstruments._support import Instrument
from audioinstruments import _support

VOICE = make_table([(n, 1.0 / (n ** 1.1)) for n in range(1, 15)], fast=False)


def create(sample_rate, transport=None):
    SR = sample_rate
    synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
    verb = audiofreeverb.Freeverb(roomsize=0.92, damp=0.4, mix=0.4,
                                  sample_rate=SR, channel_count=2,
                                  bits_per_sample=16, samples_signed=True,
                                  buffer_size=2048)
    formant1 = synthio.Math(synthio.MathOperation.SUM, 850.0, 0.0, 0.0)
    formant2 = synthio.Math(synthio.MathOperation.SUM, 1250.0, 0.0, 0.0)
    bp1 = synthio.Biquad(synthio.FilterMode.BAND_PASS, formant1, Q=4.5)
    bp2 = synthio.Biquad(synthio.FilterMode.BAND_PASS, formant2, Q=5.5)
    soft = synthio.Biquad(synthio.FilterMode.LOW_PASS, 900.0, Q=0.8)
    env = synthio.Envelope(attack_time=0.9, decay_time=0.4, release_time=2.0,
                           attack_level=1.0, sustain_level=0.85)

    verb.play(synth)

    voices = {}
    MAX_VOICES = 4
    serial = 0




    def release_voice(k):
        _support.release_voice(voices, synth, k)


    def steal_oldest():
        _support.steal_oldest(voices, release_voice)


    def handle_event(event_type, channel, note_id, data0, value0, value1,
                     sample_position):
        nonlocal serial
        k = key_of(channel, note_id, data0)
        if event_type == EVENT_NOTE_ON and value0 > 0.0:
            release_voice(k)
            if len(voices) >= MAX_VOICES:
                steal_oldest()
            hz = synthio.midi_to_hz(data0 + value1)
            amp = 0.09 + 0.12 * value0
            vib = synthio.LFO(rate=4.1, scale=0.004,
                              phase_offset=0.37 * (serial % 3))
            base = synthio.Note(hz, waveform=VOICE, envelope=env, filter=soft,
                                amplitude=amp, panning=0.0, bend=vib)
            f1 = synthio.Note(hz, waveform=VOICE, envelope=env, filter=bp1,
                              amplitude=amp * 0.75, panning=-0.35, bend=vib)
            f2 = synthio.Note(hz, waveform=VOICE, envelope=env, filter=bp2,
                              amplitude=amp * 0.55, panning=0.35, bend=vib)
            serial += 1
            voices[k] = ((base, f1, f2), serial)
            synth.press(base)
            synth.press(f1)
            synth.press(f2)
        elif event_type in (EVENT_NOTE_OFF, EVENT_NOTE_ON):
            release_voice(k)
        elif event_type == EVENT_PARAMETER:
            if data0 == 0:
                shift = 0.7 + 0.7 * value0
                formant1.a = 850.0 * shift
                formant2.a = 1250.0 * shift
            elif data0 == 1:
                verb.mix = 0.15 + 0.4 * value0

    instrument = Instrument(synth, handle_event, PATCHES, MACRO_LABELS,
                            transport=transport, output=verb)
    instrument.program_change(0)
    return instrument


if __name__ == "__main__":
    import mpvst_adapter

    mpvst_adapter.attach(create)
