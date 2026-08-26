# mpvst-macro-labels: Cutoff | Resonance | Echo
"""Signal lead: monophonic Moog-style lead - saw plus sub-octave square
through a resonant low-pass, delayed vibrato, tempo-ish echo. Macro 1
sweeps the cutoff, macro 2 the resonance, macro 3 the echo send.
"""

MACRO_LABELS = (
    "Cutoff", "Resonance", "Echo",
)

# Patch 0 is the sound this instrument's defaults describe, so a fresh
# instance and patch 0 are the same thing - create() applies it. A macro
# a caller does not set resolves here rather than to the middle of its
# range.
PATCHES = {
    0: ('Init', (75, 19, 64)),
}

import array
import audiodelays
import audiofreeverb
import synthio

from audioinstruments._support import (
    EVENT_NOTE_ON, EVENT_NOTE_OFF, EVENT_PARAMETER, logmap, make_table,
)
from audioinstruments._support import Instrument

SAW = make_table([(n, 1.0 / n) for n in range(1, 25)], fast=False)
SQUARE = make_table([(n, 1.0 / n) for n in range(1, 14, 2)], fast=False)
DETUNE = 2.0 ** (5.0 / 1200.0)
RISE = array.array("h", (0, 32767))


def create(sample_rate, transport=None):
    SR = sample_rate
    synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
    echo = audiodelays.Echo(max_delay_ms=700, delay_ms=320, decay=0.42,
                            mix=0.25, sample_rate=SR, channel_count=2,
                            bits_per_sample=16, samples_signed=True,
                            buffer_size=2048)
    verb = audiofreeverb.Freeverb(roomsize=0.8, damp=0.4, mix=0.18,
                                  sample_rate=SR, channel_count=2,
                                  bits_per_sample=16, samples_signed=True,
                                  buffer_size=2048)
    cutoff = synthio.Math(synthio.MathOperation.SUM, 2200.0, 0.0, 0.0)
    resonance = synthio.Math(synthio.MathOperation.SUM, 1.6, 0.0, 0.0)
    lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, cutoff, Q=resonance)
    env = synthio.Envelope(attack_time=0.03, decay_time=0.2, release_time=0.6,
                           attack_level=1.0, sustain_level=0.85)

    echo.play(synth)
    verb.play(echo)

    current = None


    def release_current():
        nonlocal current
        if current is not None:
            for note in current[1]:
                synth.release(note)
            current = None


    def handle_event(event_type, channel, note_id, data0, value0, value1,
                     sample_position):
        nonlocal current
        k = (channel, note_id if note_id >= 0 else data0)
        if event_type == EVENT_NOTE_ON and value0 > 0.0:
            release_current()
            hz = synthio.midi_to_hz(data0 + value1)
            amp = 0.22 + 0.28 * value0
            wobble = synthio.LFO(rate=5.4, scale=0.011)
            onset = synthio.LFO(waveform=RISE, once=True, rate=1.0 / 0.7,
                                scale=1.0, interpolate=True)
            vib = synthio.Math(synthio.MathOperation.PRODUCT, wobble, onset, 0.0)
            a = synthio.Note(hz * DETUNE, waveform=SAW, envelope=env, filter=lp,
                             amplitude=amp, panning=-0.08, bend=vib)
            b = synthio.Note(hz * 0.5, waveform=SQUARE, envelope=env, filter=lp,
                             amplitude=amp * 0.6, panning=0.08, bend=vib)
            current = (k, (a, b))
            synth.press(a)
            synth.press(b)
        elif event_type in (EVENT_NOTE_OFF, EVENT_NOTE_ON):
            if current is not None and current[0] == k:
                release_current()
        elif event_type == EVENT_PARAMETER:
            if data0 == 0:
                cutoff.a = logmap(value0, 320.0, 8200.0)
            elif data0 == 1:
                resonance.a = 0.8 + 5.4 * value0
            elif data0 == 2:
                echo.mix = 0.5 * value0

    instrument = Instrument(synth, handle_event, PATCHES, MACRO_LABELS,
                            transport=transport, output=verb)
    instrument.program_change(0)
    return instrument


if __name__ == "__main__":
    import mpvst_adapter

    mpvst_adapter.attach(create)
