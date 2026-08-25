# mpvst-macro-labels: Lift | Center | Space
#
# Riser: a cluster of detuned saws plus band-passed noise that climbs as
# macro 1 rises - automate Lift from 0 to 1 across the bars before a drop
# and cut the note at the downbeat. Macro 2 places the noise band, macro 3
# the room.

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


def noise_table(length=8192, seed=246813579):
    out = array.array("h", bytearray(length * 2))
    state = seed
    for i in range(length):
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        out[i] = ((state >> 15) & 0xFFFF) - 32768
    return out


def logmap(v, lo, hi):
    return lo * ((hi / lo) ** v)


SAW = make_table([(n, 1.0 / n) for n in range(1, 19)])
NOISE = noise_table()
NOISE_HZ = SR / 8192.0

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
# Lift raises the cluster by up to an octave and swells its level.
lift_bend = synthio.Math(synthio.MathOperation.SUM, 0.0, 0.0, 0.0)
wobble = synthio.LFO(rate=6.5, scale=0.012)
bend_total = synthio.Math(synthio.MathOperation.SUM, lift_bend, wobble, 0.0)
center = synthio.Math(synthio.MathOperation.SUM, 1800.0, 0.0, 0.0)
noise_bp = synthio.Biquad(synthio.FilterMode.BAND_PASS, center, Q=1.8)
cluster_lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, 2600.0, Q=1.1)

env = synthio.Envelope(attack_time=1.6, decay_time=0.4, release_time=0.35,
                       attack_level=1.0, sustain_level=1.0)

verb = audiofreeverb.Freeverb(roomsize=0.9, damp=0.35, mix=0.3,
                              sample_rate=SR, channel_count=2,
                              bits_per_sample=16, samples_signed=True,
                              buffer_size=2048)
verb.play(synth)

DETUNES = (0.995, 1.0, 1.006)
PANS = (-0.4, 0.0, 0.4)
voices = {}
MAX_VOICES = 2
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
        amp = 0.1 + 0.2 * value0
        notes = []
        for i in range(3):
            notes.append(synthio.Note(hz * DETUNES[i], waveform=SAW,
                                      envelope=env, filter=cluster_lp,
                                      amplitude=amp, panning=PANS[i],
                                      bend=bend_total))
        notes.append(synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env,
                                  filter=noise_bp, amplitude=amp * 1.3,
                                  bend=lift_bend))
        serial += 1
        voices[k] = (tuple(notes), serial)
        for note in notes:
            synth.press(note)
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0:
            lift_bend.a = value0
        elif data0 == 1:
            center.a = logmap(value0, 700.0, 6400.0)
        elif data0 == 2:
            verb.mix = 0.12 + 0.4 * value0


vstaudio.on_event(handle_event)
vstaudio.output(verb)
