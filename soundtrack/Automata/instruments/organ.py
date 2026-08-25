# mpvst-macro-labels: Drawbars | Space
#
# Organ: an additive drawbar waveform (partials 1,2,3,4,6,8) that speaks
# instantly and holds forever, slightly chorused. The harmonic floor of
# the climax. Macro 1 darkens or opens the upper drawbars via the
# low-pass, macro 2 the room.

import array
import math

import audiodelays
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


def beat_clock():
    info = vstaudio.transport()
    bpm = info[2] if info[2] and info[2] > 1.0 else 120.0
    return bpm, info[1] * bpm / 60.0


DRAWBARS = make_table(((1, 1.0), (2, 0.85), (3, 0.5), (4, 0.4),
                       (6, 0.18), (8, 0.12)))

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
cutoff = synthio.Math(synthio.MathOperation.SUM, 1800.0, 0.0, 0.0)
lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, cutoff, Q=0.75)
env = synthio.Envelope(attack_time=0.03, decay_time=0.05,
                       release_time=0.12, attack_level=1.0,
                       sustain_level=1.0)

chorus = audiodelays.Chorus(max_delay_ms=30, delay_ms=11, voices=2,
                            mix=0.25, sample_rate=SR, channel_count=2,
                            bits_per_sample=16, samples_signed=True,
                            buffer_size=2048)
verb = audiofreeverb.Freeverb(roomsize=0.8, damp=0.5, mix=0.2,
                              sample_rate=SR, channel_count=2,
                              bits_per_sample=16, samples_signed=True,
                              buffer_size=2048)
chorus.play(synth)
verb.play(chorus)

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
        amp = 0.16 + 0.22 * value0
        note = synthio.Note(hz, waveform=DRAWBARS, envelope=env,
                            filter=lp, amplitude=amp)
        serial += 1
        voices[k] = ((note,), serial)
        synth.press(note)
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0:
            cutoff.a = logmap(value0, 700.0, 4200.0)
        elif data0 == 1:
            verb.mix = 0.35 * value0


vstaudio.on_event(handle_event)
vstaudio.output(verb)
