# mpvst-macro-labels: Tone | Room
#
# Clap: three noise bursts whose attacks are staggered by a few
# milliseconds - the smear of many hands - through a band-pass and a
# real room. Macro 1 moves the band, macro 2 the room.

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


NOISE = noise_table(seed=24681357)
NOISE_HZ = SR / 8192.0

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
band = synthio.Math(synthio.MathOperation.SUM, 1150.0, 0.0, 0.0)
bp = synthio.Biquad(synthio.FilterMode.BAND_PASS, band, Q=1.3)

ATTACKS = (0.001, 0.013, 0.027)
PANS = (-0.12, 0.0, 0.12)

verb = audiofreeverb.Freeverb(roomsize=0.85, damp=0.45, mix=0.28,
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
        amp = 0.24 + 0.4 * value0
        notes = []
        for i in range(3):
            env = synthio.Envelope(attack_time=ATTACKS[i], decay_time=0.16,
                                   release_time=0.08, attack_level=1.0,
                                   sustain_level=0.0)
            notes.append(synthio.Note(NOISE_HZ, waveform=NOISE,
                                      envelope=env, filter=bp,
                                      amplitude=amp * (1.0 - 0.18 * i),
                                      panning=PANS[i]))
        serial += 1
        voices[k] = (tuple(notes), serial)
        for note in notes:
            synth.press(note)
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0:
            band.a = logmap(value0, 800.0, 2100.0)
        elif data0 == 1:
            verb.mix = 0.45 * value0


# Patch 1 (Program Change 0) is the sound this script's module-level
# defaults describe, so a fresh instance and Patch 1 are the same thing.
# piece.py also reads it: a macro a composition does not set resolves here
# rather than to 0.5. Derived by tools/derive_patches.py - see that file
# before editing these numbers by hand.
PATCHES = {
    0: ("Init", (
        0.376036, 0.622222)),
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
