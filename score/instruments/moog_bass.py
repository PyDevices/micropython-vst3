# mpvst-macro-labels: Cutoff | Resonance | Punch
#
# Ostinato Moog bass: saw plus a sub-octave square through a resonant
# low-pass. Macro 1 sweeps the cutoff, macro 2 the resonance, macro 3 sets
# how hard the per-note filter pluck opens. This is the automation star of
# the score.

import array
import math

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


SAW = make_table([(n, 1.0 / n) for n in range(1, 29)])
SQUARE = make_table([(n, 1.0 / n) for n in range(1, 16, 2)])

# One-shot downward ramp used as the per-note filter pluck.
FALL = array.array("h", (32767, 0))

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
cutoff = synthio.Math(synthio.MathOperation.SUM, 700.0, 0.0, 0.0)
resonance = synthio.Math(synthio.MathOperation.SUM, 1.4, 0.0, 0.0)
punch = 1600.0

env = synthio.Envelope(attack_time=0.006, decay_time=0.18,
                       release_time=0.12, attack_level=1.0,
                       sustain_level=0.55)

voices = {}
MAX_VOICES = 3
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
    global serial, punch
    k = key_of(channel, note_id, data0)
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        if len(voices) >= MAX_VOICES:
            steal_oldest()
        hz = synthio.midi_to_hz(data0 + value1)
        amp = 0.22 + 0.30 * value0
        pluck = synthio.LFO(waveform=FALL, once=True, rate=4.0,
                            scale=punch * (0.4 + 0.6 * value0),
                            interpolate=True)
        freq = synthio.Math(synthio.MathOperation.SUM, cutoff, pluck, 0.0)
        flt = synthio.Biquad(synthio.FilterMode.LOW_PASS, freq, Q=resonance)
        a = synthio.Note(hz, waveform=SAW, envelope=env, filter=flt,
                         amplitude=amp, panning=-0.1, bend=0.001)
        b = synthio.Note(hz * 0.5, waveform=SQUARE, envelope=env, filter=flt,
                         amplitude=amp * 0.8, panning=0.1)
        serial += 1
        voices[k] = ((a, b), serial)
        synth.press(a)
        synth.press(b)
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0:
            cutoff.a = logmap(value0, 90.0, 5200.0)
        elif data0 == 1:
            resonance.a = 0.8 + 6.7 * value0
        elif data0 == 2:
            punch = 3600.0 * value0


vstaudio.on_event(handle_event)
vstaudio.output(synth)
