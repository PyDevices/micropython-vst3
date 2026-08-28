# mpvst-macro-labels: Echo
"""Glitch percussion, three flavors by pitch: below 40 a ring-swept zap,
40-59 a crushed noise burst, 60 and up a bare tick. A tempo-synced
echo (via vstaudio.transport) turns single hits into stutters; macro 1
is the echo send.
"""

MACRO_LABELS = (
    "Echo",
)

# Patch 0 is the sound this instrument's defaults describe, so a fresh
# instance and patch 0 are the same thing - create() applies it. A macro
# a caller does not set resolves here rather than to the middle of its
# range.
PATCHES = {
    0: ('Init', (56,)),
}

import audiodelays
import audiofilters
import synthio

from audioinstruments._support import (
    EVENT_NOTE_ON, EVENT_NOTE_OFF, EVENT_PARAMETER, FALL, key_of,
    make_table, noise_table,
)
from audioinstruments._support import Instrument
from audioinstruments._support import static_transport
from audioinstruments import _support

SQUARE = make_table([(n, 1.0 / n) for n in range(1, 12, 2)], fast=False)
SINE = make_table(((1, 1.0),), fast=False)
NOISE = noise_table(seed=5647382910)


def create(sample_rate, transport=None):
    SR = sample_rate
    if transport is None:
        transport = static_transport
    NOISE_HZ = SR / 8192.0
    synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
    crush = audiofilters.Distortion(drive=0.82, mix=0.85,
                                    sample_rate=SR, channel_count=2,
                                    bits_per_sample=16, samples_signed=True,
                                    buffer_size=2048)
    echo = audiodelays.Echo(max_delay_ms=900, delay_ms=180, decay=0.45,
                            mix=0.2, sample_rate=SR, channel_count=2,
                            bits_per_sample=16, samples_signed=True,
                            buffer_size=2048, freq_shift=False)
    def sync_echo():
        info = transport()
        bpm = info[2] if info[2] and info[2] > 1.0 else 120.0
        want = 60000.0 / bpm * 0.75
        if abs(echo.delay_ms - want) > 4.0:
            echo.delay_ms = want
    crush.play(synth)
    echo.play(crush)

    tick_hp = synthio.Biquad(synthio.FilterMode.HIGH_PASS, 6000.0, Q=0.8)
    zap_lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, 2400.0, Q=2.2)
    burst_bp = synthio.Biquad(synthio.FilterMode.BAND_PASS, 2800.0, Q=1.0)

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
            sync_echo()
            amp = 0.22 + 0.4 * value0
            pan = 0.4 - 0.2 * (serial % 5)
            if data0 < 40:
                env = synthio.Envelope(attack_time=0.001, decay_time=0.15,
                                       release_time=0.06, attack_level=1.0,
                                       sustain_level=0.0)
                sweep = synthio.LFO(waveform=FALL, once=True, rate=9.0,
                                    scale=2.5, interpolate=True)
                note = synthio.Note(synthio.midi_to_hz(data0 + 24),
                                    waveform=SQUARE, envelope=env,
                                    filter=zap_lp, amplitude=amp, panning=pan,
                                    ring_frequency=880.0, ring_waveform=SINE,
                                    ring_bend=sweep)
            elif data0 < 60:
                env = synthio.Envelope(attack_time=0.001, decay_time=0.07,
                                       release_time=0.04, attack_level=1.0,
                                       sustain_level=0.0)
                note = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env,
                                    filter=burst_bp, amplitude=amp, panning=pan)
            else:
                env = synthio.Envelope(attack_time=0.0005, decay_time=0.012,
                                       release_time=0.01, attack_level=1.0,
                                       sustain_level=0.0)
                note = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env,
                                    filter=tick_hp, amplitude=amp, panning=pan)
            serial += 1
            voices[k] = ((note,), serial)
            synth.press(note)
        elif event_type in (EVENT_NOTE_OFF, EVENT_NOTE_ON):
            release_voice(k)
        elif event_type == EVENT_PARAMETER:
            if data0 == 0:
                echo.mix = 0.45 * value0

    instrument = Instrument(synth, handle_event, PATCHES, MACRO_LABELS,
                            transport=transport, output=echo)
    instrument.program_change(0)
    return instrument


if __name__ == "__main__":
    import mpvst_adapter

    mpvst_adapter.attach(create)
