# mpvst-macro-labels: Brightness | Space
#
# Low string ensemble: three saws per voice (detuned pair panned wide plus a
# center octave-down layer), gentle per-voice vibrato, ensemble low-pass,
# concert-hall reverb. Macro 1 is section brightness, macro 2 the hall.

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


STRING = make_table([(n, 1.0 / n) for n in range(1, 21)])
DETUNE = 2.0 ** (5.0 / 1200.0)

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
cutoff = synthio.Math(synthio.MathOperation.SUM, 1100.0, 0.0, 0.0)
lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, cutoff, Q=0.85)
env = synthio.Envelope(attack_time=0.4, decay_time=0.3, release_time=1.4,
                       attack_level=1.0, sustain_level=0.85)

verb = audiofreeverb.Freeverb(roomsize=0.9, damp=0.5, mix=0.28,
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
        amp = 0.09 + 0.13 * value0
        vib = synthio.LFO(rate=4.4 + 0.15 * (serial % 3), scale=0.0055,
                          phase_offset=0.33 * (serial % 3))
        a = synthio.Note(hz * DETUNE, waveform=STRING, envelope=env,
                         filter=lp, amplitude=amp, panning=-0.4, bend=vib)
        b = synthio.Note(hz / DETUNE, waveform=STRING, envelope=env,
                         filter=lp, amplitude=amp, panning=0.4, bend=vib)
        low = synthio.Note(hz * 0.5, waveform=STRING, envelope=env,
                           filter=lp, amplitude=amp * 0.55, panning=0.0)
        serial += 1
        voices[k] = ((a, b, low), serial)
        synth.press(a)
        synth.press(b)
        synth.press(low)
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0:
            cutoff.a = logmap(value0, 380.0, 3200.0)
        elif data0 == 1:
            verb.mix = 0.12 + 0.38 * value0


vstaudio.on_event(handle_event)
vstaudio.output(verb)
