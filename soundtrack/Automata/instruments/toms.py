# mpvst-macro-labels: Tone | Room
"""Toms: pitched drum voices - sine body with a settle, a skin-noise
transient - panned across the kit by MIDI pitch. Macro 1 opens the
body tone, macro 2 the room.
"""

MACRO_LABELS = (
    "Tone", "Room",
)

# Patch 0 is the sound this instrument's defaults describe, so a fresh
# instance and patch 0 are the same thing - create() applies it. A macro
# a caller does not set resolves here rather than to the middle of its
# range.
PATCHES = {
    0: ('Init', (66, 70)),
}

import audiofreeverb
import synthio

from audioinstruments._support import (
    EVENT_NOTE_ON, EVENT_NOTE_OFF, EVENT_PARAMETER, FALL, key_of, logmap,
    make_table, noise_table,
)
from audioinstruments._support import Instrument
from audioinstruments import _support

BODY = make_table(((1, 1.0), (1.5, 0.3), (2.1, 0.12)), fast=False)
NOISE = noise_table(seed=1029384756)


def create(sample_rate, transport=None):
    SR = sample_rate
    NOISE_HZ = SR / 8192.0
    synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
    verb = audiofreeverb.Freeverb(roomsize=0.85, damp=0.5, mix=0.22,
                                  sample_rate=SR, channel_count=2,
                                  bits_per_sample=16, samples_signed=True,
                                  buffer_size=2048)
    tone = synthio.Math(synthio.MathOperation.SUM, 600.0, 0.0, 0.0)
    body_lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, tone, Q=0.9)
    skin_bp = synthio.Biquad(synthio.FilterMode.BAND_PASS, 900.0, Q=0.8)

    body_env = synthio.Envelope(attack_time=0.002, decay_time=0.42,
                                release_time=0.2, attack_level=1.0,
                                sustain_level=0.0)
    skin_env = synthio.Envelope(attack_time=0.001, decay_time=0.045,
                                release_time=0.03, attack_level=1.0,
                                sustain_level=0.0)

    verb.play(synth)

    voices = {}
    serial = 0




    def release_voice(k):
        _support.release_voice(voices, synth, k)


    def steal_oldest():
        _support.steal_oldest(voices, release_voice)

    MAX_VOICES = 4


    def handle_event(event_type, channel, note_id, data0, value0, value1,
                     sample_position):
        nonlocal serial
        k = key_of(channel, note_id, data0)
        if event_type == EVENT_NOTE_ON and value0 > 0.0:
            release_voice(k)
            if len(voices) >= MAX_VOICES:
                steal_oldest()
            hz = synthio.midi_to_hz(data0 + value1)
            amp = 0.28 + 0.45 * value0
            pan = max(-0.5, min(0.5, (data0 - 47) * 0.12))
            settle = synthio.LFO(waveform=FALL, once=True, rate=1.0 / 0.09,
                                 scale=0.35, interpolate=True)
            body = synthio.Note(hz, waveform=BODY, envelope=body_env,
                                filter=body_lp, amplitude=amp, bend=settle,
                                panning=pan)
            skin = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=skin_env,
                                filter=skin_bp, amplitude=amp * 0.5,
                                panning=pan)
            serial += 1
            voices[k] = ((body, skin), serial)
            synth.press(body)
            synth.press(skin)
        elif event_type in (EVENT_NOTE_OFF, EVENT_NOTE_ON):
            release_voice(k)
        elif event_type == EVENT_PARAMETER:
            if data0 == 0:
                tone.a = logmap(value0, 260.0, 1300.0)
            elif data0 == 1:
                verb.mix = 0.4 * value0

    instrument = Instrument(synth, handle_event, PATCHES, MACRO_LABELS,
                            transport=transport, output=verb)
    instrument.program_change(0)
    return instrument


if __name__ == "__main__":
    import mpvst_adapter

    mpvst_adapter.attach(create)
