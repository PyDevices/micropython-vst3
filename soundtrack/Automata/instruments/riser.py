# mpvst-macro-labels: Lift | Center | Space | Drop
"""Riser and tape stop: a cluster of detuned saws plus band-passed noise.
Automate Lift 0..1 across the bars before a drop and cut the note at
the downbeat; automate Drop 0..1 while a chord holds and the whole
cluster falls two octaves like a tape machine losing power. Macro 2
places the noise band, macro 3 the room.
"""

MACRO_LABELS = (
    "Lift", "Center", "Space", "Drop",
)

# Patch 0 is the sound this instrument's defaults describe, so a fresh
# instance and patch 0 are the same thing - create() applies it. A macro
# a caller does not set resolves here rather than to the middle of its
# range.
PATCHES = {
    0: ('Init', (0, 54, 57, 0)),
}

import audiofreeverb
import synthio

from audioinstruments._support import (
    EVENT_NOTE_ON, EVENT_NOTE_OFF, EVENT_PARAMETER, key_of, logmap,
    make_table, noise_table,
)
from audioinstruments._support import Instrument
from audioinstruments import _support

SAW = make_table([(n, 1.0 / n) for n in range(1, 19)], fast=False)
NOISE = noise_table(seed=246813579)


def create(sample_rate, transport=None):
    SR = sample_rate
    NOISE_HZ = SR / 8192.0
    synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
    verb = audiofreeverb.Freeverb(roomsize=0.9, damp=0.35, mix=0.3,
                                  sample_rate=SR, channel_count=2,
                                  bits_per_sample=16, samples_signed=True,
                                  buffer_size=2048)
    # Lift raises the cluster by up to an octave and swells its level.
    lift_bend = synthio.Math(synthio.MathOperation.SUM, 0.0, 0.0, 0.0)
    drop_bend = synthio.Math(synthio.MathOperation.SUM, 0.0, 0.0, 0.0)
    wobble = synthio.LFO(rate=6.5, scale=0.012)
    updown = synthio.Math(synthio.MathOperation.SUM, lift_bend, drop_bend, 0.0)
    bend_total = synthio.Math(synthio.MathOperation.SUM, updown, wobble, 0.0)
    center = synthio.Math(synthio.MathOperation.SUM, 1800.0, 0.0, 0.0)
    noise_bp = synthio.Biquad(synthio.FilterMode.BAND_PASS, center, Q=1.8)
    cluster_lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, 2600.0, Q=1.1)

    env = synthio.Envelope(attack_time=1.6, decay_time=0.4, release_time=0.35,
                           attack_level=1.0, sustain_level=1.0)

    verb.play(synth)

    DETUNES = (0.995, 1.0, 1.006)
    PANS = (-0.4, 0.0, 0.4)
    voices = {}
    MAX_VOICES = 2
    serial = 0




    def release_voice(k):
        _support.release_voice(voices, synth, k)


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
            hz = synthio.midi_to_hz(data0 + value1)
            amp = 0.1 + 0.2 * value0
            notes = []
            for i in range(3):
                notes.append(synthio.Note(hz * DETUNES[i], waveform=SAW,
                                          envelope=env, filter=cluster_lp,
                                          amplitude=amp, panning=PANS[i],
                                          bend=bend_total))
            notes.append(synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env,
                                      filter=noise_bp, amplitude=amp * 1.3,
                                      bend=updown))
            serial += 1
            voices[k] = (tuple(notes), serial)
            for note in notes:
                synth.press(note)
        elif event_type in (EVENT_NOTE_OFF, EVENT_NOTE_ON):
            release_voice(k)
        elif event_type == EVENT_PARAMETER:
            if data0 == 0:
                lift_bend.a = value0
            elif data0 == 1:
                center.a = logmap(value0, 700.0, 6400.0)
            elif data0 == 2:
                verb.mix = 0.12 + 0.4 * value0
            elif data0 == 3:
                drop_bend.a = -2.2 * value0

    instrument = Instrument(synth, handle_event, PATCHES, MACRO_LABELS,
                            transport=transport, output=verb)
    instrument.program_change(0)
    return instrument


if __name__ == "__main__":
    import mpvst_adapter

    mpvst_adapter.attach(create)
