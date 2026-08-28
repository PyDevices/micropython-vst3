# mpvst-macro-labels: Doom | Space
"""Cinematic impact: every note fires three layers - a sub boom with a
falling pitch, a braam of detuned saws (root and fifth) whose filter
blooms open, and a noise crack transient - into a huge room. Macro 1
darkens or opens the braam, macro 2 the room.
"""

MACRO_LABELS = (
    "Doom", "Space",
)

# Patch 0 is the sound this instrument's defaults describe, so a fresh
# instance and patch 0 are the same thing - create() applies it. A macro
# a caller does not set resolves here rather than to the middle of its
# range.
PATCHES = {
    0: ('Init', (65, 73)),
}

import array
import audiofreeverb
import synthio

from audioinstruments._support import (
    EVENT_NOTE_ON, EVENT_NOTE_OFF, EVENT_PARAMETER, FALL, key_of, logmap,
    make_table, noise_table,
)
from audioinstruments._support import Instrument
from audioinstruments import _support

SINE = make_table(((1, 1.0), (2, 0.12)), fast=False)
SAW = make_table([(n, 1.0 / n) for n in range(1, 23)], fast=False)
NOISE = noise_table(seed=192837465)
RISE = array.array("h", (0, 32767))
DETUNE = 2.0 ** (9.0 / 1200.0)


def create(sample_rate, transport=None):
    SR = sample_rate
    NOISE_HZ = SR / 8192.0
    synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
    verb = audiofreeverb.Freeverb(roomsize=0.95, damp=0.4, mix=0.38,
                                  sample_rate=SR, channel_count=2,
                                  bits_per_sample=16, samples_signed=True,
                                  buffer_size=2048)
    doom = synthio.Math(synthio.MathOperation.SUM, 500.0, 0.0, 0.0)

    boom_env = synthio.Envelope(attack_time=0.002, decay_time=2.6,
                                release_time=1.2, attack_level=1.0,
                                sustain_level=0.0)
    braam_env = synthio.Envelope(attack_time=0.7, decay_time=1.6,
                                 release_time=2.4, attack_level=1.0,
                                 sustain_level=0.35)
    crack_env = synthio.Envelope(attack_time=0.001, decay_time=0.14,
                                 release_time=0.1, attack_level=1.0,
                                 sustain_level=0.0)
    crack_hp = synthio.Biquad(synthio.FilterMode.HIGH_PASS, 1400.0, Q=0.8)
    boom_lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, 160.0, Q=0.9)

    verb.play(synth)

    voices = {}
    MAX_VOICES = 2
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
            amp = 0.26 + 0.36 * value0
            drop = synthio.LFO(waveform=FALL, once=True, rate=1.0 / 0.4,
                               scale=0.6, interpolate=True)
            boom = synthio.Note(hz * 0.5, waveform=SINE, envelope=boom_env,
                                filter=boom_lp, amplitude=amp, bend=drop)
            bloom = synthio.LFO(waveform=RISE, once=True, rate=1.0 / 1.2,
                                scale=doom, interpolate=True)
            bfreq = synthio.Math(synthio.MathOperation.SUM, 110.0, bloom, 0.0)
            blp = synthio.Biquad(synthio.FilterMode.LOW_PASS, bfreq, Q=1.6)
            braam_a = synthio.Note(hz * DETUNE, waveform=SAW, envelope=braam_env,
                                   filter=blp, amplitude=amp * 0.6, panning=-0.3)
            braam_b = synthio.Note(hz * 1.5 / DETUNE, waveform=SAW,
                                   envelope=braam_env, filter=blp,
                                   amplitude=amp * 0.42, panning=0.3)
            crack = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=crack_env,
                                 filter=crack_hp, amplitude=amp * 0.3)
            serial += 1
            voices[k] = ((boom, braam_a, braam_b, crack), serial)
            for note in voices[k][0]:
                synth.press(note)
        elif event_type in (EVENT_NOTE_OFF, EVENT_NOTE_ON):
            release_voice(k)
        elif event_type == EVENT_PARAMETER:
            if data0 == 0:
                doom.a = logmap(value0, 140.0, 1700.0)
            elif data0 == 1:
                verb.mix = 0.15 + 0.4 * value0

    instrument = Instrument(synth, handle_event, PATCHES, MACRO_LABELS,
                            transport=transport, output=verb)
    instrument.program_change(0)
    return instrument


if __name__ == "__main__":
    import mpvst_adapter

    mpvst_adapter.attach(create)
