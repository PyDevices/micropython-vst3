# mpvst-macro-labels: Cutoff | Pump | Space
"""Sidechain-pumping pad: warm detuned saws whose amplitude ducks on
every beat. The pump LFO reads the host transport at note-on for the
exact tempo and beat phase, so the duck locks to the kick with no
manual sync. Macro 1 opens the filter, macro 2 sets pump depth, macro 3
the hall.
"""

MACRO_LABELS = (
    "Cutoff", "Pump", "Space",
)

# Patch 0 is the sound this instrument's defaults describe, so a fresh
# instance and patch 0 are the same thing - create() applies it. A macro
# a caller does not set resolves here rather than to the middle of its
# range.
PATCHES = {
    0: ('Init', (57, 107, 51)),
}

import array
import audiofreeverb
import synthio

from audioinstruments._support import (
    EVENT_NOTE_ON, EVENT_NOTE_OFF, EVENT_PARAMETER, key_of, logmap,
    make_table,
)
from audioinstruments._support import Instrument
from audioinstruments._support import static_transport
from audioinstruments import _support

SAW = make_table([(n, 1.0 / (n ** 1.25)) for n in range(1, 19)], fast=False)
DETUNE = 2.0 ** (7.0 / 1200.0)

# One cycle of the duck: hard dip right after the beat, exponential-ish
# recovery to full level. 0..32767 so scale/offset shape it linearly.
PUMP = array.array("h", bytearray(256 * 2))
for i in range(256):
    x = i / 255.0
    PUMP[i] = int(32767 * (0.06 + 0.94 * (x ** 0.6)))


def create(sample_rate, transport=None):
    SR = sample_rate
    if transport is None:
        transport = static_transport
    def beat_clock():
        info = transport()
        bpm = info[2] if info[2] and info[2] > 1.0 else 120.0
        return bpm, info[1] * bpm / 60.0
    synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
    verb = audiofreeverb.Freeverb(roomsize=0.88, damp=0.4, mix=0.26,
                                  sample_rate=SR, channel_count=2,
                                  bits_per_sample=16, samples_signed=True,
                                  buffer_size=2048)
    cutoff = synthio.Math(synthio.MathOperation.SUM, 1400.0, 0.0, 0.0)
    lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, cutoff, Q=1.0)
    depth = synthio.Math(synthio.MathOperation.SUM, 0.8, 0.0, 0.0)
    rest = synthio.Math(synthio.MathOperation.SUM, 0.2, 0.0, 0.0)
    env = synthio.Envelope(attack_time=0.03, decay_time=0.3,
                           release_time=0.5, attack_level=1.0,
                           sustain_level=0.9)

    verb.play(synth)

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
            bpm, beats = beat_clock()
            hz = synthio.midi_to_hz(data0 + value1)
            amp = 0.1 + 0.13 * value0
            pump = synthio.LFO(waveform=PUMP, rate=bpm / 60.0,
                               scale=depth, offset=rest,
                               phase_offset=beats % 1.0, interpolate=True)
            vol_a = synthio.Math(synthio.MathOperation.PRODUCT, pump, amp, 1.0)
            vol_b = synthio.Math(synthio.MathOperation.PRODUCT, pump, amp, 1.0)
            a = synthio.Note(hz * DETUNE, waveform=SAW, envelope=env,
                             filter=lp, amplitude=vol_a, panning=-0.4)
            b = synthio.Note(hz / DETUNE, waveform=SAW, envelope=env,
                             filter=lp, amplitude=vol_b, panning=0.4)
            serial += 1
            voices[k] = ((a, b), serial)
            synth.press(a)
            synth.press(b)
        elif event_type in (EVENT_NOTE_OFF, EVENT_NOTE_ON):
            release_voice(k)
        elif event_type == EVENT_PARAMETER:
            if data0 == 0:
                cutoff.a = logmap(value0, 380.0, 6800.0)
            elif data0 == 1:
                depth.a = 0.95 * value0
                rest.a = 1.0 - 0.95 * value0
            elif data0 == 2:
                verb.mix = 0.1 + 0.4 * value0

    instrument = Instrument(synth, handle_event, PATCHES, MACRO_LABELS,
                            transport=transport, output=verb)
    instrument.program_change(0)
    return instrument


if __name__ == "__main__":
    import mpvst_adapter

    mpvst_adapter.attach(create)
