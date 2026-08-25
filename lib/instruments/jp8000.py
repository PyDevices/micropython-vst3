# mpvst-macro-labels: Volume | Cutoff | Resonance | Supersaw Detune | Supersaw Mix | Env Depth | Chorus | Amp Attack | Amp Decay | Amp Sustain | Amp Release | Filter Attack | Filter Decay | Filter Sustain | HPF Cutoff | Master Tune

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
cutoff_base = 2500.0
resonance = 1.0
supersaw_detune = 0.2
supersaw_mix = 0.8
env_depth = 4000.0
chorus = 0.0

a_a = 0.01
a_d = 0.3
a_s = 0.5
a_r = 0.3
f_a = 0.01
f_d = 0.3
f_s = 0.5
hpf = 20.0
master_tune = 1.0

voices = {}
serial = 0
MAX_VOICES = 8

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
    global volume, cutoff_base, resonance, supersaw_detune, supersaw_mix, env_depth, chorus
    global a_a, a_d, a_s, a_r, f_a, f_d, f_s, hpf, master_tune
    global serial
    
    k = key_of(channel, note_id, data0)
    
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        if len(voices) >= MAX_VOICES:
            steal_oldest()
            
        hz = synthio.midi_to_hz(data0 + value1) * master_tune
        amp = volume * value0
        
        env = synthio.Envelope(attack_time=a_a, decay_time=a_d, release_time=a_r, attack_level=1.0, sustain_level=a_s)
        
        env_tbl = env_shape_table(f_a, f_d, f_s)
        f_sweep = synthio.LFO(waveform=env_tbl, once=True, rate=1.0/max(0.01, f_a + f_d), scale=env_depth, interpolate=True)
        cutoff = synthio.Math(synthio.MathOperation.SUM, cutoff_base, f_sweep, 0.0)
        
        lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, cutoff, Q=resonance)
        # The JP-8000's HPF sits before the resonant VCF in series; synthio only allows one
        # filter per Note, so approximate it by high-passing the two outermost detuned saws
        # (thinning their low end as cutoff rises) while the rest keep the full swept VCF.
        hp = synthio.Biquad(synthio.FilterMode.HIGH_PASS, hpf, Q=0.7)

        notes = []

        # 7-Saw Supersaw
        # 1 center, 3 detuned up, 3 detuned down
        detunes = [
            0.0,
            supersaw_detune * 0.02,
            -supersaw_detune * 0.02,
            supersaw_detune * 0.04,
            -supersaw_detune * 0.04,
            supersaw_detune * 0.06,
            -supersaw_detune * 0.06
        ]
        pans = [0.0, 0.3, -0.3, 0.6, -0.6, 0.9, -0.9]
        
        base_a = amp * (1.0 / 7.0) * supersaw_mix * 2.0
        
        for i in range(7):
            d = detunes[i]
            p = pans[i] * (0.5 + chorus * 0.5)
            note_filter = hp if i >= 5 else lp
            n = synthio.Note(hz * (1.0 + d), waveform=SAW, envelope=env, filter=note_filter, amplitude=base_a, panning=p)
            notes.append(n)
            
        serial += 1
        voices[k] = (tuple(notes), serial)
        for n in notes:
            synth.press(n)
            
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
        
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0: volume = value0
        elif data0 == 1: cutoff_base = 50.0 * (100.0 ** value0)
        elif data0 == 2: resonance = 0.5 + value0 * 3.5
        elif data0 == 3: supersaw_detune = value0
        elif data0 == 4: supersaw_mix = value0
        elif data0 == 5: env_depth = value0 * 8000.0
        elif data0 == 6: chorus = value0
        elif data0 == 7: a_a = 0.001 + value0 * 2.0
        elif data0 == 8: a_d = 0.05 + value0 * 3.0
        elif data0 == 9: a_s = value0
        elif data0 == 10: a_r = 0.01 + value0 * 4.0
        elif data0 == 11: f_a = 0.001 + value0 * 2.0
        elif data0 == 12: f_d = 0.05 + value0 * 3.0
        elif data0 == 13: f_s = value0
        elif data0 == 14: hpf = 20.0 + value0 * 1000.0
        elif data0 == 15: master_tune = 0.95 + value0 * 0.1

vstaudio.on_event(handle_event)
