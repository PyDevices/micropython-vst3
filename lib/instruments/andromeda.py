# mpvst-macro-labels: Volume | Filter 1 Cutoff | Filter 2 Cutoff | Filter Mix | Resonance 1 | Resonance 2 | Env 1 -> F1 | Env 1 -> F2 | Unison Detune | Amp Attack | Amp Decay | Amp Sustain | Amp Release | Filter Attack | Filter Decay | Master Tune

import array
import math

import synthio
import vstaudio

try:
    from ulab import numpy as np
except ImportError:
    np = None

SR = vstaudio.sample_rate()
TAU = 2.0 * math.pi

def make_table(parts, length=2048, gain=32000):
    # Additive-harmonic tables (up to ~40 partials) are a real hot spot for the plain-Python
    # nested loop; use ulab when it's available (real engine) and fall back to it when not
    # (desktop test harness).
    if np is not None:
        idx = np.arange(length)
        acc = np.zeros(length)
        for mult, amp in parts:
            acc = acc + amp * np.sin(idx * (TAU * mult / length))
        peak = np.max(acc * acc) ** 0.5
        if peak <= 0.0:
            peak = 1.0
        scaled = acc * (gain / peak)
        return array.array("h", [int(v) for v in scaled])
    vals = [0.0] * length
    for mult, amp in parts:
        step = TAU * mult / length
        for i in range(length):
            vals[i] += amp * math.sin(step * i)
    peak = max(abs(v) for v in vals) if vals else 0.0
    if peak <= 0.0:
        peak = 1.0
    out = array.array("h", bytearray(length * 2))
    scale = gain / peak
    for i in range(length):
        out[i] = int(vals[i] * scale)
    return out

SAW = make_table([(n, 1.0 / n) for n in range(1, 40)])
SQUARE = make_table([(n, 1.0 / n) for n in range(1, 40, 2)])
def env_shape_table(attack, decay, sustain, length=96):
    # One-shot LFO waveform: ramps 0 -> peak over the attack fraction, then
    # peak -> sustain over the decay fraction, holding sustain afterwards
    # (once=True freezes at the table's last sample).
    total = attack + decay
    n_a = 1 if total <= 0.0 else int(length * attack / total)
    if n_a < 1:
        n_a = 1
    if n_a > length - 1:
        n_a = length - 1
    sustain_level = int(32767 * sustain)
    out = array.array("h", bytearray(length * 2))
    for i in range(n_a):
        out[i] = int(32767 * (i + 1) / n_a)
    span = length - n_a
    for i in range(span):
        out[n_a + i] = int(32767 + (sustain_level - 32767) * (i + 1) / span)
    return out


synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
vstaudio.output(synth)

# Macros
volume = 0.8
f1_cutoff = 2000.0
f2_cutoff = 3000.0
f_mix = 0.5
res1 = 1.0
res2 = 1.0
env_to_f1 = 2000.0
env_to_f2 = 1000.0
unison_detune = 0.0
a_a = 0.01
a_d = 0.3
a_s = 0.5
a_r = 0.3
f_a = 0.01
f_d = 0.3
master_tune = 1.0

voices = {}
serial = 0
MAX_VOICES = 16

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

def handle_event(event_type, channel, note_id, data0, value0, value1, sample_position):
    global volume, f1_cutoff, f2_cutoff, f_mix, res1, res2, env_to_f1, env_to_f2
    global unison_detune, a_a, a_d, a_s, a_r, f_a, f_d, master_tune
    global serial
    
    k = key_of(channel, note_id, data0)
    
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        if len(voices) >= MAX_VOICES:
            steal_oldest()
            
        hz = synthio.midi_to_hz(data0 + value1) * master_tune
        amp = volume * value0
        
        env = synthio.Envelope(attack_time=a_a, decay_time=a_d, release_time=a_r, attack_level=1.0, sustain_level=a_s)
        
        env_tbl = env_shape_table(f_a, f_d, 0.0)
        f_sweep = synthio.LFO(waveform=env_tbl, once=True, rate=1.0/max(0.01, f_a + f_d), scale=1.0, interpolate=True)
        
        c1 = synthio.Math(synthio.MathOperation.SUM, f1_cutoff, synthio.Math(synthio.MathOperation.SCALE_OFFSET, f_sweep, env_to_f1, 0.0), 0.0)
        c2 = synthio.Math(synthio.MathOperation.SUM, f2_cutoff, synthio.Math(synthio.MathOperation.SCALE_OFFSET, f_sweep, env_to_f2, 0.0), 0.0)
        
        # Filter 1: Moog-style Low Pass
        lp1 = synthio.Biquad(synthio.FilterMode.LOW_PASS, c1, Q=res1)
        # Filter 2: SEM-style High Pass (or Multi, but we'll use HP for contrast)
        hp2 = synthio.Biquad(synthio.FilterMode.HIGH_PASS, c2, Q=res2)
        
        notes = []
        if unison_detune > 0.01:
            for i, detune in enumerate([-unison_detune, 0.0, unison_detune]):
                pan = [-0.5, 0.0, 0.5][i]
                n1 = synthio.Note(hz * (1.0 + detune * 0.012), waveform=SAW, envelope=env, filter=lp1, amplitude=amp * (1.0 - f_mix) * 0.3, panning=pan)
                n2 = synthio.Note(hz * (1.0 + detune * 0.012), waveform=SQUARE, envelope=env, filter=hp2, amplitude=amp * f_mix * 0.3, panning=pan)
                notes.extend([n1, n2])
        else:
            n1 = synthio.Note(hz, waveform=SAW, envelope=env, filter=lp1, amplitude=amp * (1.0 - f_mix))
            n2 = synthio.Note(hz * 1.002, waveform=SQUARE, envelope=env, filter=hp2, amplitude=amp * f_mix)
            notes.extend([n1, n2])
            
        serial += 1
        voices[k] = (tuple(notes), serial)
        for n in notes:
            synth.press(n)
            
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
        
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0: volume = value0
        elif data0 == 1: f1_cutoff = 50.0 * (100.0 ** value0)
        elif data0 == 2: f2_cutoff = 50.0 * (100.0 ** value0)
        elif data0 == 3: f_mix = value0
        elif data0 == 4: res1 = 0.5 + value0 * 3.5
        elif data0 == 5: res2 = 0.5 + value0 * 3.5
        elif data0 == 6: env_to_f1 = value0 * 8000.0
        elif data0 == 7: env_to_f2 = value0 * 8000.0
        elif data0 == 8: unison_detune = value0
        elif data0 == 9: a_a = 0.001 + value0 * 2.0
        elif data0 == 10: a_d = 0.05 + value0 * 3.0
        elif data0 == 11: a_s = value0
        elif data0 == 12: a_r = 0.01 + value0 * 4.0
        elif data0 == 13: f_a = 0.001 + value0 * 2.0
        elif data0 == 14: f_d = 0.05 + value0 * 3.0
        elif data0 == 15: master_tune = 0.95 + value0 * 0.1

vstaudio.on_event(handle_event)
