# mpvst-macro-labels: Cutoff | Resonance | Echo
#
# Pulse sequencer: plucked square/saw hybrid with a small per-note filter
# snap and a dotted-eighth echo, notes alternating left and right. The
# rising-cutoff arpeggio is the classic analog build device: automate
# macro 1 upward across a section. Macro 2 is resonance, macro 3 the echo.

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


def logmap(v, lo, hi):
    return lo * ((hi / lo) ** v)


PLUCK = make_table([(n, 1.0 / n) for n in range(1, 12, 2)] +
                   [(n, 0.5 / n) for n in range(2, 17, 2)])
FALL = array.array("h", (32767, 0))

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
cutoff = synthio.Math(synthio.MathOperation.SUM, 1200.0, 0.0, 0.0)
resonance = synthio.Math(synthio.MathOperation.SUM, 1.8, 0.0, 0.0)
env = synthio.Envelope(attack_time=0.004, decay_time=0.14,
                       release_time=0.18, attack_level=1.0,
                       sustain_level=0.2)

echo = audiodelays.Echo(max_delay_ms=700, delay_ms=346, decay=0.4,
                        mix=0.28, sample_rate=SR, channel_count=2,
                        bits_per_sample=16, samples_signed=True,
                        buffer_size=2048)
echo.play(synth)

voices = {}
MAX_VOICES = 5
serial = 0
PAN = (-0.35, 0.2, 0.35, -0.2)


def key_of(channel, note_id, pitch):
    return (channel, note_id if note_id >= 0 else pitch)


def release_voice(k):
    voice = voices.pop(k, None)
    if voice is not None:
        synth.release(voice[0])


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
        amp = 0.22 + 0.4 * value0
        snap = synthio.LFO(waveform=FALL, once=True, rate=1.0 / 0.11,
                           scale=600.0 + 900.0 * value0, interpolate=True)
        freq = synthio.Math(synthio.MathOperation.SUM, cutoff, snap, 0.0)
        flt = synthio.Biquad(synthio.FilterMode.LOW_PASS, freq, Q=resonance)
        note = synthio.Note(hz, waveform=PLUCK, envelope=env, filter=flt,
                            amplitude=amp, panning=PAN[serial % 4])
        serial += 1
        voices[k] = (note, serial)
        synth.press(note)
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0:
            cutoff.a = logmap(value0, 260.0, 7600.0)
        elif data0 == 1:
            resonance.a = 0.8 + 5.7 * value0
        elif data0 == 2:
            echo.mix = 0.5 * value0


vstaudio.on_event(handle_event)
vstaudio.output(echo)
