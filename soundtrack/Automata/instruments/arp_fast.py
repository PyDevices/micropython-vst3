# mpvst-macro-labels: Cutoff | Echo
"""Fast arpeggio synth: a bright saw-plus-octave pluck with a filter
snap, ping-ponging across the field, with a light tempo-synced echo.
Macros: cutoff, echo send.
"""

MACRO_LABELS = (
    "Cutoff", "Echo",
)

# Patch 0 is the sound this instrument's defaults describe, so a fresh
# instance and patch 0 are the same thing - create() applies it. A macro
# a caller does not set resolves here rather than to the middle of its
# range.
PATCHES = {
    0: ('Init', (72, 51)),
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

BRIGHT = make_table([(n, 1.0 / n) for n in range(1, 21)] +
                    [(2, 0.5)])


def create(sample_rate, transport=None):
    SR = sample_rate
    if transport is None:
        transport = static_transport
    def beat_clock():
        info = transport()
        bpm = info[2] if info[2] and info[2] > 1.0 else 120.0
        return bpm, info[1] * bpm / 60.0
    synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
    echo = audiodelays.Echo(max_delay_ms=800, delay_ms=250, decay=0.35,
                            mix=0.16, sample_rate=SR, channel_count=2,
                            bits_per_sample=16, samples_signed=True,
                            buffer_size=2048, freq_shift=False)
    cutoff = synthio.Math(synthio.MathOperation.SUM, 2600.0, 0.0, 0.0)
    env = synthio.Envelope(attack_time=0.003, decay_time=0.09,
                           release_time=0.1, attack_level=1.0,
                           sustain_level=0.15)

    echo.play(synth)

    PAN = (-0.45, 0.15, 0.45, -0.15)

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
            want = 60000.0 / bpm * 0.75
            if abs(echo.delay_ms - want) > 4.0:
                echo.delay_ms = want
            hz = synthio.midi_to_hz(data0 + value1)
            amp = 0.18 + 0.32 * value0
            snap = synthio.LFO(waveform=FALL, once=True, rate=1.0 / 0.08,
                               scale=700.0 + 900.0 * value0, interpolate=True)
            freq = synthio.Math(synthio.MathOperation.SUM, cutoff, snap, 0.0)
            flt = synthio.Biquad(synthio.FilterMode.LOW_PASS, freq, Q=1.7)
            note = synthio.Note(hz, waveform=BRIGHT, envelope=env,
                                filter=flt, amplitude=amp,
                                panning=PAN[serial % 4])
            serial += 1
            voices[k] = ((note,), serial)
            synth.press(note)
        elif event_type in (EVENT_NOTE_OFF, EVENT_NOTE_ON):
            release_voice(k)
        elif event_type == EVENT_PARAMETER:
            if data0 == 0:
                cutoff.a = logmap(value0, 500.0, 9000.0)
            elif data0 == 1:
                echo.mix = 0.4 * value0

    instrument = Instrument(synth, handle_event, PATCHES, MACRO_LABELS,
                            transport=transport, output=echo)
    instrument.program_change(0)
    return instrument


if __name__ == "__main__":
    import mpvst_adapter

    mpvst_adapter.attach(create)
