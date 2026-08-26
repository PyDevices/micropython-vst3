# mpvst-macro-labels: Shimmer | Space
#
# Glass halo pad: triangle-ish tone ring-modulated at an inharmonic ratio,
# high-passed so it floats above the mix, with slow tremolo and a very large
# reverb. Macro 1 raises the ring-mod shimmer, macro 2 the room.

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


SOFT = make_table(((1, 1.0), (3, 0.10), (5, 0.035), (7, 0.015)))
SINE = make_table(((1, 1.0),))
RING_RATIO = 3.007

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
hp = synthio.Biquad(synthio.FilterMode.HIGH_PASS, 320.0, Q=0.8)
env = synthio.Envelope(attack_time=1.8, decay_time=0.6, release_time=3.5,
                       attack_level=1.0, sustain_level=0.8)

verb = audiofreeverb.Freeverb(roomsize=0.92, damp=0.3, mix=0.42,
                              sample_rate=SR, channel_count=2,
                              bits_per_sample=16, samples_signed=True,
                              buffer_size=2048)
verb.play(synth)

shimmer = 0.35
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
    global serial, shimmer
    k = key_of(channel, note_id, data0)
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        if len(voices) >= MAX_VOICES:
            steal_oldest()
        hz = synthio.midi_to_hz(data0 + value1)
        amp = 0.10 + 0.13 * value0
        trem = synthio.LFO(rate=0.9, scale=0.12 * amp, offset=amp,
                           phase_offset=0.25 * (serial % 4))
        pure = synthio.Note(hz, waveform=SOFT, envelope=env, filter=hp,
                            amplitude=trem, panning=-0.3)
        glass = synthio.Note(hz, waveform=SOFT, envelope=env, filter=hp,
                             amplitude=amp * shimmer, panning=0.35,
                             ring_frequency=hz * RING_RATIO,
                             ring_waveform=SINE)
        serial += 1
        voices[k] = ((pure, glass), serial)
        synth.press(pure)
        synth.press(glass)
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0:
            shimmer = 0.1 + 0.8 * value0
            for voice in voices.values():
                voice[0][1].amplitude = 0.24 * shimmer
        elif data0 == 1:
            verb.mix = 0.15 + 0.45 * value0


# Patch 1 (Program Change 0) is the sound this script's module-level
# defaults describe, so a fresh instance and Patch 1 are the same thing.
# piece.py also reads it: a macro a composition does not set resolves here
# rather than to 0.5. Derived by tools/derive_patches.py - see that file
# before editing these numbers by hand.
PATCHES = {
    0: ("Init", (
        0.3125, 0.6)),
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
