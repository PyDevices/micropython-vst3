# mpvst-macro-labels: Brightness | Space
#
# High string ensemble: brighter table than the low section, detuned pair
# per voice with independent vibrato phases, singing register. Macro 1 is
# brightness, macro 2 the hall.

import array
import math

import audiofreeverb
import synthio
import vstaudio

SR = vstaudio.sample_rate()
TAU = 2.0 * math.pi


def make_table(parts, length=2048, gain=32000):
    vals = [0.0] * length
    for mult, amp in parts:
        step = TAU * mult / length
        for i in range(length):
            vals[i] += amp * math.sin(step * i)
    peak = 0.0
    for v in vals:
        a = v if v >= 0.0 else -v
        if a > peak:
            peak = a
    if peak <= 0.0:
        peak = 1.0
    out = array.array("h", bytearray(length * 2))
    scale = gain / peak
    for i in range(length):
        out[i] = int(vals[i] * scale)
    return out


def logmap(v, lo, hi):
    return lo * ((hi / lo) ** v)


STRING = make_table([(n, 1.0 / (n ** 0.95)) for n in range(1, 27)])
DETUNE = 2.0 ** (6.0 / 1200.0)

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
cutoff = synthio.Math(synthio.MathOperation.SUM, 2400.0, 0.0, 0.0)
lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, cutoff, Q=0.8)
env = synthio.Envelope(attack_time=0.32, decay_time=0.3, release_time=1.6,
                       attack_level=1.0, sustain_level=0.85)

verb = audiofreeverb.Freeverb(roomsize=0.9, damp=0.42, mix=0.3,
                              sample_rate=SR, channel_count=2,
                              bits_per_sample=16, samples_signed=True,
                              buffer_size=2048)
verb.play(synth)

voices = {}
MAX_VOICES = 5
serial = 0


def key_of(channel, note_id, pitch):
    return (channel, note_id if note_id >= 0 else pitch)


def release_voice(k):
    voice = voices.pop(k, None)
    if voice is not None:
        for note in voice[0]:
            synth.release(note)


def steal_oldest():
    oldest = None
    for k in voices:
        if oldest is None or voices[k][1] < voices[oldest][1]:
            oldest = k
    if oldest is not None:
        release_voice(oldest)


def handle_event(event_type, channel, note_id, data0, value0, value1,
                 sample_position):
    global serial
    k = key_of(channel, note_id, data0)
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        if len(voices) >= MAX_VOICES:
            steal_oldest()
        hz = synthio.midi_to_hz(data0 + value1)
        amp = 0.13 + 0.2 * value0
        vib_a = synthio.LFO(rate=5.0 + 0.2 * (serial % 3), scale=0.0065,
                            phase_offset=0.29 * (serial % 3))
        vib_b = synthio.LFO(rate=5.3 - 0.17 * (serial % 3), scale=0.006,
                            phase_offset=0.61 * (serial % 2))
        a = synthio.Note(hz * DETUNE, waveform=STRING, envelope=env,
                         filter=lp, amplitude=amp, panning=-0.35, bend=vib_a)
        b = synthio.Note(hz / DETUNE, waveform=STRING, envelope=env,
                         filter=lp, amplitude=amp, panning=0.35, bend=vib_b)
        serial += 1
        voices[k] = ((a, b), serial)
        synth.press(a)
        synth.press(b)
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0:
            cutoff.a = logmap(value0, 620.0, 6800.0)
        elif data0 == 1:
            verb.mix = 0.12 + 0.4 * value0


# Patch 1 (Program Change 0) is the sound this script's module-level
# defaults describe, so a fresh instance and Patch 1 are the same thing.
# piece.py also reads it: a macro a composition does not set resolves here
# rather than to 0.5. Derived by tools/derive_patches.py - see that file
# before editing these numbers by hand.
PATCHES = {
    0: ("Init", (
        0.565147, 0.45)),
}


def _apply_patch(index, channel=0, note_id=-1, sample_position=0):
    patch = PATCHES.get(index)
    if patch is None:
        return
    for macro_index, macro_value in enumerate(patch[1]):
        handle_event(vstaudio.EVENT_PARAMETER, channel, note_id,
                     macro_index, macro_value, 0.0, sample_position)


def _dispatch(event_type, channel, note_id, data0, value0, value1,
              sample_position):
    if event_type == vstaudio.EVENT_PROGRAM_CHANGE:
        _apply_patch(data0, channel, note_id, sample_position)
        return
    handle_event(event_type, channel, note_id, data0, value0, value1,
                 sample_position)


vstaudio.on_event(_dispatch)

vstaudio.output(verb)
