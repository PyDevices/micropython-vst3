# mpvst-macro-labels: Tone | Space
"""Timpani: a struck fundamental with a fast downward pitch settle plus a
filtered noise thump, in a large room. Rolls are just repeated notes.
Macro 1 opens the strike tone, macro 2 the room.
"""

MACRO_LABELS = (
    "Tone", "Space",
)

# Patch 0 is the sound this instrument's defaults describe, so a fresh
# instance and patch 0 are the same thing - create() applies it. A macro
# a caller does not set resolves here rather than to the middle of its
# range.
PATCHES = {
    0: ('Init', (65, 57)),
}

import audiofreeverb
import synthio

from audioinstruments._support import (
    EVENT_NOTE_ON, EVENT_NOTE_OFF, EVENT_PARAMETER, FALL, key_of, logmap,
    make_table, noise_table,
)
from audioinstruments._support import Instrument
from audioinstruments import _support

DRUM = make_table(((1, 1.0), (1.5, 0.35), (1.98, 0.2), (2.44, 0.1)), fast=False)
NOISE = noise_table(seed=987654321)


def create(sample_rate, transport=None):
    SR = sample_rate
    NOISE_HZ = SR / 8192.0
    synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
    verb = audiofreeverb.Freeverb(roomsize=0.92, damp=0.5, mix=0.3,
                                  sample_rate=SR, channel_count=2,
                                  bits_per_sample=16, samples_signed=True,
                                  buffer_size=2048)
    tone = synthio.Math(synthio.MathOperation.SUM, 420.0, 0.0, 0.0)
    tone_lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, tone, Q=1.0)
    thump_lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, 240.0, Q=0.9)

    strike_env = synthio.Envelope(attack_time=0.002, decay_time=0.9,
                                  release_time=0.6, attack_level=1.0,
                                  sustain_level=0.0)
    thump_env = synthio.Envelope(attack_time=0.001, decay_time=0.09,
                                 release_time=0.09, attack_level=1.0,
                                 sustain_level=0.0)

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
            amp = 0.24 + 0.4 * value0
            settle = synthio.LFO(waveform=FALL, once=True, rate=1.0 / 0.07,
                                 scale=0.3, interpolate=True)
            strike = synthio.Note(hz, waveform=DRUM, envelope=strike_env,
                                  filter=tone_lp, amplitude=amp, bend=settle,
                                  panning=-0.05)
            thump = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=thump_env,
                                 filter=thump_lp, amplitude=amp * 0.6,
                                 panning=0.05)
            serial += 1
            voices[k] = ((strike, thump), serial)
            synth.press(strike)
            synth.press(thump)
        elif event_type in (EVENT_NOTE_OFF, EVENT_NOTE_ON):
            release_voice(k)
        elif event_type == EVENT_PARAMETER:
            if data0 == 0:
                tone.a = logmap(value0, 180.0, 950.0)
            elif data0 == 1:
                verb.mix = 0.12 + 0.4 * value0

    instrument = Instrument(synth, handle_event, PATCHES, MACRO_LABELS,
                            transport=transport, output=verb)
    instrument.program_change(0)
    return instrument


if __name__ == "__main__":
    import mpvst_adapter

    mpvst_adapter.attach(create)
