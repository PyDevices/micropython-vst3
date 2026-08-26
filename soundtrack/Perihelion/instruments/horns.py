# mpvst-macro-labels: Bloom | Space
#
# Horn ensemble: softened saw pair whose low-pass blooms open over the first
# third of a second of every note - the brass "wah" that sells a sustained
# horn pad. Macro 1 sets how far the bloom opens, macro 2 the room.

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


HORN = make_table([(n, 1.0 / (n ** 1.2)) for n in range(1, 17)])
DETUNE = 2.0 ** (4.0 / 1200.0)
RISE = array.array("h", (0, 32767))

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
bloom = 2000.0
env = synthio.Envelope(attack_time=0.12, decay_time=0.2, release_time=0.9,
                       attack_level=1.0, sustain_level=0.9)

verb = audiofreeverb.Freeverb(roomsize=0.85, damp=0.45, mix=0.25,
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
    global serial, bloom
    k = key_of(channel, note_id, data0)
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        if len(voices) >= MAX_VOICES:
            steal_oldest()
        hz = synthio.midi_to_hz(data0 + value1)
        amp = 0.11 + 0.16 * value0
        opener = synthio.LFO(waveform=RISE, once=True, rate=1.0 / 0.35,
                             scale=bloom * (0.5 + 0.5 * value0),
                             interpolate=True)
        freq = synthio.Math(synthio.MathOperation.SUM, 260.0, opener, 0.0)
        flt = synthio.Biquad(synthio.FilterMode.LOW_PASS, freq, Q=1.3)
        a = synthio.Note(hz * DETUNE, waveform=HORN, envelope=env,
                         filter=flt, amplitude=amp, panning=-0.25)
        b = synthio.Note(hz / DETUNE, waveform=HORN, envelope=env,
                         filter=flt, amplitude=amp, panning=0.2)
        serial += 1
        voices[k] = ((a, b), serial)
        synth.press(a)
        synth.press(b)
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0:
            bloom = logmap(value0, 480.0, 3900.0)
        elif data0 == 1:
            verb.mix = 0.1 + 0.35 * value0


# Patch 1 (Program Change 0) is the sound this script's module-level
# defaults describe, so a fresh instance and Patch 1 are the same thing.
# piece.py also reads it: a macro a composition does not set resolves here
# rather than to 0.5. Derived by tools/derive_patches.py - see that file
# before editing these numbers by hand.
PATCHES = {
    0: ("Init", (
        0.681219, 0.428571)),
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
