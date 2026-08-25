# mpvst-macro-labels: Color
#
# Shaker: a short band-passed noise chick. Groove comes entirely from
# velocity accents in the pattern. Macro 1 moves the band.

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


def noise_table(length=8192, seed=1234567):
    out = array.array("h", bytearray(length * 2))
    state = seed
    for i in range(length):
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        out[i] = ((state >> 15) & 0xFFFF) - 32768
    return out


def logmap(v, lo, hi):
    return lo * ((hi / lo) ** v)


NOISE = noise_table(seed=1111999)
NOISE_HZ = SR / 8192.0

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
color = synthio.Math(synthio.MathOperation.SUM, 6400.0, 0.0, 0.0)
bp = synthio.Biquad(synthio.FilterMode.BAND_PASS, color, Q=1.0)
env = synthio.Envelope(attack_time=0.012, decay_time=0.05,
                       release_time=0.03, attack_level=1.0,
                       sustain_level=0.0)

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

MAX_VOICES = 3


def handle_event(event_type, channel, note_id, data0, value0, value1,
                 sample_position):
    global serial
    k = key_of(channel, note_id, data0)
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        if len(voices) >= MAX_VOICES:
            steal_oldest()
        amp = 0.12 + 0.4 * value0
        note = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env,
                            filter=bp, amplitude=amp, panning=-0.2)
        serial += 1
        voices[k] = ((note,), serial)
        synth.press(note)
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0:
            color.a = logmap(value0, 4200.0, 9000.0)


vstaudio.on_event(handle_event)
vstaudio.output(synth)
