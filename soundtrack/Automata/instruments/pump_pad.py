# mpvst-macro-labels: Cutoff | Pump | Space
#
# Sidechain-pumping pad: warm detuned saws whose amplitude ducks on
# every beat. The pump LFO reads vstaudio.transport() at note-on for the
# exact tempo and beat phase, so the duck locks to the kick with no
# manual sync. Macro 1 opens the filter, macro 2 sets pump depth, macro 3
# the hall.

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


def beat_clock():
    info = vstaudio.transport()
    bpm = info[2] if info[2] and info[2] > 1.0 else 120.0
    return bpm, info[1] * bpm / 60.0


SAW = make_table([(n, 1.0 / (n ** 1.25)) for n in range(1, 19)])
DETUNE = 2.0 ** (7.0 / 1200.0)

# One cycle of the duck: hard dip right after the beat, exponential-ish
# recovery to full level. 0..32767 so scale/offset shape it linearly.
PUMP = array.array("h", bytearray(256 * 2))
for i in range(256):
    x = i / 255.0
    PUMP[i] = int(32767 * (0.06 + 0.94 * (x ** 0.6)))

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
cutoff = synthio.Math(synthio.MathOperation.SUM, 1400.0, 0.0, 0.0)
lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, cutoff, Q=1.0)
depth = synthio.Math(synthio.MathOperation.SUM, 0.8, 0.0, 0.0)
rest = synthio.Math(synthio.MathOperation.SUM, 0.2, 0.0, 0.0)
env = synthio.Envelope(attack_time=0.03, decay_time=0.3,
                       release_time=0.5, attack_level=1.0,
                       sustain_level=0.9)

verb = audiofreeverb.Freeverb(roomsize=0.88, damp=0.4, mix=0.26,
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

MAX_VOICES = 4


def handle_event(event_type, channel, note_id, data0, value0, value1,
                 sample_position):
    global serial
    k = key_of(channel, note_id, data0)
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        if len(voices) >= MAX_VOICES:
            steal_oldest()
        bpm, beats = beat_clock()
        hz = synthio.midi_to_hz(data0 + value1)
        amp = 0.1 + 0.13 * value0
        pump = synthio.LFO(waveform=PUMP, rate=bpm / 60.0,
                           scale=depth, offset=rest,
                           phase_offset=beats % 1.0, interpolate=True)
        vol_a = synthio.Math(synthio.MathOperation.PRODUCT, pump, amp, 1.0)
        vol_b = synthio.Math(synthio.MathOperation.PRODUCT, pump, amp, 1.0)
        a = synthio.Note(hz * DETUNE, waveform=SAW, envelope=env,
                         filter=lp, amplitude=vol_a, panning=-0.4)
        b = synthio.Note(hz / DETUNE, waveform=SAW, envelope=env,
                         filter=lp, amplitude=vol_b, panning=0.4)
        serial += 1
        voices[k] = ((a, b), serial)
        synth.press(a)
        synth.press(b)
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0:
            cutoff.a = logmap(value0, 380.0, 6800.0)
        elif data0 == 1:
            depth.a = 0.95 * value0
            rest.a = 1.0 - 0.95 * value0
        elif data0 == 2:
            verb.mix = 0.1 + 0.4 * value0


# Patch 1 (Program Change 0) is the sound this script's module-level
# defaults describe, so a fresh instance and Patch 1 are the same thing.
# piece.py also reads it: a macro a composition does not set resolves here
# rather than to 0.5. Derived by tools/derive_patches.py - see that file
# before editing these numbers by hand.
PATCHES = {
    0: ("Init", (
        0.45209, 0.842, 0.4)),
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
