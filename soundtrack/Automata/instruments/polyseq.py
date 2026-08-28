# mpvst-macro-labels: Cutoff | Resonance | Echo
"""Sequenced polysynth: a hollow squarish pluck with a per-note filter
snap and a tempo-synced echo at three eighths - the engine of the 7/8
movement. Notes alternate across the stereo field. Macros: cutoff,
resonance, echo send.
"""

MACRO_LABELS = (
    "Cutoff", "Resonance", "Echo",
)

# Patch 0 is the sound this instrument's defaults describe, so a fresh
# instance and patch 0 are the same thing - create() applies it. A macro
# a caller does not set resolves here rather than to the middle of its
# range.
PATCHES = {
    0: ('Init', (63, 31, 76)),
}

import audiodelays
import synthio

from audioinstruments._support import (
    EVENT_NOTE_ON, EVENT_NOTE_OFF, EVENT_PARAMETER, FALL, key_of, logmap,
    make_table,
)
from audioinstruments._support import Instrument
from audioinstruments._support import static_transport
from audioinstruments import _support

HOLLOW = make_table([(n, 1.0 / n) for n in range(1, 14, 2)] +
                    [(2, 0.22), (4, 0.1)])
DETUNE = 2.0 ** (6.0 / 1200.0)


def create(sample_rate, transport=None):
    SR = sample_rate
    if transport is None:
        transport = static_transport
    def beat_clock():
        info = transport()
        bpm = info[2] if info[2] and info[2] > 1.0 else 120.0
        return bpm, info[1] * bpm / 60.0
    synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
    echo = audiodelays.Echo(max_delay_ms=1200, delay_ms=800, decay=0.42,
                            mix=0.3, sample_rate=SR, channel_count=2,
                            bits_per_sample=16, samples_signed=True,
                            buffer_size=2048, freq_shift=False)
    cutoff = synthio.Math(synthio.MathOperation.SUM, 1500.0, 0.0, 0.0)
    resonance = synthio.Math(synthio.MathOperation.SUM, 2.2, 0.0, 0.0)
    env = synthio.Envelope(attack_time=0.004, decay_time=0.16,
                           release_time=0.2, attack_level=1.0,
                           sustain_level=0.25)

    echo.play(synth)

    PAN = (-0.4, 0.25, -0.15, 0.4, 0.0, -0.3, 0.35)

    voices = {}
    serial = 0




    def release_voice(k):
        _support.release_voice(voices, synth, k)


    def steal_oldest():
        _support.steal_oldest(voices, release_voice)

    MAX_VOICES = 5


    def handle_event(event_type, channel, note_id, data0, value0, value1,
                     sample_position):
        nonlocal serial
        k = key_of(channel, note_id, data0)
        if event_type == EVENT_NOTE_ON and value0 > 0.0:
            release_voice(k)
            if len(voices) >= MAX_VOICES:
                steal_oldest()
            bpm, _ = beat_clock()
            want = 60000.0 / bpm * 1.5
            if abs(echo.delay_ms - want) > 4.0:
                echo.delay_ms = want
            hz = synthio.midi_to_hz(data0 + value1)
            amp = 0.2 + 0.34 * value0
            snap = synthio.LFO(waveform=FALL, once=True, rate=1.0 / 0.1,
                               scale=500.0 + 1100.0 * value0, interpolate=True)
            freq = synthio.Math(synthio.MathOperation.SUM, cutoff, snap, 0.0)
            flt = synthio.Biquad(synthio.FilterMode.LOW_PASS, freq, Q=resonance)
            note = synthio.Note(hz * DETUNE, waveform=HOLLOW, envelope=env,
                                filter=flt, amplitude=amp,
                                panning=PAN[serial % 7])
            serial += 1
            voices[k] = ((note,), serial)
            synth.press(note)
        elif event_type in (EVENT_NOTE_OFF, EVENT_NOTE_ON):
            release_voice(k)
        elif event_type == EVENT_PARAMETER:
            if data0 == 0:
                cutoff.a = logmap(value0, 320.0, 7200.0)
            elif data0 == 1:
                resonance.a = 0.8 + 5.8 * value0
            elif data0 == 2:
                echo.mix = 0.5 * value0

    instrument = Instrument(synth, handle_event, PATCHES, MACRO_LABELS,
                            transport=transport, output=echo)
    instrument.program_change(0)
    return instrument


if __name__ == "__main__":
    import mpvst_adapter

    mpvst_adapter.attach(create)
