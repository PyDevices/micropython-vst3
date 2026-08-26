# mpvst-macro-labels: Cutoff | Resonance | Env Amount | Glide
"""303-style acid bass: one saw into a screaming resonant low-pass with a
per-note filter pluck, through soft-clip distortion. Monophonic with
real slides - an overlapping note glides the pitch instead of
retriggering, exactly like tying notes on the original. Velocity above
0.85 is an accent. Macros: cutoff, resonance, envelope amount, glide.
"""

MACRO_LABELS = (
    "Cutoff", "Resonance", "Env Amount", "Glide",
)

# Patch 0 is the sound this instrument's defaults describe, so a fresh
# instance and patch 0 are the same thing - create() applies it. A macro
# a caller does not set resolves here rather than to the middle of its
# range.
PATCHES = {
    0: ('Init', (57, 33, 48, 22)),
}

import audiofilters
import math
import synthio

from audioinstruments._support import (
    EVENT_NOTE_ON, EVENT_NOTE_OFF, EVENT_PARAMETER, FALL, logmap,
    make_table,
)
from audioinstruments._support import Instrument
from audioinstruments._support import static_transport

SAW = make_table([(n, 1.0 / n) for n in range(1, 25)], fast=False)


def create(sample_rate, transport=None):
    SR = sample_rate
    if transport is None:
        transport = static_transport
    def beat_clock():
        info = transport()
        bpm = info[2] if info[2] and info[2] > 1.0 else 120.0
        return bpm, info[1] * bpm / 60.0
    synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
    grit = audiofilters.Distortion(drive=0.5, post_gain=-3.0, soft_clip=True,
                                   mix=0.55, sample_rate=SR, channel_count=2,
                                   bits_per_sample=16, samples_signed=True,
                                   buffer_size=2048)
    cutoff = synthio.Math(synthio.MathOperation.SUM, 700.0, 0.0, 0.0)
    resonance = synthio.Math(synthio.MathOperation.SUM, 3.0, 0.0, 0.0)
    env_amount = 1800.0
    glide_time = 0.055

    grit.play(synth)

    env = synthio.Envelope(attack_time=0.003, decay_time=0.19,
                           release_time=0.07, attack_level=1.0,
                           sustain_level=0.3)

    # Monophonic state: the sounding note and the stack of held keys so a
    # release can fall back to the previous pitch (last-note priority).
    current = None          # (note, hz)
    held = []               # [(key, pitch)]


    def start_note(pitch, velocity):
        nonlocal current
        hz = synthio.midi_to_hz(pitch)
        accent = velocity > 0.85
        amp = (0.4 + 0.4 * velocity) * (1.25 if accent else 1.0)
        pluck = synthio.LFO(waveform=FALL, once=True,
                            rate=1.0 / (0.14 if accent else 0.22),
                            scale=env_amount * (1.5 if accent else 1.0),
                            interpolate=True)
        freq = synthio.Math(synthio.MathOperation.SUM, cutoff, pluck, 0.0)
        flt = synthio.Biquad(synthio.FilterMode.LOW_PASS, freq, Q=resonance)
        note = synthio.Note(hz, waveform=SAW, envelope=env, filter=flt,
                            amplitude=amp)
        if current is not None:
            synth.release(current[0])
        current = (note, hz)
        synth.press(note)


    def slide_to(pitch):
        nonlocal current
        note, old_hz = current
        new_hz = synthio.midi_to_hz(pitch)
        note.frequency = new_hz
        note.bend = synthio.LFO(waveform=FALL, once=True,
                                rate=1.0 / max(0.015, glide_time),
                                scale=math.log(old_hz / new_hz) / math.log(2.0),
                                interpolate=True)
        current = (note, new_hz)


    def handle_event(event_type, channel, note_id, data0, value0, value1,
                     sample_position):
        nonlocal current, env_amount, glide_time
        k = (channel, note_id if note_id >= 0 else data0)
        if event_type == EVENT_NOTE_ON and value0 > 0.0:
            if current is not None and held:
                held.append((k, data0))
                slide_to(data0)
            else:
                held.append((k, data0))
                start_note(data0, value0)
        elif event_type in (EVENT_NOTE_OFF, EVENT_NOTE_ON):
            for i in range(len(held) - 1, -1, -1):
                if held[i][0] == k:
                    was_last = (i == len(held) - 1)
                    held.pop(i)
                    if was_last and current is not None:
                        if held:
                            slide_to(held[-1][1])
                        else:
                            synth.release(current[0])
                            current = None
                    break
        elif event_type == EVENT_PARAMETER:
            if data0 == 0:
                cutoff.a = logmap(value0, 110.0, 6800.0)
            elif data0 == 1:
                resonance.a = 0.8 + 8.4 * value0
            elif data0 == 2:
                env_amount = 4800.0 * value0
            elif data0 == 3:
                glide_time = 0.02 + 0.2 * value0

    instrument = Instrument(synth, handle_event, PATCHES, MACRO_LABELS,
                            transport=transport, output=grit)
    instrument.program_change(0)
    return instrument


if __name__ == "__main__":
    import mpvst_adapter

    mpvst_adapter.attach(create)
