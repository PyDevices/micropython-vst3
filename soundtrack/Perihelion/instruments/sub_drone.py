# mpvst-macro-labels: Depth | Space
#
# Aphelion sub drone: sine with a touch of 2nd/3rd harmonic, very slow
# attack, low-pass depth macro, small reverb. The floor of the score.

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


WARM = make_table(((1, 1.0), (2, 0.18), (3, 0.07)))

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
cutoff = synthio.Math(synthio.MathOperation.SUM, 140.0, 0.0, 0.0)
lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, cutoff, Q=0.9)
env = synthio.Envelope(attack_time=2.5, decay_time=0.5, release_time=4.5,
                       attack_level=1.0, sustain_level=1.0)

verb = audiofreeverb.Freeverb(roomsize=0.72, damp=0.5, mix=0.12,
                              sample_rate=SR, channel_count=2,
                              bits_per_sample=16, samples_signed=True,
                              buffer_size=2048)
verb.play(synth)

voices = {}
MAX_VOICES = 4


def key_of(channel, note_id, pitch):
    return (channel, note_id if note_id >= 0 else pitch)


def steal_oldest():
    oldest = None
    for k in voices:
        if oldest is None or voices[k][1] < voices[oldest][1]:
            oldest = k
    if oldest is not None:
        synth.release(voices.pop(oldest)[0])


serial = 0


def handle_event(event_type, channel, note_id, data0, value0, value1,
                 sample_position):
    global serial
    k = key_of(channel, note_id, data0)
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        old = voices.pop(k, None)
        if old is not None:
            synth.release(old[0])
        if len(voices) >= MAX_VOICES:
            steal_oldest()
        amp = 0.26 + 0.34 * value0
        note = synthio.Note(synthio.midi_to_hz(data0 + value1),
                            waveform=WARM, envelope=env, filter=lp,
                            amplitude=amp)
        serial += 1
        voices[k] = (note, serial)
        synth.press(note)
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        old = voices.pop(k, None)
        if old is not None:
            synth.release(old[0])
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0:
            cutoff.a = logmap(value0, 60.0, 420.0)
        elif data0 == 1:
            verb.mix = 0.05 + 0.3 * value0


# Patch 1 (Program Change 0) is the sound this script's module-level
# defaults describe, so a fresh instance and Patch 1 are the same thing.
# piece.py also reads it: a macro a composition does not set resolves here
# rather than to 0.5. Derived by tools/derive_patches.py - see that file
# before editing these numbers by hand.
PATCHES = {
    0: ("Init", (
        0.435425, 0.233333)),
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
