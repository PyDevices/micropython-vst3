# mpvst-macro-labels: Cutoff | Width
"""Reese bass: two saws detuned a quarter of a semitone fighting each
other through a dark low-pass and a wide chorus. The slow beating IS
the sound. Macro 1 opens the filter, macro 2 the chorus width.
"""

MACRO_LABELS = (
    "Cutoff", "Width",
)

# Patch 0 is the sound this instrument's defaults describe, so a fresh
# instance and patch 0 are the same thing - create() applies it. A macro
# a caller does not set resolves here rather than to the middle of its
# range.
PATCHES = {
    0: ('Init', (62, 85)),
}

import audiodelays
import synthio

from audioinstruments._support import (
    EVENT_NOTE_ON, EVENT_NOTE_OFF, EVENT_PARAMETER, key_of, logmap,
    make_table,
)
from audioinstruments._support import Instrument
from audioinstruments._support import static_transport
from audioinstruments import _support

SAW = make_table([(n, 1.0 / n) for n in range(1, 21)], fast=False)
DETUNE = 2.0 ** (12.0 / 1200.0)


def create(sample_rate, transport=None):
    SR = sample_rate
    if transport is None:
        transport = static_transport
    def beat_clock():
        info = transport()
        bpm = info[2] if info[2] and info[2] > 1.0 else 120.0
        return bpm, info[1] * bpm / 60.0
    synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
    chorus = audiodelays.Chorus(max_delay_ms=30, delay_ms=12, voices=3,
                                mix=0.4, sample_rate=SR, channel_count=2,
                                bits_per_sample=16, samples_signed=True,
                                buffer_size=2048)
    cutoff = synthio.Math(synthio.MathOperation.SUM, 650.0, 0.0, 0.0)
    lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, cutoff, Q=1.2)
    env = synthio.Envelope(attack_time=0.06, decay_time=0.2,
                           release_time=0.25, attack_level=1.0,
                           sustain_level=0.9)

    chorus.play(synth)

    voices = {}
    serial = 0




    def release_voice(k):
        _support.release_voice(voices, synth, k)


    def steal_oldest():
        _support.steal_oldest(voices, release_voice)

    MAX_VOICES = 2


    def handle_event(event_type, channel, note_id, data0, value0, value1,
                     sample_position):
        nonlocal serial
        k = key_of(channel, note_id, data0)
        if event_type == EVENT_NOTE_ON and value0 > 0.0:
            release_voice(k)
            if len(voices) >= MAX_VOICES:
                steal_oldest()
            hz = synthio.midi_to_hz(data0 + value1)
            amp = 0.26 + 0.34 * value0
            a = synthio.Note(hz * DETUNE, waveform=SAW, envelope=env,
                             filter=lp, amplitude=amp, panning=-0.35)
            b = synthio.Note(hz / DETUNE, waveform=SAW, envelope=env,
                             filter=lp, amplitude=amp, panning=0.35)
            serial += 1
            voices[k] = ((a, b), serial)
            synth.press(a)
            synth.press(b)
        elif event_type in (EVENT_NOTE_OFF, EVENT_NOTE_ON):
            release_voice(k)
        elif event_type == EVENT_PARAMETER:
            if data0 == 0:
                cutoff.a = logmap(value0, 260.0, 1700.0)
            elif data0 == 1:
                chorus.mix = 0.6 * value0

    instrument = Instrument(synth, handle_event, PATCHES, MACRO_LABELS,
                            transport=transport, output=chorus)
    instrument.program_change(0)
    return instrument


if __name__ == "__main__":
    import mpvst_adapter

    mpvst_adapter.attach(create)
