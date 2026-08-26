# mpvst-macro-labels: Drawbars | Space
"""Organ: an additive drawbar waveform (partials 1,2,3,4,6,8) that speaks
instantly and holds forever, slightly chorused. The harmonic floor of
the climax. Macro 1 darkens or opens the upper drawbars via the
low-pass, macro 2 the room.
"""

MACRO_LABELS = (
    "Drawbars", "Space",
)

# Patch 0 is the sound this instrument's defaults describe, so a fresh
# instance and patch 0 are the same thing - create() applies it. A macro
# a caller does not set resolves here rather than to the middle of its
# range.
PATCHES = {
    0: ('Init', (67, 73)),
}

import audiodelays
import audiofreeverb
import synthio

from audioinstruments._support import (
    EVENT_NOTE_ON, EVENT_NOTE_OFF, EVENT_PARAMETER, key_of, logmap,
    make_table,
)
from audioinstruments._support import Instrument
from audioinstruments._support import static_transport
from audioinstruments import _support

DRAWBARS = make_table(((1, 1.0), (2, 0.85), (3, 0.5), (4, 0.4),
                       (6, 0.18), (8, 0.12)))


def create(sample_rate, transport=None):
    SR = sample_rate
    if transport is None:
        transport = static_transport
    def beat_clock():
        info = transport()
        bpm = info[2] if info[2] and info[2] > 1.0 else 120.0
        return bpm, info[1] * bpm / 60.0
    synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
    chorus = audiodelays.Chorus(max_delay_ms=30, delay_ms=11, voices=2,
                                mix=0.25, sample_rate=SR, channel_count=2,
                                bits_per_sample=16, samples_signed=True,
                                buffer_size=2048)
    verb = audiofreeverb.Freeverb(roomsize=0.8, damp=0.5, mix=0.2,
                                  sample_rate=SR, channel_count=2,
                                  bits_per_sample=16, samples_signed=True,
                                  buffer_size=2048)
    cutoff = synthio.Math(synthio.MathOperation.SUM, 1800.0, 0.0, 0.0)
    lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, cutoff, Q=0.75)
    env = synthio.Envelope(attack_time=0.03, decay_time=0.05,
                           release_time=0.12, attack_level=1.0,
                           sustain_level=1.0)

    chorus.play(synth)
    verb.play(chorus)

    voices = {}
    serial = 0




    def release_voice(k):
        _support.release_voice(voices, synth, k)


    def steal_oldest():
        _support.steal_oldest(voices, release_voice)

    MAX_VOICES = 4


    def handle_event(event_type, channel, note_id, data0, value0, value1,
                     sample_position):
        nonlocal serial
        k = key_of(channel, note_id, data0)
        if event_type == EVENT_NOTE_ON and value0 > 0.0:
            release_voice(k)
            if len(voices) >= MAX_VOICES:
                steal_oldest()
            hz = synthio.midi_to_hz(data0 + value1)
            amp = 0.16 + 0.22 * value0
            note = synthio.Note(hz, waveform=DRAWBARS, envelope=env,
                                filter=lp, amplitude=amp)
            serial += 1
            voices[k] = ((note,), serial)
            synth.press(note)
        elif event_type in (EVENT_NOTE_OFF, EVENT_NOTE_ON):
            release_voice(k)
        elif event_type == EVENT_PARAMETER:
            if data0 == 0:
                cutoff.a = logmap(value0, 700.0, 4200.0)
            elif data0 == 1:
                verb.mix = 0.35 * value0

    instrument = Instrument(synth, handle_event, PATCHES, MACRO_LABELS,
                            transport=transport, output=verb)
    instrument.program_change(0)
    return instrument


if __name__ == "__main__":
    import mpvst_adapter

    mpvst_adapter.attach(create)
