# mpvst-macro-labels: Cutoff | Resonance | Echo
"""Pulse sequencer: plucked square/saw hybrid with a small per-note filter
snap and a dotted-eighth echo, notes alternating left and right. The
rising-cutoff arpeggio is the classic analog build device: automate
macro 1 upward across a section. Macro 2 is resonance, macro 3 the echo.
"""

MACRO_LABELS = (
    "Cutoff", "Resonance", "Echo",
)

# Patch 0 is the sound this instrument's defaults describe, so a fresh
# instance and patch 0 are the same thing - create() applies it. A macro
# a caller does not set resolves here rather than to the middle of its
# range.
PATCHES = {
    0: ('Init', (58, 22, 71)),
}

import audiodelays
import synthio

from audioinstruments._support import (
    EVENT_NOTE_ON, EVENT_NOTE_OFF, EVENT_PARAMETER, FALL, key_of, logmap,
    make_table,
)
from audioinstruments._support import Instrument
from audioinstruments import _support

PLUCK = make_table([(n, 1.0 / n) for n in range(1, 12, 2)] +
                   [(n, 0.5 / n) for n in range(2, 17, 2)])


def create(sample_rate, transport=None):
    SR = sample_rate
    synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
    echo = audiodelays.Echo(max_delay_ms=700, delay_ms=346, decay=0.4,
                            mix=0.28, sample_rate=SR, channel_count=2,
                            bits_per_sample=16, samples_signed=True,
                            buffer_size=2048)
    cutoff = synthio.Math(synthio.MathOperation.SUM, 1200.0, 0.0, 0.0)
    resonance = synthio.Math(synthio.MathOperation.SUM, 1.8, 0.0, 0.0)
    env = synthio.Envelope(attack_time=0.004, decay_time=0.14,
                           release_time=0.18, attack_level=1.0,
                           sustain_level=0.2)

    echo.play(synth)

    voices = {}
    MAX_VOICES = 5
    serial = 0
    PAN = (-0.35, 0.2, 0.35, -0.2)




    def release_voice(k):
        voice = voices.pop(k, None)
        if voice is not None:
            synth.release(voice[0])


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
            amp = 0.22 + 0.4 * value0
            snap = synthio.LFO(waveform=FALL, once=True, rate=1.0 / 0.11,
                               scale=600.0 + 900.0 * value0, interpolate=True)
            freq = synthio.Math(synthio.MathOperation.SUM, cutoff, snap, 0.0)
            flt = synthio.Biquad(synthio.FilterMode.LOW_PASS, freq, Q=resonance)
            note = synthio.Note(hz, waveform=PLUCK, envelope=env, filter=flt,
                                amplitude=amp, panning=PAN[serial % 4])
            serial += 1
            voices[k] = (note, serial)
            synth.press(note)
        elif event_type in (EVENT_NOTE_OFF, EVENT_NOTE_ON):
            release_voice(k)
        elif event_type == EVENT_PARAMETER:
            if data0 == 0:
                cutoff.a = logmap(value0, 260.0, 7600.0)
            elif data0 == 1:
                resonance.a = 0.8 + 5.7 * value0
            elif data0 == 2:
                echo.mix = 0.5 * value0

    instrument = Instrument(synth, handle_event, PATCHES, MACRO_LABELS,
                            transport=transport, output=echo)
    instrument.program_change(0)
    return instrument


if __name__ == "__main__":
    import mpvst_adapter

    mpvst_adapter.attach(create)
