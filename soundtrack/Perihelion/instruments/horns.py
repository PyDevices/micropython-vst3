# mpvst-macro-labels: Bloom | Space
"""Horn ensemble: softened saw pair whose low-pass blooms open over the first
third of a second of every note - the brass "wah" that sells a sustained
horn pad. Macro 1 sets how far the bloom opens, macro 2 the room.
"""

MACRO_LABELS = (
    "Bloom", "Space",
)

# Patch 0 is the sound this instrument's defaults describe, so a fresh
# instance and patch 0 are the same thing - create() applies it. A macro
# a caller does not set resolves here rather than to the middle of its
# range.
PATCHES = {
    0: ('Init', (87, 54)),
}

import array
import audiofreeverb
import synthio

from audioinstruments._support import (
    EVENT_NOTE_ON, EVENT_NOTE_OFF, EVENT_PARAMETER, key_of, logmap,
    make_table,
)
from audioinstruments._support import Instrument
from audioinstruments import _support

HORN = make_table([(n, 1.0 / (n ** 1.2)) for n in range(1, 17)], fast=False)
DETUNE = 2.0 ** (4.0 / 1200.0)
RISE = array.array("h", (0, 32767))


def create(sample_rate, transport=None):
    SR = sample_rate
    synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
    verb = audiofreeverb.Freeverb(roomsize=0.85, damp=0.45, mix=0.25,
                                  sample_rate=SR, channel_count=2,
                                  bits_per_sample=16, samples_signed=True,
                                  buffer_size=2048)
    bloom = 2000.0
    env = synthio.Envelope(attack_time=0.12, decay_time=0.2, release_time=0.9,
                           attack_level=1.0, sustain_level=0.9)

    verb.play(synth)

    voices = {}
    MAX_VOICES = 5
    serial = 0




    def release_voice(k):
        _support.release_voice(voices, synth, k)


    def steal_oldest():
        _support.steal_oldest(voices, release_voice)


    def handle_event(event_type, channel, note_id, data0, value0, value1,
                     sample_position):
        nonlocal serial, bloom
        k = key_of(channel, note_id, data0)
        if event_type == EVENT_NOTE_ON and value0 > 0.0:
            release_voice(k)
            if len(voices) >= MAX_VOICES:
                steal_oldest()
            hz = synthio.midi_to_hz(data0 + value1)
            amp = 0.11 + 0.16 * value0
            opener = synthio.LFO(waveform=RISE, once=True, rate=1.0 / 0.35,
                                 scale=bloom * (0.5 + 0.5 * value0),
                                 interpolate=True)
            freq = synthio.Math(synthio.MathOperation.SUM, 260.0, opener, 0.0)
            flt = synthio.Biquad(synthio.FilterMode.LOW_PASS, freq, Q=1.3)
            a = synthio.Note(hz * DETUNE, waveform=HORN, envelope=env,
                             filter=flt, amplitude=amp, panning=-0.25)
            b = synthio.Note(hz / DETUNE, waveform=HORN, envelope=env,
                             filter=flt, amplitude=amp, panning=0.2)
            serial += 1
            voices[k] = ((a, b), serial)
            synth.press(a)
            synth.press(b)
        elif event_type in (EVENT_NOTE_OFF, EVENT_NOTE_ON):
            release_voice(k)
        elif event_type == EVENT_PARAMETER:
            if data0 == 0:
                bloom = logmap(value0, 480.0, 3900.0)
            elif data0 == 1:
                verb.mix = 0.1 + 0.35 * value0

    instrument = Instrument(synth, handle_event, PATCHES, MACRO_LABELS,
                            transport=transport, output=verb)
    instrument.program_change(0)
    return instrument


if __name__ == "__main__":
    import mpvst_adapter

    mpvst_adapter.attach(create)
