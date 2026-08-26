# mpvst-macro-labels: Shimmer | Space
"""Glass halo pad: triangle-ish tone ring-modulated at an inharmonic ratio,
high-passed so it floats above the mix, with slow tremolo and a very large
reverb. Macro 1 raises the ring-mod shimmer, macro 2 the room.
"""

MACRO_LABELS = (
    "Shimmer", "Space",
)

# Patch 0 is the sound this instrument's defaults describe, so a fresh
# instance and patch 0 are the same thing - create() applies it. A macro
# a caller does not set resolves here rather than to the middle of its
# range.
PATCHES = {
    0: ('Init', (40, 76)),
}

import audiofreeverb
import synthio

from audioinstruments._support import (
    EVENT_NOTE_ON, EVENT_NOTE_OFF, EVENT_PARAMETER, key_of, make_table,
)
from audioinstruments._support import Instrument
from audioinstruments import _support

SOFT = make_table(((1, 1.0), (3, 0.10), (5, 0.035), (7, 0.015)), fast=False)
SINE = make_table(((1, 1.0),), fast=False)
RING_RATIO = 3.007


def create(sample_rate, transport=None):
    SR = sample_rate
    synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
    verb = audiofreeverb.Freeverb(roomsize=0.92, damp=0.3, mix=0.42,
                                  sample_rate=SR, channel_count=2,
                                  bits_per_sample=16, samples_signed=True,
                                  buffer_size=2048)
    hp = synthio.Biquad(synthio.FilterMode.HIGH_PASS, 320.0, Q=0.8)
    env = synthio.Envelope(attack_time=1.8, decay_time=0.6, release_time=3.5,
                           attack_level=1.0, sustain_level=0.8)

    verb.play(synth)

    shimmer = 0.35
    voices = {}
    MAX_VOICES = 5
    serial = 0




    def release_voice(k):
        _support.release_voice(voices, synth, k)


    def steal_oldest():
        _support.steal_oldest(voices, release_voice)


    def handle_event(event_type, channel, note_id, data0, value0, value1,
                     sample_position):
        nonlocal serial, shimmer
        k = key_of(channel, note_id, data0)
        if event_type == EVENT_NOTE_ON and value0 > 0.0:
            release_voice(k)
            if len(voices) >= MAX_VOICES:
                steal_oldest()
            hz = synthio.midi_to_hz(data0 + value1)
            amp = 0.10 + 0.13 * value0
            trem = synthio.LFO(rate=0.9, scale=0.12 * amp, offset=amp,
                               phase_offset=0.25 * (serial % 4))
            pure = synthio.Note(hz, waveform=SOFT, envelope=env, filter=hp,
                                amplitude=trem, panning=-0.3)
            glass = synthio.Note(hz, waveform=SOFT, envelope=env, filter=hp,
                                 amplitude=amp * shimmer, panning=0.35,
                                 ring_frequency=hz * RING_RATIO,
                                 ring_waveform=SINE)
            serial += 1
            voices[k] = ((pure, glass), serial)
            synth.press(pure)
            synth.press(glass)
        elif event_type in (EVENT_NOTE_OFF, EVENT_NOTE_ON):
            release_voice(k)
        elif event_type == EVENT_PARAMETER:
            if data0 == 0:
                shimmer = 0.1 + 0.8 * value0
                for voice in voices.values():
                    voice[0][1].amplitude = 0.24 * shimmer
            elif data0 == 1:
                verb.mix = 0.15 + 0.45 * value0

    instrument = Instrument(synth, handle_event, PATCHES, MACRO_LABELS,
                            transport=transport, output=verb)
    instrument.program_change(0)
    return instrument


if __name__ == "__main__":
    import mpvst_adapter

    mpvst_adapter.attach(create)
