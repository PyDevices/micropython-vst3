# mpvst-macro-labels: Color | Echo | Space
"""Aurora bells: a struck sine ring-modulated at a bell partial ratio, with
a quieter upper partial, echo, and a long hall. Carries the signal motif.
Macro 1 tunes the ring ratio (mellow to metallic), macro 2 the echo,
macro 3 the room.
"""

MACRO_LABELS = (
    "Color", "Echo", "Space",
)

# Patch 0 is the sound this instrument's defaults describe, so a fresh
# instance and patch 0 are the same thing - create() applies it. A macro
# a caller does not set resolves here rather than to the middle of its
# range.
PATCHES = {
    0: ('Init', (45, 64, 64)),
}

import audiodelays
import audiofreeverb
import synthio

from audioinstruments._support import (
    EVENT_NOTE_ON, EVENT_NOTE_OFF, EVENT_PARAMETER, key_of, make_table,
)
from audioinstruments._support import Instrument
from audioinstruments import _support

SINE = make_table(((1, 1.0),), fast=False)


def create(sample_rate, transport=None):
    SR = sample_rate
    synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
    echo = audiodelays.Echo(max_delay_ms=900, delay_ms=428, decay=0.45,
                            mix=0.25, sample_rate=SR, channel_count=2,
                            bits_per_sample=16, samples_signed=True,
                            buffer_size=2048)
    verb = audiofreeverb.Freeverb(roomsize=0.9, damp=0.3, mix=0.35,
                                  sample_rate=SR, channel_count=2,
                                  bits_per_sample=16, samples_signed=True,
                                  buffer_size=2048)
    ratio = 3.36
    strike_env = synthio.Envelope(attack_time=0.003, decay_time=1.4,
                                  release_time=3.0, attack_level=1.0,
                                  sustain_level=0.2)
    partial_env = synthio.Envelope(attack_time=0.002, decay_time=0.7,
                                   release_time=1.6, attack_level=1.0,
                                   sustain_level=0.1)

    echo.play(synth)
    verb.play(echo)

    voices = {}
    MAX_VOICES = 5
    serial = 0




    def release_voice(k):
        _support.release_voice(voices, synth, k)


    def steal_oldest():
        _support.steal_oldest(voices, release_voice)


    def handle_event(event_type, channel, note_id, data0, value0, value1,
                     sample_position):
        nonlocal serial, ratio
        k = key_of(channel, note_id, data0)
        if event_type == EVENT_NOTE_ON and value0 > 0.0:
            release_voice(k)
            if len(voices) >= MAX_VOICES:
                steal_oldest()
            hz = synthio.midi_to_hz(data0 + value1)
            amp = 0.15 + 0.25 * value0
            pan = 0.3 - 0.2 * (serial % 3)
            strike = synthio.Note(hz, waveform=SINE, envelope=strike_env,
                                  amplitude=amp, panning=pan,
                                  ring_frequency=hz * ratio, ring_waveform=SINE,
                                  ring_bend=0.0001)
            upper = synthio.Note(hz * 2.67, waveform=SINE, envelope=partial_env,
                                 amplitude=amp * 0.3, panning=-pan)
            serial += 1
            voices[k] = ((strike, upper), serial)
            synth.press(strike)
            synth.press(upper)
        elif event_type in (EVENT_NOTE_OFF, EVENT_NOTE_ON):
            release_voice(k)
        elif event_type == EVENT_PARAMETER:
            if data0 == 0:
                ratio = 2.9 + 1.3 * value0
            elif data0 == 1:
                echo.mix = 0.5 * value0
            elif data0 == 2:
                verb.mix = 0.15 + 0.4 * value0

    instrument = Instrument(synth, handle_event, PATCHES, MACRO_LABELS,
                            transport=transport, output=verb)
    instrument.program_change(0)
    return instrument


if __name__ == "__main__":
    import mpvst_adapter

    mpvst_adapter.attach(create)
