# mpvst-macro-labels: Depth | Space
"""Aphelion sub drone: sine with a touch of 2nd/3rd harmonic, very slow
attack, low-pass depth macro, small reverb. The floor of the score.
"""

MACRO_LABELS = (
    "Depth", "Space",
)

# Patch 0 is the sound this instrument's defaults describe, so a fresh
# instance and patch 0 are the same thing - create() applies it. A macro
# a caller does not set resolves here rather than to the middle of its
# range.
PATCHES = {
    0: ('Init', (55, 30)),
}

import audiofreeverb
import synthio

from audioinstruments._support import (
    EVENT_NOTE_ON, EVENT_NOTE_OFF, EVENT_PARAMETER, key_of, logmap,
    make_table,
)
from audioinstruments._support import Instrument

WARM = make_table(((1, 1.0), (2, 0.18), (3, 0.07)), fast=False)


def create(sample_rate, transport=None):
    SR = sample_rate
    synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
    verb = audiofreeverb.Freeverb(roomsize=0.72, damp=0.5, mix=0.12,
                                  sample_rate=SR, channel_count=2,
                                  bits_per_sample=16, samples_signed=True,
                                  buffer_size=2048)
    cutoff = synthio.Math(synthio.MathOperation.SUM, 140.0, 0.0, 0.0)
    lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, cutoff, Q=0.9)
    env = synthio.Envelope(attack_time=2.5, decay_time=0.5, release_time=4.5,
                           attack_level=1.0, sustain_level=1.0)

    verb.play(synth)

    voices = {}
    MAX_VOICES = 4




    def steal_oldest():
        oldest = None
        for k in voices:
            if oldest is None or voices[k][1] < voices[oldest][1]:
                oldest = k
        if oldest is not None:
            synth.release(voices.pop(oldest)[0])


    serial = 0


    def handle_event(event_type, channel, note_id, data0, value0, value1,
                     sample_position):
        nonlocal serial
        k = key_of(channel, note_id, data0)
        if event_type == EVENT_NOTE_ON and value0 > 0.0:
            old = voices.pop(k, None)
            if old is not None:
                synth.release(old[0])
            if len(voices) >= MAX_VOICES:
                steal_oldest()
            amp = 0.26 + 0.34 * value0
            note = synthio.Note(synthio.midi_to_hz(data0 + value1),
                                waveform=WARM, envelope=env, filter=lp,
                                amplitude=amp)
            serial += 1
            voices[k] = (note, serial)
            synth.press(note)
        elif event_type in (EVENT_NOTE_OFF, EVENT_NOTE_ON):
            old = voices.pop(k, None)
            if old is not None:
                synth.release(old[0])
        elif event_type == EVENT_PARAMETER:
            if data0 == 0:
                cutoff.a = logmap(value0, 60.0, 420.0)
            elif data0 == 1:
                verb.mix = 0.05 + 0.3 * value0

    instrument = Instrument(synth, handle_event, PATCHES, MACRO_LABELS,
                            transport=transport, output=verb)
    instrument.program_change(0)
    return instrument


if __name__ == "__main__":
    import mpvst_adapter

    mpvst_adapter.attach(create)
