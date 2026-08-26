# mpvst-macro-labels: Tone | Space
"""Felt keys: a soft struck tone with a long natural decay, gently
detuned pair, warm low-pass, and a real room. The closing melody
instrument. Macro 1 opens the tone, macro 2 the room.
"""

MACRO_LABELS = (
    "Tone", "Space",
)

# Patch 0 is the sound this instrument's defaults describe, so a fresh
# instance and patch 0 are the same thing - create() applies it. A macro
# a caller does not set resolves here rather than to the middle of its
# range.
PATCHES = {
    0: ('Init', (67, 57)),
}

import audiofreeverb
import synthio

from audioinstruments._support import (
    EVENT_NOTE_ON, EVENT_NOTE_OFF, EVENT_PARAMETER, key_of, logmap,
    make_table,
)
from audioinstruments._support import Instrument
from audioinstruments._support import static_transport
from audioinstruments import _support

FELT = make_table(((1, 1.0), (2, 0.34), (3, 0.08), (4, 0.05), (5, 0.02)), fast=False)
DETUNE = 2.0 ** (2.5 / 1200.0)


def create(sample_rate, transport=None):
    SR = sample_rate
    if transport is None:
        transport = static_transport
    def beat_clock():
        info = transport()
        bpm = info[2] if info[2] and info[2] > 1.0 else 120.0
        return bpm, info[1] * bpm / 60.0
    synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
    verb = audiofreeverb.Freeverb(roomsize=0.87, damp=0.45, mix=0.3,
                                  sample_rate=SR, channel_count=2,
                                  bits_per_sample=16, samples_signed=True,
                                  buffer_size=2048)
    tone = synthio.Math(synthio.MathOperation.SUM, 2400.0, 0.0, 0.0)
    lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, tone, Q=0.75)
    env = synthio.Envelope(attack_time=0.004, decay_time=2.4,
                           release_time=0.6, attack_level=1.0,
                           sustain_level=0.12)

    verb.play(synth)

    voices = {}
    serial = 0




    def release_voice(k):
        _support.release_voice(voices, synth, k)


    def steal_oldest():
        _support.steal_oldest(voices, release_voice)

    MAX_VOICES = 6


    def handle_event(event_type, channel, note_id, data0, value0, value1,
                     sample_position):
        nonlocal serial
        k = key_of(channel, note_id, data0)
        if event_type == EVENT_NOTE_ON and value0 > 0.0:
            release_voice(k)
            if len(voices) >= MAX_VOICES:
                steal_oldest()
            hz = synthio.midi_to_hz(data0 + value1)
            amp = 0.14 + 0.24 * value0
            a = synthio.Note(hz * DETUNE, waveform=FELT, envelope=env,
                             filter=lp, amplitude=amp, panning=-0.12)
            b = synthio.Note(hz / DETUNE, waveform=FELT, envelope=env,
                             filter=lp, amplitude=amp * 0.8, panning=0.12)
            serial += 1
            voices[k] = ((a, b), serial)
            synth.press(a)
            synth.press(b)
        elif event_type in (EVENT_NOTE_OFF, EVENT_NOTE_ON):
            release_voice(k)
        elif event_type == EVENT_PARAMETER:
            if data0 == 0:
                tone.a = logmap(value0, 1100.0, 4800.0)
            elif data0 == 1:
                verb.mix = 0.12 + 0.4 * value0

    instrument = Instrument(synth, handle_event, PATCHES, MACRO_LABELS,
                            transport=transport, output=verb)
    instrument.program_change(0)
    return instrument


if __name__ == "__main__":
    import mpvst_adapter

    mpvst_adapter.attach(create)
