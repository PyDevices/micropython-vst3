# mpvst-macro-labels: Tone | Room
"""Clap: three noise bursts whose attacks are staggered by a few
milliseconds - the smear of many hands - through a band-pass and a
real room. Macro 1 moves the band, macro 2 the room.
"""

MACRO_LABELS = (
    "Tone", "Room",
)

# Patch 0 is the sound this instrument's defaults describe, so a fresh
# instance and patch 0 are the same thing - create() applies it. A macro
# a caller does not set resolves here rather than to the middle of its
# range.
PATCHES = {
    0: ('Init', (48, 79)),
}

import audiofreeverb
import synthio

from audioinstruments._support import (
    EVENT_NOTE_ON, EVENT_NOTE_OFF, EVENT_PARAMETER, key_of, logmap,
    noise_table,
)
from audioinstruments._support import Instrument
from audioinstruments import _support

NOISE = noise_table(seed=24681357)


def create(sample_rate, transport=None):
    SR = sample_rate
    NOISE_HZ = SR / 8192.0
    synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
    verb = audiofreeverb.Freeverb(roomsize=0.85, damp=0.45, mix=0.28,
                                  sample_rate=SR, channel_count=2,
                                  bits_per_sample=16, samples_signed=True,
                                  buffer_size=2048)
    band = synthio.Math(synthio.MathOperation.SUM, 1150.0, 0.0, 0.0)
    bp = synthio.Biquad(synthio.FilterMode.BAND_PASS, band, Q=1.3)

    ATTACKS = (0.001, 0.013, 0.027)
    PANS = (-0.12, 0.0, 0.12)

    verb.play(synth)

    voices = {}
    serial = 0




    def release_voice(k):
        _support.release_voice(voices, synth, k)


    def steal_oldest():
        _support.steal_oldest(voices, release_voice)

    MAX_VOICES = 3


    def handle_event(event_type, channel, note_id, data0, value0, value1,
                     sample_position):
        nonlocal serial
        k = key_of(channel, note_id, data0)
        if event_type == EVENT_NOTE_ON and value0 > 0.0:
            release_voice(k)
            if len(voices) >= MAX_VOICES:
                steal_oldest()
            amp = 0.24 + 0.4 * value0
            notes = []
            for i in range(3):
                env = synthio.Envelope(attack_time=ATTACKS[i], decay_time=0.16,
                                       release_time=0.08, attack_level=1.0,
                                       sustain_level=0.0)
                notes.append(synthio.Note(NOISE_HZ, waveform=NOISE,
                                          envelope=env, filter=bp,
                                          amplitude=amp * (1.0 - 0.18 * i),
                                          panning=PANS[i]))
            serial += 1
            voices[k] = (tuple(notes), serial)
            for note in notes:
                synth.press(note)
        elif event_type in (EVENT_NOTE_OFF, EVENT_NOTE_ON):
            release_voice(k)
        elif event_type == EVENT_PARAMETER:
            if data0 == 0:
                band.a = logmap(value0, 800.0, 2100.0)
            elif data0 == 1:
                verb.mix = 0.45 * value0

    instrument = Instrument(synth, handle_event, PATCHES, MACRO_LABELS,
                            transport=transport, output=verb)
    instrument.program_change(0)
    return instrument


if __name__ == "__main__":
    import mpvst_adapter

    mpvst_adapter.attach(create)
