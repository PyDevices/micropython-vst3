# mpvst-macro-labels: Air | Space
"""Air texture: band-passed noise breathing very slowly under everything,
felt more than heard. Macro 1 places the band, macro 2 the room.
"""

MACRO_LABELS = (
    "Air", "Space",
)

# Patch 0 is the sound this instrument's defaults describe, so a fresh
# instance and patch 0 are the same thing - create() applies it. A macro
# a caller does not set resolves here rather than to the middle of its
# range.
PATCHES = {
    0: ('Init', (68, 95)),
}

import audiofreeverb
import synthio

from audioinstruments._support import (
    EVENT_NOTE_ON, EVENT_NOTE_OFF, EVENT_PARAMETER, key_of, logmap,
    noise_table,
)
from audioinstruments._support import Instrument

NOISE = noise_table(seed=31415926)


def create(sample_rate, transport=None):
    SR = sample_rate
    NOISE_HZ = SR / 8192.0
    synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
    verb = audiofreeverb.Freeverb(roomsize=0.92, damp=0.3, mix=0.5,
                                  sample_rate=SR, channel_count=2,
                                  bits_per_sample=16, samples_signed=True,
                                  buffer_size=2048)
    air = synthio.Math(synthio.MathOperation.SUM, 2300.0, 0.0, 0.0)
    bp = synthio.Biquad(synthio.FilterMode.BAND_PASS, air, Q=0.6)
    env = synthio.Envelope(attack_time=3.0, decay_time=0.5, release_time=4.0,
                           attack_level=1.0, sustain_level=1.0)

    verb.play(synth)

    voices = {}




    def handle_event(event_type, channel, note_id, data0, value0, value1,
                     sample_position):
        k = key_of(channel, note_id, data0)
        if event_type == EVENT_NOTE_ON and value0 > 0.0:
            old = voices.pop(k, None)
            if old is not None:
                synth.release(old)
            breathe = synthio.LFO(rate=0.11, scale=0.35 * (0.1 + 0.2 * value0),
                                  offset=0.1 + 0.2 * value0)
            note = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env,
                                filter=bp, amplitude=breathe)
            voices[k] = note
            synth.press(note)
        elif event_type in (EVENT_NOTE_OFF, EVENT_NOTE_ON):
            old = voices.pop(k, None)
            if old is not None:
                synth.release(old)
        elif event_type == EVENT_PARAMETER:
            if data0 == 0:
                air.a = logmap(value0, 900.0, 5200.0)
            elif data0 == 1:
                verb.mix = 0.2 + 0.4 * value0

    instrument = Instrument(synth, handle_event, PATCHES, MACRO_LABELS,
                            transport=transport, output=verb)
    instrument.program_change(0)
    return instrument


if __name__ == "__main__":
    import mpvst_adapter

    mpvst_adapter.attach(create)
