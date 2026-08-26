# mpvst-macro-labels: Doom | Space
#
# Cinematic impact: every note fires three layers - a sub boom with a
# falling pitch, a braam of detuned saws (root and fifth) whose filter
# blooms open, and a noise crack transient - into a huge room. Macro 1
# darkens or opens the braam, macro 2 the room.

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


def noise_table(length=8192, seed=192837465):
    out = array.array("h", bytearray(length * 2))
    state = seed
    for i in range(length):
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        out[i] = ((state >> 15) & 0xFFFF) - 32768
    return out


def logmap(v, lo, hi):
    return lo * ((hi / lo) ** v)


SINE = make_table(((1, 1.0), (2, 0.12)))
SAW = make_table([(n, 1.0 / n) for n in range(1, 23)])
NOISE = noise_table()
NOISE_HZ = SR / 8192.0
FALL = array.array("h", (32767, 0))
RISE = array.array("h", (0, 32767))
DETUNE = 2.0 ** (9.0 / 1200.0)

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
doom = synthio.Math(synthio.MathOperation.SUM, 500.0, 0.0, 0.0)

boom_env = synthio.Envelope(attack_time=0.002, decay_time=2.6,
                            release_time=1.2, attack_level=1.0,
                            sustain_level=0.0)
braam_env = synthio.Envelope(attack_time=0.7, decay_time=1.6,
                             release_time=2.4, attack_level=1.0,
                             sustain_level=0.35)
crack_env = synthio.Envelope(attack_time=0.001, decay_time=0.14,
                             release_time=0.1, attack_level=1.0,
                             sustain_level=0.0)
crack_hp = synthio.Biquad(synthio.FilterMode.HIGH_PASS, 1400.0, Q=0.8)
boom_lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, 160.0, Q=0.9)

verb = audiofreeverb.Freeverb(roomsize=0.95, damp=0.4, mix=0.38,
                              sample_rate=SR, channel_count=2,
                              bits_per_sample=16, samples_signed=True,
                              buffer_size=2048)
verb.play(synth)

voices = {}
MAX_VOICES = 2
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
        amp = 0.26 + 0.36 * value0
        drop = synthio.LFO(waveform=FALL, once=True, rate=1.0 / 0.4,
                           scale=0.6, interpolate=True)
        boom = synthio.Note(hz * 0.5, waveform=SINE, envelope=boom_env,
                            filter=boom_lp, amplitude=amp, bend=drop)
        bloom = synthio.LFO(waveform=RISE, once=True, rate=1.0 / 1.2,
                            scale=doom, interpolate=True)
        bfreq = synthio.Math(synthio.MathOperation.SUM, 110.0, bloom, 0.0)
        blp = synthio.Biquad(synthio.FilterMode.LOW_PASS, bfreq, Q=1.6)
        braam_a = synthio.Note(hz * DETUNE, waveform=SAW, envelope=braam_env,
                               filter=blp, amplitude=amp * 0.6, panning=-0.3)
        braam_b = synthio.Note(hz * 1.5 / DETUNE, waveform=SAW,
                               envelope=braam_env, filter=blp,
                               amplitude=amp * 0.42, panning=0.3)
        crack = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=crack_env,
                             filter=crack_hp, amplitude=amp * 0.3)
        serial += 1
        voices[k] = ((boom, braam_a, braam_b, crack), serial)
        for note in voices[k][0]:
            synth.press(note)
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0:
            doom.a = logmap(value0, 140.0, 1700.0)
        elif data0 == 1:
            verb.mix = 0.15 + 0.4 * value0


# Patch 1 (Program Change 0) is the sound this script's module-level
# defaults describe, so a fresh instance and Patch 1 are the same thing.
# piece.py also reads it: a macro a composition does not set resolves here
# rather than to 0.5. Derived by tools/derive_patches.py - see that file
# before editing these numbers by hand.
PATCHES = {
    0: ("Init", (
        0.509851, 0.575)),
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
