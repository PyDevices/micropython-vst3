# mpvst-macro-labels: Punch | Tone
"""Kick drum: a sine body with a fast downward pitch drop plus a click
transient. Macro 1 is decay length, macro 2 darkens the body low-pass
(all the way down it becomes the intro heartbeat). MIDI pitch is
ignored; velocity is everything.
"""

MACRO_LABELS = (
    "Punch", "Tone",
)

# Patch 0 is the sound this instrument's defaults describe, so a fresh
# instance and patch 0 are the same thing - create() applies it. A macro
# a caller does not set resolves here rather than to the middle of its
# range.
PATCHES = {
    0: ('Init', (51, 92)),
}

import synthio

from audioinstruments._support import (
    EVENT_NOTE_ON, EVENT_NOTE_OFF, EVENT_PARAMETER, FALL, key_of, logmap,
    make_table, noise_table,
)
from audioinstruments._support import Instrument
from audioinstruments import _support

BODY = make_table(((1, 1.0), (2, 0.08)), fast=False)
NOISE = noise_table(seed=424242)


def create(sample_rate, transport=None):
    SR = sample_rate
    NOISE_HZ = SR / 8192.0
    synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
    tone = synthio.Math(synthio.MathOperation.SUM, 320.0, 0.0, 0.0)
    body_lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, tone, Q=0.8)
    click_hp = synthio.Biquad(synthio.FilterMode.HIGH_PASS, 2800.0, Q=0.7)
    decay = 0.32

    voices = {}
    serial = 0




    def release_voice(k):
        _support.release_voice(voices, synth, k)


    def steal_oldest():
        _support.steal_oldest(voices, release_voice)

    MAX_VOICES = 2


    def handle_event(event_type, channel, note_id, data0, value0, value1,
                     sample_position):
        nonlocal serial, decay
        k = key_of(channel, note_id, data0)
        if event_type == EVENT_NOTE_ON and value0 > 0.0:
            release_voice(k)
            if len(voices) >= MAX_VOICES:
                steal_oldest()
            amp = 0.35 + 0.55 * value0
            env = synthio.Envelope(attack_time=0.001, decay_time=decay,
                                   release_time=0.06, attack_level=1.0,
                                   sustain_level=0.0)
            drop = synthio.LFO(waveform=FALL, once=True, rate=20.0,
                               scale=1.55, interpolate=True)
            body = synthio.Note(47.0, waveform=BODY, envelope=env,
                                filter=body_lp, amplitude=amp, bend=drop)
            click_env = synthio.Envelope(attack_time=0.0005, decay_time=0.014,
                                         release_time=0.01, attack_level=1.0,
                                         sustain_level=0.0)
            click = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=click_env,
                                 filter=click_hp, amplitude=amp * 0.4 * value0)
            serial += 1
            voices[k] = ((body, click), serial)
            synth.press(body)
            synth.press(click)
        elif event_type in (EVENT_NOTE_OFF, EVENT_NOTE_ON):
            release_voice(k)
        elif event_type == EVENT_PARAMETER:
            if data0 == 0:
                decay = 0.16 + 0.4 * value0
            elif data0 == 1:
                tone.a = logmap(value0, 90.0, 520.0)

    instrument = Instrument(synth, handle_event, PATCHES, MACRO_LABELS,
                            transport=transport)
    instrument.program_change(0)
    return instrument


if __name__ == "__main__":
    import mpvst_adapter

    mpvst_adapter.attach(create)
