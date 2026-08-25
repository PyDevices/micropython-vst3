# mpvst-macro-labels: Cutoff | Motion | Space
#
# Analog dawn pad: two detuned saws panned wide through a slowly breathing
# low-pass, chorus, and a large reverb. Macro 1 opens the filter, macro 2
# deepens the internal filter motion, macro 3 pushes the pad into the room.

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


def logmap(v, lo, hi):
    return lo * ((hi / lo) ** v)


WARM_SAW = make_table([(n, 1.0 / (n ** 1.35)) for n in range(1, 19)])
DETUNE = 2.0 ** (8.0 / 1200.0)

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
cut_base = synthio.Math(synthio.MathOperation.SUM, 900.0, 0.0, 0.0)
motion_depth = synthio.Math(synthio.MathOperation.SUM, 260.0, 0.0, 0.0)
breath = synthio.LFO(rate=0.07, scale=motion_depth, phase_offset=0.75)
cut_sum = synthio.Math(synthio.MathOperation.SUM, cut_base, breath, 0.0)
# The breath excursion can exceed a dark cutoff base; a negative filter
# frequency destabilises the biquad, so clamp to the audible band.
cutoff = synthio.Math(synthio.MathOperation.MID, cut_sum, 90.0, 9000.0)
lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, cutoff, Q=1.05)

env = synthio.Envelope(attack_time=1.2, decay_time=0.5, release_time=2.4,
                       attack_level=1.0, sustain_level=0.85)

chorus = audiodelays.Chorus(max_delay_ms=40, delay_ms=17, voices=3, mix=0.35,
                            sample_rate=SR, channel_count=2,
                            bits_per_sample=16, samples_signed=True,
                            buffer_size=2048)
verb = audiofreeverb.Freeverb(roomsize=0.88, damp=0.35, mix=0.3,
                              sample_rate=SR, channel_count=2,
                              bits_per_sample=16, samples_signed=True,
                              buffer_size=2048)
chorus.play(synth)
verb.play(chorus)

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
    global serial
    k = key_of(channel, note_id, data0)
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        if len(voices) >= MAX_VOICES:
            steal_oldest()
        hz = synthio.midi_to_hz(data0 + value1)
        amp = 0.07 + 0.09 * value0
        a = synthio.Note(hz * DETUNE, waveform=WARM_SAW, envelope=env,
                         filter=lp, amplitude=amp, panning=-0.5)
        b = synthio.Note(hz / DETUNE, waveform=WARM_SAW, envelope=env,
                         filter=lp, amplitude=amp, panning=0.5)
        serial += 1
        voices[k] = ((a, b), serial)
        synth.press(a)
        synth.press(b)
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0:
            cut_base.a = logmap(value0, 260.0, 5200.0)
        elif data0 == 1:
            motion_depth.a = 40.0 + 900.0 * value0
        elif data0 == 2:
            verb.mix = 0.1 + 0.4 * value0


vstaudio.on_event(handle_event)
vstaudio.output(verb)
