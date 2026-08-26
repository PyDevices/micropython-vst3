# mpvst-macro-labels: Tone | Room
#
# Snare: tonal body at 185 Hz with a quick settle, band-passed wire noise,
# and a high sizzle layer. Velocity mostly drives the noise, so ghost
# notes come out as soft body taps. Macro 1 moves the wire band, macro 2
# the room.

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


def noise_table(length=8192, seed=1234567):
    out = array.array("h", bytearray(length * 2))
    state = seed
    for i in range(length):
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        out[i] = ((state >> 15) & 0xFFFF) - 32768
    return out


def logmap(v, lo, hi):
    return lo * ((hi / lo) ** v)


BODY = make_table(((1, 1.0), (1.6, 0.4)))
NOISE = noise_table(seed=87654321)
NOISE_HZ = SR / 8192.0
FALL = array.array("h", (32767, 0))

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
wire_center = synthio.Math(synthio.MathOperation.SUM, 1700.0, 0.0, 0.0)
wire_bp = synthio.Biquad(synthio.FilterMode.BAND_PASS, wire_center, Q=1.1)
sizzle_hp = synthio.Biquad(synthio.FilterMode.HIGH_PASS, 5200.0, Q=0.7)

body_env = synthio.Envelope(attack_time=0.001, decay_time=0.1,
                            release_time=0.05, attack_level=1.0,
                            sustain_level=0.0)
wire_env = synthio.Envelope(attack_time=0.001, decay_time=0.13,
                            release_time=0.07, attack_level=1.0,
                            sustain_level=0.0)
sizzle_env = synthio.Envelope(attack_time=0.001, decay_time=0.2,
                              release_time=0.1, attack_level=1.0,
                              sustain_level=0.0)

verb = audiofreeverb.Freeverb(roomsize=0.75, damp=0.5, mix=0.14,
                              sample_rate=SR, channel_count=2,
                              bits_per_sample=16, samples_signed=True,
                              buffer_size=2048)
verb.play(synth)

voices = {}
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

MAX_VOICES = 3


def handle_event(event_type, channel, note_id, data0, value0, value1,
                 sample_position):
    global serial
    k = key_of(channel, note_id, data0)
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        if len(voices) >= MAX_VOICES:
            steal_oldest()
        amp = 0.3 + 0.5 * value0
        settle = synthio.LFO(waveform=FALL, once=True, rate=16.0,
                             scale=0.22, interpolate=True)
        body = synthio.Note(185.0, waveform=BODY, envelope=body_env,
                            amplitude=amp * 0.8, bend=settle)
        wire = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=wire_env,
                            filter=wire_bp,
                            amplitude=amp * (0.25 + 0.75 * value0))
        sizzle = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=sizzle_env,
                              filter=sizzle_hp,
                              amplitude=amp * 0.5 * value0, panning=0.06)
        serial += 1
        voices[k] = ((body, wire, sizzle), serial)
        for note in voices[k][0]:
            synth.press(note)
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0:
            wire_center.a = logmap(value0, 1100.0, 3200.0)
        elif data0 == 1:
            verb.mix = 0.35 * value0


# Patch 1 (Program Change 0) is the sound this script's module-level
# defaults describe, so a fresh instance and Patch 1 are the same thing.
# piece.py also reads it: a macro a composition does not set resolves here
# rather than to 0.5. Derived by tools/derive_patches.py - see that file
# before editing these numbers by hand.
PATCHES = {
    0: ("Init", (
        0.407662, 0.4)),
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
