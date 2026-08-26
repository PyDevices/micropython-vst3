# mpvst-macro-labels: Center | Space
"""Air swell: band-passed noise whose center climbs while the note swells -
the reverse-cymbal rise into a downbeat. Macro 1 places the band, macro 2
the room.
"""

MACRO_LABELS = (
    "Center", "Space",
)

# Patch 0 is the sound this instrument's defaults describe, so a fresh
# instance and patch 0 are the same thing - create() applies it. A macro
# a caller does not set resolves here rather than to the middle of its
# range.
PATCHES = {
    0: ('Init', (58, 95)),
}

import array
import audiofreeverb
import synthio

from audioinstruments._support import (
    EVENT_NOTE_ON, EVENT_NOTE_OFF, EVENT_PARAMETER, key_of, logmap,
    noise_table,
)
from audioinstruments._support import Instrument
from audioinstruments import _support

NOISE = noise_table(seed=555444333)
RISE = array.array("h", (0, 32767))


def create(sample_rate, transport=None):
    SR = sample_rate
    NOISE_HZ = SR / 8192.0
    synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
    verb = audiofreeverb.Freeverb(roomsize=0.93, damp=0.25, mix=0.5,
                                  sample_rate=SR, channel_count=2,
                                  bits_per_sample=16, samples_signed=True,
                                  buffer_size=2048)
    center = synthio.Math(synthio.MathOperation.SUM, 2400.0, 0.0, 0.0)
    env = synthio.Envelope(attack_time=2.2, decay_time=0.5, release_time=1.8,
                           attack_level=1.0, sustain_level=1.0)

    verb.play(synth)

    voices = {}
    MAX_VOICES = 3
    serial = 0




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
            amp = 0.15 + 0.3 * value0
            climb = synthio.LFO(waveform=RISE, once=True, rate=1.0 / 3.0,
                                scale=3400.0, interpolate=True)
            freq = synthio.Math(synthio.MathOperation.SUM, center, climb, 0.0)
            bp = synthio.Biquad(synthio.FilterMode.BAND_PASS, freq, Q=2.4)
            note = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env,
                                filter=bp, amplitude=amp,
                                panning=0.25 - 0.5 * (serial % 2))
            serial += 1
            voices[k] = (note, serial)
            synth.press(note)
        elif event_type in (EVENT_NOTE_OFF, EVENT_NOTE_ON):
            release_voice(k)
        elif event_type == EVENT_PARAMETER:
            if data0 == 0:
                center.a = logmap(value0, 900.0, 7800.0)
            elif data0 == 1:
                verb.mix = 0.2 + 0.4 * value0

    instrument = Instrument(synth, handle_event, PATCHES, MACRO_LABELS,
                            transport=transport, output=verb)
    instrument.program_change(0)
    return instrument


if __name__ == "__main__":
    import mpvst_adapter

    mpvst_adapter.attach(create)
