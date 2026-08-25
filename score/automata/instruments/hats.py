# mpvst-macro-labels: Tone
#
# Hi-hats: high-passed noise. Pitch 42 is the closed hat, 46 the open hat,
# and a closed hit chokes any ringing open one, like a real pair of
# cymbals on a rod. Macro 1 moves the high-pass corner.

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


NOISE = noise_table(seed=13571357)
NOISE_HZ = SR / 8192.0

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
corner = synthio.Math(synthio.MathOperation.SUM, 8200.0, 0.0, 0.0)
hp = synthio.Biquad(synthio.FilterMode.HIGH_PASS, corner, Q=0.8)

closed_env = synthio.Envelope(attack_time=0.001, decay_time=0.035,
                              release_time=0.02, attack_level=1.0,
                              sustain_level=0.0)
open_env = synthio.Envelope(attack_time=0.001, decay_time=0.32,
                            release_time=0.05, attack_level=1.0,
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

MAX_VOICES = 4
open_keys = []


def handle_event(event_type, channel, note_id, data0, value0, value1,
                 sample_position):
    global serial
    k = key_of(channel, note_id, data0)
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        if len(voices) >= MAX_VOICES:
            steal_oldest()
        is_open = data0 >= 45
        if not is_open:
            while open_keys:
                release_voice(open_keys.pop())
        amp = (0.2 + 0.5 * value0) * (0.9 if is_open else 1.0)
        env = open_env if is_open else closed_env
        note = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env,
                            filter=hp, amplitude=amp, panning=0.12)
        serial += 1
        voices[k] = ((note,), serial)
        if is_open:
            open_keys.append(k)
        synth.press(note)
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
        if k in open_keys:
            open_keys.remove(k)
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0:
            corner.a = logmap(value0, 6200.0, 11500.0)


vstaudio.on_event(handle_event)
vstaudio.output(synth)
