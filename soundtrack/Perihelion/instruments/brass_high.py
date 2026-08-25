# mpvst-macro-labels: Brightness | Space
#
# Trumpet section: bright saw pair with a fast filter bloom and a shorter
# room. Carries the climax theme. Macro 1 is brightness, macro 2 the room.

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


def logmap(v, lo, hi):
    return lo * ((hi / lo) ** v)


BRASS = make_table([(n, 1.0 / (n ** 0.9)) for n in range(1, 31)])
DETUNE = 2.0 ** (3.5 / 1200.0)
RISE = array.array("h", (0, 32767))

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
brightness = 3200.0
env = synthio.Envelope(attack_time=0.05, decay_time=0.15, release_time=0.5,
                       attack_level=1.0, sustain_level=0.9)

verb = audiofreeverb.Freeverb(roomsize=0.82, damp=0.4, mix=0.22,
                              sample_rate=SR, channel_count=2,
                              bits_per_sample=16, samples_signed=True,
                              buffer_size=2048)
verb.play(synth)

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
    global serial, brightness
    k = key_of(channel, note_id, data0)
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        if len(voices) >= MAX_VOICES:
            steal_oldest()
        hz = synthio.midi_to_hz(data0 + value1)
        amp = 0.16 + 0.3 * value0
        opener = synthio.LFO(waveform=RISE, once=True, rate=1.0 / 0.15,
                             scale=brightness * (0.5 + 0.5 * value0),
                             interpolate=True)
        freq = synthio.Math(synthio.MathOperation.SUM, 550.0, opener, 0.0)
        flt = synthio.Biquad(synthio.FilterMode.LOW_PASS, freq, Q=1.15)
        a = synthio.Note(hz * DETUNE, waveform=BRASS, envelope=env,
                         filter=flt, amplitude=amp, panning=0.22)
        b = synthio.Note(hz / DETUNE, waveform=BRASS, envelope=env,
                         filter=flt, amplitude=amp, panning=-0.18)
        serial += 1
        voices[k] = ((a, b), serial)
        synth.press(a)
        synth.press(b)
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0:
            brightness = logmap(value0, 850.0, 7200.0)
        elif data0 == 1:
            verb.mix = 0.1 + 0.35 * value0


vstaudio.on_event(handle_event)
vstaudio.output(verb)
