# mpvst-macro-labels: Color | Space
"""FM-flavored bells: a pure carrier blended with a ring-modulated
partner at an inharmonic 3.51 ratio - velocity leans the blend toward
the bright layer, like striking harder on a DX tine. Chorus and a long
hall. Macro 1 tunes the ratio, macro 2 the hall.
"""

MACRO_LABELS = (
    "Color", "Space",
)

# Patch 0 is the sound this instrument's defaults describe, so a fresh
# instance and patch 0 are the same thing - create() applies it. A macro
# a caller does not set resolves here rather than to the middle of its
# range.
PATCHES = {
    0: ('Init', (55, 73)),
}

import audiodelays
import audiofreeverb
import synthio

from audioinstruments._support import (
    EVENT_NOTE_ON, EVENT_NOTE_OFF, EVENT_PARAMETER, key_of, make_table,
)
from audioinstruments._support import Instrument
from audioinstruments._support import static_transport
from audioinstruments import _support

SINE = make_table(((1, 1.0),), fast=False)


def create(sample_rate, transport=None):
    SR = sample_rate
    if transport is None:
        transport = static_transport
    def beat_clock():
        info = transport()
        bpm = info[2] if info[2] and info[2] > 1.0 else 120.0
        return bpm, info[1] * bpm / 60.0
    ratio = 3.51
    synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
    chorus = audiodelays.Chorus(max_delay_ms=30, delay_ms=14, voices=3,
                                mix=0.3, sample_rate=SR, channel_count=2,
                                bits_per_sample=16, samples_signed=True,
                                buffer_size=2048)
    verb = audiofreeverb.Freeverb(roomsize=0.9, damp=0.3, mix=0.38,
                                  sample_rate=SR, channel_count=2,
                                  bits_per_sample=16, samples_signed=True,
                                  buffer_size=2048)
    strike_env = synthio.Envelope(attack_time=0.002, decay_time=1.6,
                                  release_time=2.5, attack_level=1.0,
                                  sustain_level=0.15)

    chorus.play(synth)
    verb.play(chorus)

    voices = {}
    serial = 0




    def release_voice(k):
        _support.release_voice(voices, synth, k)


    def steal_oldest():
        _support.steal_oldest(voices, release_voice)

    MAX_VOICES = 5


    def handle_event(event_type, channel, note_id, data0, value0, value1,
                     sample_position):
        nonlocal serial, ratio
        k = key_of(channel, note_id, data0)
        if event_type == EVENT_NOTE_ON and value0 > 0.0:
            release_voice(k)
            if len(voices) >= MAX_VOICES:
                steal_oldest()
            hz = synthio.midi_to_hz(data0 + value1)
            amp = 0.16 + 0.26 * value0
            pan = 0.25 - 0.25 * (serial % 3)
            pure = synthio.Note(hz, waveform=SINE, envelope=strike_env,
                                amplitude=amp * (1.0 - 0.45 * value0),
                                panning=pan)
            bright = synthio.Note(hz, waveform=SINE, envelope=strike_env,
                                  amplitude=amp * (0.35 + 0.6 * value0),
                                  panning=-pan, ring_frequency=hz * ratio,
                                  ring_waveform=SINE, ring_bend=0.0001)
            serial += 1
            voices[k] = ((pure, bright), serial)
            synth.press(pure)
            synth.press(bright)
        elif event_type in (EVENT_NOTE_OFF, EVENT_NOTE_ON):
            release_voice(k)
        elif event_type == EVENT_PARAMETER:
            if data0 == 0:
                ratio = 2.9 + 1.4 * value0
            elif data0 == 1:
                verb.mix = 0.15 + 0.4 * value0

    instrument = Instrument(synth, handle_event, PATCHES, MACRO_LABELS,
                            transport=transport, output=verb)
    instrument.program_change(0)
    return instrument


if __name__ == "__main__":
    import mpvst_adapter

    mpvst_adapter.attach(create)
