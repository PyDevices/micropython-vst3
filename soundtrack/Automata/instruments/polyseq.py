# mpvst-macro-labels: Cutoff | Resonance | Echo
#
# Sequenced polysynth: a hollow squarish pluck with a per-note filter
# snap and a tempo-synced echo at three eighths - the engine of the 7/8
# movement. Notes alternate across the stereo field. Macros: cutoff,
# resonance, echo send.

import array
import math

import audiodelays
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


HOLLOW = make_table([(n, 1.0 / n) for n in range(1, 14, 2)] +
                    [(2, 0.22), (4, 0.1)])
FALL = array.array("h", (32767, 0))
DETUNE = 2.0 ** (6.0 / 1200.0)

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
cutoff = synthio.Math(synthio.MathOperation.SUM, 1500.0, 0.0, 0.0)
resonance = synthio.Math(synthio.MathOperation.SUM, 2.2, 0.0, 0.0)
env = synthio.Envelope(attack_time=0.004, decay_time=0.16,
                       release_time=0.2, attack_level=1.0,
                       sustain_level=0.25)

echo = audiodelays.Echo(max_delay_ms=1200, delay_ms=800, decay=0.42,
                        mix=0.3, sample_rate=SR, channel_count=2,
                        bits_per_sample=16, samples_signed=True,
                        buffer_size=2048, freq_shift=False)
echo.play(synth)

PAN = (-0.4, 0.25, -0.15, 0.4, 0.0, -0.3, 0.35)

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
    global serial
    k = key_of(channel, note_id, data0)
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        if len(voices) >= MAX_VOICES:
            steal_oldest()
        bpm, _ = beat_clock()
        want = 60000.0 / bpm * 1.5
        if abs(echo.delay_ms - want) > 4.0:
            echo.delay_ms = want
        hz = synthio.midi_to_hz(data0 + value1)
        amp = 0.2 + 0.34 * value0
        snap = synthio.LFO(waveform=FALL, once=True, rate=1.0 / 0.1,
                           scale=500.0 + 1100.0 * value0, interpolate=True)
        freq = synthio.Math(synthio.MathOperation.SUM, cutoff, snap, 0.0)
        flt = synthio.Biquad(synthio.FilterMode.LOW_PASS, freq, Q=resonance)
        note = synthio.Note(hz * DETUNE, waveform=HOLLOW, envelope=env,
                            filter=flt, amplitude=amp,
                            panning=PAN[serial % 7])
        serial += 1
        voices[k] = ((note,), serial)
        synth.press(note)
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0:
            cutoff.a = logmap(value0, 320.0, 7200.0)
        elif data0 == 1:
            resonance.a = 0.8 + 5.8 * value0
        elif data0 == 2:
            echo.mix = 0.5 * value0


# Patch 1 (Program Change 0) is the sound this script's module-level
# defaults describe, so a fresh instance and Patch 1 are the same thing.
# piece.py also reads it: a macro a composition does not set resolves here
# rather than to 0.5. Derived by tools/derive_patches.py - see that file
# before editing these numbers by hand.
PATCHES = {
    0: ("Init", (
        0.496191, 0.241379, 0.6)),
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

vstaudio.output(echo)
