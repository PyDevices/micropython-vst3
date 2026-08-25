# mpvst-macro-labels: Cutoff | Echo
#
# Fast arpeggio synth: a bright saw-plus-octave pluck with a filter
# snap, ping-ponging across the field, with a light tempo-synced echo.
# Macros: cutoff, echo send.

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


BRIGHT = make_table([(n, 1.0 / n) for n in range(1, 21)] +
                    [(2, 0.5)])
FALL = array.array("h", (32767, 0))

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
cutoff = synthio.Math(synthio.MathOperation.SUM, 2600.0, 0.0, 0.0)
env = synthio.Envelope(attack_time=0.003, decay_time=0.09,
                       release_time=0.1, attack_level=1.0,
                       sustain_level=0.15)

echo = audiodelays.Echo(max_delay_ms=800, delay_ms=250, decay=0.35,
                        mix=0.16, sample_rate=SR, channel_count=2,
                        bits_per_sample=16, samples_signed=True,
                        buffer_size=2048, freq_shift=False)
echo.play(synth)

PAN = (-0.45, 0.15, 0.45, -0.15)

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
        want = 60000.0 / bpm * 0.75
        if abs(echo.delay_ms - want) > 4.0:
            echo.delay_ms = want
        hz = synthio.midi_to_hz(data0 + value1)
        amp = 0.18 + 0.32 * value0
        snap = synthio.LFO(waveform=FALL, once=True, rate=1.0 / 0.08,
                           scale=700.0 + 900.0 * value0, interpolate=True)
        freq = synthio.Math(synthio.MathOperation.SUM, cutoff, snap, 0.0)
        flt = synthio.Biquad(synthio.FilterMode.LOW_PASS, freq, Q=1.7)
        note = synthio.Note(hz, waveform=BRIGHT, envelope=env,
                            filter=flt, amplitude=amp,
                            panning=PAN[serial % 4])
        serial += 1
        voices[k] = ((note,), serial)
        synth.press(note)
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0:
            cutoff.a = logmap(value0, 500.0, 9000.0)
        elif data0 == 1:
            echo.mix = 0.4 * value0


vstaudio.on_event(handle_event)
vstaudio.output(echo)
