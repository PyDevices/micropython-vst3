# mpvst-macro-labels: Volume | Cutoff | Resonance | FM Amount | Osc Sync | Morph 1 | Morph 2 | Morph 3 | Morph 4 | Amp Attack | Amp Decay | Amp Sustain | Amp Release | Filter Attack | Filter Decay | Filter Sustain

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
cutoff_base = 3000.0
resonance = 1.0
fm_amount = 0.0
osc_sync = 0.0
morph1 = 0.0
morph2 = 0.0
morph3 = 0.0
morph4 = 0.0
amp_a = 0.01
amp_d = 0.3
amp_s = 0.5
amp_r = 0.3
filt_a = 0.01
filt_d = 0.3
filt_s = 0.5

voices = {}
serial = 0
MAX_VOICES = 12

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
    global volume, cutoff_base, resonance, fm_amount, osc_sync, morph1, morph2, morph3, morph4
    global amp_a, amp_d, amp_s, amp_r, filt_a, filt_d, filt_s
    global serial
    
    k = key_of(channel, note_id, data0)
    
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        if len(voices) >= MAX_VOICES:
            steal_oldest()
            
        hz = synthio.midi_to_hz(data0 + value1)
        amp = volume * value0
        
        env = synthio.Envelope(attack_time=amp_a, decay_time=amp_d, release_time=amp_r, attack_level=1.0, sustain_level=amp_s)
        
        # Morph parameters dynamically alter the tone
        actual_cutoff = cutoff_base * (1.0 + morph1 * 2.0)
        actual_res = resonance * (1.0 + morph2)
        
        env_tbl = env_shape_table(filt_a, filt_d, filt_s)
        f_sweep = synthio.LFO(waveform=env_tbl, once=True, rate=1.0/max(0.01, filt_a + filt_d), scale=4000.0 * (1.0 + morph3), interpolate=True)
        cutoff = synthio.Math(synthio.MathOperation.SUM, actual_cutoff, f_sweep, 0.0)
        
        lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, cutoff, Q=actual_res)
        
        o1 = synthio.Note(hz, waveform=SAW, envelope=env, filter=lp, amplitude=amp * 0.5)
        # FM emulation via detune/amplitude, plus Osc Sync: true audio-rate hard sync isn't
        # achievable in synthio (no per-sample phase reset), so approximate its buzzy,
        # harmonically-locked character by snapping osc2 toward an integer multiple of osc1's
        # frequency as Osc Sync increases, and brightening its waveform to match.
        base_ratio = 1.0 + fm_amount * 2.0 + morph4
        if osc_sync > 0.01:
            ratio = round(base_ratio)
            if ratio < 1:
                ratio = 1
            sync_ratio = base_ratio + (ratio - base_ratio) * osc_sync
            o2_wave = SAW
        else:
            sync_ratio = base_ratio
            o2_wave = SQUARE
        o2 = synthio.Note(hz * sync_ratio, waveform=o2_wave, envelope=env, filter=lp, amplitude=amp * 0.5 * (0.5 + fm_amount))

        serial += 1
        voices[k] = ((o1, o2), serial)
        synth.press(o1)
        synth.press(o2)
            
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
        
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0: volume = value0
        elif data0 == 1: cutoff_base = 50.0 * (100.0 ** value0)
        elif data0 == 2: resonance = 0.5 + value0 * 3.5
        elif data0 == 3: fm_amount = value0
        elif data0 == 4: osc_sync = value0
        elif data0 == 5: morph1 = value0
        elif data0 == 6: morph2 = value0
        elif data0 == 7: morph3 = value0
        elif data0 == 8: morph4 = value0
        elif data0 == 9: amp_a = 0.001 + value0 * 2.0
        elif data0 == 10: amp_d = 0.05 + value0 * 3.0
        elif data0 == 11: amp_s = value0
        elif data0 == 12: amp_r = 0.01 + value0 * 4.0
        elif data0 == 13: filt_a = 0.001 + value0 * 2.0
        elif data0 == 14: filt_d = 0.05 + value0 * 3.0
        elif data0 == 15: filt_s = value0

vstaudio.on_event(handle_event)
