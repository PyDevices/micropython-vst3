# mpvst-macro-labels: Tone | Room
#
# Toms: pitched drum voices - sine body with a settle, a skin-noise
# transient - panned across the kit by MIDI pitch. Macro 1 opens the
# body tone, macro 2 the room.

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


BODY = make_table(((1, 1.0), (1.5, 0.3), (2.1, 0.12)))
NOISE = noise_table(seed=1029384756)
NOISE_HZ = SR / 8192.0
FALL = array.array("h", (32767, 0))

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
tone = synthio.Math(synthio.MathOperation.SUM, 600.0, 0.0, 0.0)
body_lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, tone, Q=0.9)
skin_bp = synthio.Biquad(synthio.FilterMode.BAND_PASS, 900.0, Q=0.8)

body_env = synthio.Envelope(attack_time=0.002, decay_time=0.42,
                            release_time=0.2, attack_level=1.0,
                            sustain_level=0.0)
skin_env = synthio.Envelope(attack_time=0.001, decay_time=0.045,
                            release_time=0.03, attack_level=1.0,
                            sustain_level=0.0)

verb = audiofreeverb.Freeverb(roomsize=0.85, damp=0.5, mix=0.22,
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
        hz = synthio.midi_to_hz(data0 + value1)
        amp = 0.28 + 0.45 * value0
        pan = max(-0.5, min(0.5, (data0 - 47) * 0.12))
        settle = synthio.LFO(waveform=FALL, once=True, rate=1.0 / 0.09,
                             scale=0.35, interpolate=True)
        body = synthio.Note(hz, waveform=BODY, envelope=body_env,
                            filter=body_lp, amplitude=amp, bend=settle,
                            panning=pan)
        skin = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=skin_env,
                            filter=skin_bp, amplitude=amp * 0.5,
                            panning=pan)
        serial += 1
        voices[k] = ((body, skin), serial)
        synth.press(body)
        synth.press(skin)
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0:
            tone.a = logmap(value0, 260.0, 1300.0)
        elif data0 == 1:
            verb.mix = 0.4 * value0


vstaudio.on_event(handle_event)
vstaudio.output(verb)
