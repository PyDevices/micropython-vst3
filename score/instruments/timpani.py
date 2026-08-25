# mpvst-macro-labels: Tone | Space
#
# Timpani: a struck fundamental with a fast downward pitch settle plus a
# filtered noise thump, in a large room. Rolls are just repeated notes.
# Macro 1 opens the strike tone, macro 2 the room.

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


def noise_table(length=8192, seed=987654321):
    out = array.array("h", bytearray(length * 2))
    state = seed
    for i in range(length):
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        out[i] = ((state >> 15) & 0xFFFF) - 32768
    return out


def logmap(v, lo, hi):
    return lo * ((hi / lo) ** v)


DRUM = make_table(((1, 1.0), (1.5, 0.35), (1.98, 0.2), (2.44, 0.1)))
NOISE = noise_table()
NOISE_HZ = SR / 8192.0
FALL = array.array("h", (32767, 0))

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
tone = synthio.Math(synthio.MathOperation.SUM, 420.0, 0.0, 0.0)
tone_lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, tone, Q=1.0)
thump_lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, 240.0, Q=0.9)

strike_env = synthio.Envelope(attack_time=0.002, decay_time=0.9,
                              release_time=0.6, attack_level=1.0,
                              sustain_level=0.0)
thump_env = synthio.Envelope(attack_time=0.001, decay_time=0.09,
                             release_time=0.09, attack_level=1.0,
                             sustain_level=0.0)

verb = audiofreeverb.Freeverb(roomsize=0.92, damp=0.5, mix=0.3,
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
        amp = 0.24 + 0.4 * value0
        settle = synthio.LFO(waveform=FALL, once=True, rate=1.0 / 0.07,
                             scale=0.3, interpolate=True)
        strike = synthio.Note(hz, waveform=DRUM, envelope=strike_env,
                              filter=tone_lp, amplitude=amp, bend=settle,
                              panning=-0.05)
        thump = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=thump_env,
                             filter=thump_lp, amplitude=amp * 0.6,
                             panning=0.05)
        serial += 1
        voices[k] = ((strike, thump), serial)
        synth.press(strike)
        synth.press(thump)
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0:
            tone.a = logmap(value0, 180.0, 950.0)
        elif data0 == 1:
            verb.mix = 0.12 + 0.4 * value0


vstaudio.on_event(handle_event)
vstaudio.output(verb)
