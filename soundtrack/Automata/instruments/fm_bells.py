# mpvst-macro-labels: Color | Space
#
# FM-flavored bells: a pure carrier blended with a ring-modulated
# partner at an inharmonic 3.51 ratio - velocity leans the blend toward
# the bright layer, like striking harder on a DX tine. Chorus and a long
# hall. Macro 1 tunes the ratio, macro 2 the hall.

import array
import math

import audiodelays
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


def beat_clock():
    info = vstaudio.transport()
    bpm = info[2] if info[2] and info[2] > 1.0 else 120.0
    return bpm, info[1] * bpm / 60.0


SINE = make_table(((1, 1.0),))
ratio = 3.51

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
strike_env = synthio.Envelope(attack_time=0.002, decay_time=1.6,
                              release_time=2.5, attack_level=1.0,
                              sustain_level=0.15)

chorus = audiodelays.Chorus(max_delay_ms=30, delay_ms=14, voices=3,
                            mix=0.3, sample_rate=SR, channel_count=2,
                            bits_per_sample=16, samples_signed=True,
                            buffer_size=2048)
verb = audiofreeverb.Freeverb(roomsize=0.9, damp=0.3, mix=0.38,
                              sample_rate=SR, channel_count=2,
                              bits_per_sample=16, samples_signed=True,
                              buffer_size=2048)
chorus.play(synth)
verb.play(chorus)

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

MAX_VOICES = 5


def handle_event(event_type, channel, note_id, data0, value0, value1,
                 sample_position):
    global serial, ratio
    k = key_of(channel, note_id, data0)
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        if len(voices) >= MAX_VOICES:
            steal_oldest()
        hz = synthio.midi_to_hz(data0 + value1)
        amp = 0.16 + 0.26 * value0
        pan = 0.25 - 0.25 * (serial % 3)
        pure = synthio.Note(hz, waveform=SINE, envelope=strike_env,
                            amplitude=amp * (1.0 - 0.45 * value0),
                            panning=pan)
        bright = synthio.Note(hz, waveform=SINE, envelope=strike_env,
                              amplitude=amp * (0.35 + 0.6 * value0),
                              panning=-pan, ring_frequency=hz * ratio,
                              ring_waveform=SINE, ring_bend=0.0001)
        serial += 1
        voices[k] = ((pure, bright), serial)
        synth.press(pure)
        synth.press(bright)
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0:
            ratio = 2.9 + 1.4 * value0
        elif data0 == 1:
            verb.mix = 0.15 + 0.4 * value0


# Patch 1 (Program Change 0) is the sound this script's module-level
# defaults describe, so a fresh instance and Patch 1 are the same thing.
# piece.py also reads it: a macro a composition does not set resolves here
# rather than to 0.5. Derived by tools/derive_patches.py - see that file
# before editing these numbers by hand.
PATCHES = {
    0: ("Init", (
        0.435714, 0.575)),
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
