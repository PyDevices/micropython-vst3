# mpvst-macro-labels: Cutoff | Motion | Space
"""Analog dawn pad: two detuned saws panned wide through a slowly breathing
low-pass, chorus, and a large reverb. Macro 1 opens the filter, macro 2
deepens the internal filter motion, macro 3 pushes the pad into the room.
"""

MACRO_LABELS = (
    "Cutoff", "Motion", "Space",
)

# Patch 0 is the sound this instrument's defaults describe, so a fresh
# instance and patch 0 are the same thing - create() applies it. A macro
# a caller does not set resolves here rather than to the middle of its
# range.
PATCHES = {
    0: ('Init', (53, 31, 64)),
}

import audiodelays
import audiofreeverb
import synthio

from audioinstruments._support import (
    EVENT_NOTE_ON, EVENT_NOTE_OFF, EVENT_PARAMETER, key_of, logmap,
    make_table,
)
from audioinstruments._support import Instrument
from audioinstruments import _support

WARM_SAW = make_table([(n, 1.0 / (n ** 1.35)) for n in range(1, 19)], fast=False)
DETUNE = 2.0 ** (8.0 / 1200.0)


def create(sample_rate, transport=None):
    SR = sample_rate
    synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
    chorus = audiodelays.Chorus(max_delay_ms=40, delay_ms=17, voices=3, mix=0.35,
                                sample_rate=SR, channel_count=2,
                                bits_per_sample=16, samples_signed=True,
                                buffer_size=2048)
    verb = audiofreeverb.Freeverb(roomsize=0.88, damp=0.35, mix=0.3,
                                  sample_rate=SR, channel_count=2,
                                  bits_per_sample=16, samples_signed=True,
                                  buffer_size=2048)
    cut_base = synthio.Math(synthio.MathOperation.SUM, 900.0, 0.0, 0.0)
    motion_depth = synthio.Math(synthio.MathOperation.SUM, 260.0, 0.0, 0.0)
    breath = synthio.LFO(rate=0.07, scale=motion_depth, phase_offset=0.75)
    cut_sum = synthio.Math(synthio.MathOperation.SUM, cut_base, breath, 0.0)
    # The breath excursion can exceed a dark cutoff base; a negative filter
    # frequency destabilises the biquad, so clamp to the audible band.
    cutoff = synthio.Math(synthio.MathOperation.MID, cut_sum, 90.0, 9000.0)
    lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, cutoff, Q=1.05)

    env = synthio.Envelope(attack_time=1.2, decay_time=0.5, release_time=2.4,
                           attack_level=1.0, sustain_level=0.85)

    chorus.play(synth)
    verb.play(chorus)

    voices = {}
    MAX_VOICES = 5
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
            amp = 0.07 + 0.09 * value0
            a = synthio.Note(hz * DETUNE, waveform=WARM_SAW, envelope=env,
                             filter=lp, amplitude=amp, panning=-0.5)
            b = synthio.Note(hz / DETUNE, waveform=WARM_SAW, envelope=env,
                             filter=lp, amplitude=amp, panning=0.5)
            serial += 1
            voices[k] = ((a, b), serial)
            synth.press(a)
            synth.press(b)
        elif event_type in (EVENT_NOTE_OFF, EVENT_NOTE_ON):
            release_voice(k)
        elif event_type == EVENT_PARAMETER:
            if data0 == 0:
                cut_base.a = logmap(value0, 260.0, 5200.0)
            elif data0 == 1:
                motion_depth.a = 40.0 + 900.0 * value0
            elif data0 == 2:
                verb.mix = 0.1 + 0.4 * value0

    instrument = Instrument(synth, handle_event, PATCHES, MACRO_LABELS,
                            transport=transport, output=verb)
    instrument.program_change(0)
    return instrument


if __name__ == "__main__":
    import mpvst_adapter

    mpvst_adapter.attach(create)
