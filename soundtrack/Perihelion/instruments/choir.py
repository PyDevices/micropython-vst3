# mpvst-macro-labels: Vowel | Space
#
# Choir pad: each voice is three layers - a soft fundamental plus two
# band-pass formant layers around 850 and 1250 Hz, which reads as an "ah"
# vowel. Macro 1 shifts the formant centers (ooh to ah), macro 2 the hall.

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


VOICE = make_table([(n, 1.0 / (n ** 1.1)) for n in range(1, 15)])

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
formant1 = synthio.Math(synthio.MathOperation.SUM, 850.0, 0.0, 0.0)
formant2 = synthio.Math(synthio.MathOperation.SUM, 1250.0, 0.0, 0.0)
bp1 = synthio.Biquad(synthio.FilterMode.BAND_PASS, formant1, Q=4.5)
bp2 = synthio.Biquad(synthio.FilterMode.BAND_PASS, formant2, Q=5.5)
soft = synthio.Biquad(synthio.FilterMode.LOW_PASS, 900.0, Q=0.8)
env = synthio.Envelope(attack_time=0.9, decay_time=0.4, release_time=2.0,
                       attack_level=1.0, sustain_level=0.85)

verb = audiofreeverb.Freeverb(roomsize=0.92, damp=0.4, mix=0.4,
                              sample_rate=SR, channel_count=2,
                              bits_per_sample=16, samples_signed=True,
                              buffer_size=2048)
verb.play(synth)

voices = {}
MAX_VOICES = 4
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
        amp = 0.09 + 0.12 * value0
        vib = synthio.LFO(rate=4.1, scale=0.004,
                          phase_offset=0.37 * (serial % 3))
        base = synthio.Note(hz, waveform=VOICE, envelope=env, filter=soft,
                            amplitude=amp, panning=0.0, bend=vib)
        f1 = synthio.Note(hz, waveform=VOICE, envelope=env, filter=bp1,
                          amplitude=amp * 0.75, panning=-0.35, bend=vib)
        f2 = synthio.Note(hz, waveform=VOICE, envelope=env, filter=bp2,
                          amplitude=amp * 0.55, panning=0.35, bend=vib)
        serial += 1
        voices[k] = ((base, f1, f2), serial)
        synth.press(base)
        synth.press(f1)
        synth.press(f2)
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0:
            shift = 0.7 + 0.7 * value0
            formant1.a = 850.0 * shift
            formant2.a = 1250.0 * shift
        elif data0 == 1:
            verb.mix = 0.15 + 0.4 * value0


# Patch 1 (Program Change 0) is the sound this script's module-level
# defaults describe, so a fresh instance and Patch 1 are the same thing.
# piece.py also reads it: a macro a composition does not set resolves here
# rather than to 0.5. Derived by tools/derive_patches.py - see that file
# before editing these numbers by hand.
PATCHES = {
    0: ("Init", (
        0.429, 0.625)),
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
