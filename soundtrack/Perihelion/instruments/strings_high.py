# mpvst-macro-labels: Brightness | Space
"""High string ensemble: brighter table than the low section, detuned pair
per voice with independent vibrato phases, singing register. Macro 1 is
brightness, macro 2 the hall.
"""

MACRO_LABELS = (
    "Brightness", "Space",
)

# Patch 0 is the sound this instrument's defaults describe, so a fresh
# instance and patch 0 are the same thing - create() applies it. A macro
# a caller does not set resolves here rather than to the middle of its
# range.
PATCHES = {
    0: ('Init', (72, 57)),
}

import audiofreeverb
import synthio

from audioinstruments._support import (
    EVENT_NOTE_ON, EVENT_NOTE_OFF, EVENT_PARAMETER, key_of, logmap,
    make_table,
)
from audioinstruments._support import Instrument
from audioinstruments import _support

STRING = make_table([(n, 1.0 / (n ** 0.95)) for n in range(1, 27)], fast=False)
DETUNE = 2.0 ** (6.0 / 1200.0)


def create(sample_rate, transport=None):
    SR = sample_rate
    synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
    verb = audiofreeverb.Freeverb(roomsize=0.9, damp=0.42, mix=0.3,
                                  sample_rate=SR, channel_count=2,
                                  bits_per_sample=16, samples_signed=True,
                                  buffer_size=2048)
    cutoff = synthio.Math(synthio.MathOperation.SUM, 2400.0, 0.0, 0.0)
    lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, cutoff, Q=0.8)
    env = synthio.Envelope(attack_time=0.32, decay_time=0.3, release_time=1.6,
                           attack_level=1.0, sustain_level=0.85)

    verb.play(synth)

    voices = {}
    MAX_VOICES = 5
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
            amp = 0.13 + 0.2 * value0
            vib_a = synthio.LFO(rate=5.0 + 0.2 * (serial % 3), scale=0.0065,
                                phase_offset=0.29 * (serial % 3))
            vib_b = synthio.LFO(rate=5.3 - 0.17 * (serial % 3), scale=0.006,
                                phase_offset=0.61 * (serial % 2))
            a = synthio.Note(hz * DETUNE, waveform=STRING, envelope=env,
                             filter=lp, amplitude=amp, panning=-0.35, bend=vib_a)
            b = synthio.Note(hz / DETUNE, waveform=STRING, envelope=env,
                             filter=lp, amplitude=amp, panning=0.35, bend=vib_b)
            serial += 1
            voices[k] = ((a, b), serial)
            synth.press(a)
            synth.press(b)
        elif event_type in (EVENT_NOTE_OFF, EVENT_NOTE_ON):
            release_voice(k)
        elif event_type == EVENT_PARAMETER:
            if data0 == 0:
                cutoff.a = logmap(value0, 620.0, 6800.0)
            elif data0 == 1:
                verb.mix = 0.12 + 0.4 * value0

    instrument = Instrument(synth, handle_event, PATCHES, MACRO_LABELS,
                            transport=transport, output=verb)
    instrument.program_change(0)
    return instrument


if __name__ == "__main__":
    import mpvst_adapter

    mpvst_adapter.attach(create)
