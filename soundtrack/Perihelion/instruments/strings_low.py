# mpvst-macro-labels: Brightness | Space
"""Low string ensemble: three saws per voice (detuned pair panned wide plus a
center octave-down layer), gentle per-voice vibrato, ensemble low-pass,
concert-hall reverb. Macro 1 is section brightness, macro 2 the hall.
"""

MACRO_LABELS = (
    "Brightness", "Space",
)

# Patch 0 is the sound this instrument's defaults describe, so a fresh
# instance and patch 0 are the same thing - create() applies it. A macro
# a caller does not set resolves here rather than to the middle of its
# range.
PATCHES = {
    0: ('Init', (63, 53)),
}

import audiofreeverb
import synthio

from audioinstruments._support import (
    EVENT_NOTE_ON, EVENT_NOTE_OFF, EVENT_PARAMETER, key_of, logmap,
    make_table,
)
from audioinstruments._support import Instrument
from audioinstruments import _support

STRING = make_table([(n, 1.0 / n) for n in range(1, 21)], fast=False)
DETUNE = 2.0 ** (5.0 / 1200.0)


def create(sample_rate, transport=None):
    SR = sample_rate
    synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
    verb = audiofreeverb.Freeverb(roomsize=0.9, damp=0.5, mix=0.28,
                                  sample_rate=SR, channel_count=2,
                                  bits_per_sample=16, samples_signed=True,
                                  buffer_size=2048)
    cutoff = synthio.Math(synthio.MathOperation.SUM, 1100.0, 0.0, 0.0)
    lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, cutoff, Q=0.85)
    env = synthio.Envelope(attack_time=0.4, decay_time=0.3, release_time=1.4,
                           attack_level=1.0, sustain_level=0.85)

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
            amp = 0.09 + 0.13 * value0
            vib = synthio.LFO(rate=4.4 + 0.15 * (serial % 3), scale=0.0055,
                              phase_offset=0.33 * (serial % 3))
            a = synthio.Note(hz * DETUNE, waveform=STRING, envelope=env,
                             filter=lp, amplitude=amp, panning=-0.4, bend=vib)
            b = synthio.Note(hz / DETUNE, waveform=STRING, envelope=env,
                             filter=lp, amplitude=amp, panning=0.4, bend=vib)
            low = synthio.Note(hz * 0.5, waveform=STRING, envelope=env,
                               filter=lp, amplitude=amp * 0.55, panning=0.0)
            serial += 1
            voices[k] = ((a, b, low), serial)
            synth.press(a)
            synth.press(b)
            synth.press(low)
        elif event_type in (EVENT_NOTE_OFF, EVENT_NOTE_ON):
            release_voice(k)
        elif event_type == EVENT_PARAMETER:
            if data0 == 0:
                cutoff.a = logmap(value0, 380.0, 3200.0)
            elif data0 == 1:
                verb.mix = 0.12 + 0.38 * value0

    instrument = Instrument(synth, handle_event, PATCHES, MACRO_LABELS,
                            transport=transport, output=verb)
    instrument.program_change(0)
    return instrument


if __name__ == "__main__":
    import mpvst_adapter

    mpvst_adapter.attach(create)
