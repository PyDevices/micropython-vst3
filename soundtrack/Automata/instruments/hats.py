# mpvst-macro-labels: Tone
"""Hi-hats: high-passed noise. Pitch 42 is the closed hat, 46 the open hat,
and a closed hit chokes any ringing open one, like a real pair of
cymbals on a rod. Macro 1 moves the high-pass corner.
"""

MACRO_LABELS = (
    "Tone",
)

# Patch 0 is the sound this instrument's defaults describe, so a fresh
# instance and patch 0 are the same thing - create() applies it. A macro
# a caller does not set resolves here rather than to the middle of its
# range.
PATCHES = {
    0: ('Init', (57,)),
}

import synthio

from audioinstruments._support import (
    EVENT_NOTE_ON, EVENT_NOTE_OFF, EVENT_PARAMETER, key_of, logmap,
    noise_table,
)
from audioinstruments._support import Instrument
from audioinstruments import _support

NOISE = noise_table(seed=13571357)


def create(sample_rate, transport=None):
    SR = sample_rate
    NOISE_HZ = SR / 8192.0
    synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
    corner = synthio.Math(synthio.MathOperation.SUM, 8200.0, 0.0, 0.0)
    hp = synthio.Biquad(synthio.FilterMode.HIGH_PASS, corner, Q=0.8)

    closed_env = synthio.Envelope(attack_time=0.001, decay_time=0.035,
                                  release_time=0.02, attack_level=1.0,
                                  sustain_level=0.0)
    open_env = synthio.Envelope(attack_time=0.001, decay_time=0.32,
                                release_time=0.05, attack_level=1.0,
                                sustain_level=0.0)

    voices = {}
    serial = 0




    def release_voice(k):
        _support.release_voice(voices, synth, k)


    def steal_oldest():
        _support.steal_oldest(voices, release_voice)

    MAX_VOICES = 4
    open_keys = []


    def handle_event(event_type, channel, note_id, data0, value0, value1,
                     sample_position):
        nonlocal serial
        k = key_of(channel, note_id, data0)
        if event_type == EVENT_NOTE_ON and value0 > 0.0:
            release_voice(k)
            if len(voices) >= MAX_VOICES:
                steal_oldest()
            is_open = data0 >= 45
            if not is_open:
                while open_keys:
                    release_voice(open_keys.pop())
            amp = (0.2 + 0.5 * value0) * (0.9 if is_open else 1.0)
            env = open_env if is_open else closed_env
            note = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env,
                                filter=hp, amplitude=amp, panning=0.12)
            serial += 1
            voices[k] = ((note,), serial)
            if is_open:
                open_keys.append(k)
            synth.press(note)
        elif event_type in (EVENT_NOTE_OFF, EVENT_NOTE_ON):
            release_voice(k)
            if k in open_keys:
                open_keys.remove(k)
        elif event_type == EVENT_PARAMETER:
            if data0 == 0:
                corner.a = logmap(value0, 6200.0, 11500.0)

    instrument = Instrument(synth, handle_event, PATCHES, MACRO_LABELS,
                            transport=transport)
    instrument.program_change(0)
    return instrument


if __name__ == "__main__":
    import mpvst_adapter

    mpvst_adapter.attach(create)
