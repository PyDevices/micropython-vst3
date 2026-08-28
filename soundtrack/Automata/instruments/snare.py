# mpvst-macro-labels: Tone | Room
"""Snare: tonal body at 185 Hz with a quick settle, band-passed wire noise,
and a high sizzle layer. Velocity mostly drives the noise, so ghost
notes come out as soft body taps. Macro 1 moves the wire band, macro 2
the room.
"""

MACRO_LABELS = (
    "Tone", "Room",
)

# Patch 0 is the sound this instrument's defaults describe, so a fresh
# instance and patch 0 are the same thing - create() applies it. A macro
# a caller does not set resolves here rather than to the middle of its
# range.
PATCHES = {
    0: ('Init', (52, 51)),
}

import audiofreeverb
import synthio

from audioinstruments._support import (
    EVENT_NOTE_ON, EVENT_NOTE_OFF, EVENT_PARAMETER, FALL, key_of, logmap,
    make_table, noise_table,
)
from audioinstruments._support import Instrument
from audioinstruments import _support

BODY = make_table(((1, 1.0), (1.6, 0.4)), fast=False)
NOISE = noise_table(seed=87654321)


def create(sample_rate, transport=None):
    SR = sample_rate
    NOISE_HZ = SR / 8192.0
    synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
    verb = audiofreeverb.Freeverb(roomsize=0.75, damp=0.5, mix=0.14,
                                  sample_rate=SR, channel_count=2,
                                  bits_per_sample=16, samples_signed=True,
                                  buffer_size=2048)
    wire_center = synthio.Math(synthio.MathOperation.SUM, 1700.0, 0.0, 0.0)
    wire_bp = synthio.Biquad(synthio.FilterMode.BAND_PASS, wire_center, Q=1.1)
    sizzle_hp = synthio.Biquad(synthio.FilterMode.HIGH_PASS, 5200.0, Q=0.7)

    body_env = synthio.Envelope(attack_time=0.001, decay_time=0.1,
                                release_time=0.05, attack_level=1.0,
                                sustain_level=0.0)
    wire_env = synthio.Envelope(attack_time=0.001, decay_time=0.13,
                                release_time=0.07, attack_level=1.0,
                                sustain_level=0.0)
    sizzle_env = synthio.Envelope(attack_time=0.001, decay_time=0.2,
                                  release_time=0.1, attack_level=1.0,
                                  sustain_level=0.0)

    verb.play(synth)

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
            amp = 0.3 + 0.5 * value0
            settle = synthio.LFO(waveform=FALL, once=True, rate=16.0,
                                 scale=0.22, interpolate=True)
            body = synthio.Note(185.0, waveform=BODY, envelope=body_env,
                                amplitude=amp * 0.8, bend=settle)
            wire = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=wire_env,
                                filter=wire_bp,
                                amplitude=amp * (0.25 + 0.75 * value0))
            sizzle = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=sizzle_env,
                                  filter=sizzle_hp,
                                  amplitude=amp * 0.5 * value0, panning=0.06)
            serial += 1
            voices[k] = ((body, wire, sizzle), serial)
            for note in voices[k][0]:
                synth.press(note)
        elif event_type in (EVENT_NOTE_OFF, EVENT_NOTE_ON):
            release_voice(k)
        elif event_type == EVENT_PARAMETER:
            if data0 == 0:
                wire_center.a = logmap(value0, 1100.0, 3200.0)
            elif data0 == 1:
                verb.mix = 0.35 * value0

    instrument = Instrument(synth, handle_event, PATCHES, MACRO_LABELS,
                            transport=transport, output=verb)
    instrument.program_change(0)
    return instrument


if __name__ == "__main__":
    import mpvst_adapter

    mpvst_adapter.attach(create)
