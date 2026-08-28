# mpvst-macro-labels: Cutoff | Resonance | Punch
"""Ostinato Moog bass: saw plus a sub-octave square through a resonant
low-pass. Macro 1 sweeps the cutoff, macro 2 the resonance, macro 3 sets
how hard the per-note filter pluck opens. This is the automation star of
the score.
"""

MACRO_LABELS = (
    "Cutoff", "Resonance", "Punch",
)

# Patch 0 is the sound this instrument's defaults describe, so a fresh
# instance and patch 0 are the same thing - create() applies it. A macro
# a caller does not set resolves here rather than to the middle of its
# range.
PATCHES = {
    0: ('Init', (64, 11, 56)),
}

import synthio

from audioinstruments._support import (
    EVENT_NOTE_ON, EVENT_NOTE_OFF, EVENT_PARAMETER, FALL, key_of, logmap,
    make_table,
)
from audioinstruments._support import Instrument
from audioinstruments import _support

SAW = make_table([(n, 1.0 / n) for n in range(1, 29)], fast=False)
SQUARE = make_table([(n, 1.0 / n) for n in range(1, 16, 2)], fast=False)

# One-shot downward ramp used as the per-note filter pluck.


def create(sample_rate, transport=None):
    SR = sample_rate
    synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
    cutoff = synthio.Math(synthio.MathOperation.SUM, 700.0, 0.0, 0.0)
    resonance = synthio.Math(synthio.MathOperation.SUM, 1.4, 0.0, 0.0)
    punch = 1600.0

    env = synthio.Envelope(attack_time=0.006, decay_time=0.18,
                           release_time=0.12, attack_level=1.0,
                           sustain_level=0.55)

    voices = {}
    MAX_VOICES = 3
    serial = 0




    def release_voice(k):
        _support.release_voice(voices, synth, k)


    def steal_oldest():
        _support.steal_oldest(voices, release_voice)


    def handle_event(event_type, channel, note_id, data0, value0, value1,
                     sample_position):
        nonlocal serial, punch
        k = key_of(channel, note_id, data0)
        if event_type == EVENT_NOTE_ON and value0 > 0.0:
            release_voice(k)
            if len(voices) >= MAX_VOICES:
                steal_oldest()
            hz = synthio.midi_to_hz(data0 + value1)
            amp = 0.22 + 0.30 * value0
            pluck = synthio.LFO(waveform=FALL, once=True, rate=4.0,
                                scale=punch * (0.4 + 0.6 * value0),
                                interpolate=True)
            freq = synthio.Math(synthio.MathOperation.SUM, cutoff, pluck, 0.0)
            flt = synthio.Biquad(synthio.FilterMode.LOW_PASS, freq, Q=resonance)
            a = synthio.Note(hz, waveform=SAW, envelope=env, filter=flt,
                             amplitude=amp, panning=-0.1, bend=0.001)
            b = synthio.Note(hz * 0.5, waveform=SQUARE, envelope=env, filter=flt,
                             amplitude=amp * 0.8, panning=0.1)
            serial += 1
            voices[k] = ((a, b), serial)
            synth.press(a)
            synth.press(b)
        elif event_type in (EVENT_NOTE_OFF, EVENT_NOTE_ON):
            release_voice(k)
        elif event_type == EVENT_PARAMETER:
            if data0 == 0:
                cutoff.a = logmap(value0, 90.0, 5200.0)
            elif data0 == 1:
                resonance.a = 0.8 + 6.7 * value0
            elif data0 == 2:
                punch = 3600.0 * value0

    instrument = Instrument(synth, handle_event, PATCHES, MACRO_LABELS,
                            transport=transport)
    instrument.program_change(0)
    return instrument


if __name__ == "__main__":
    import mpvst_adapter

    mpvst_adapter.attach(create)
