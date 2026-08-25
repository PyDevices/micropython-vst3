# mpvst-macro-labels: Volume | Cutoff | Resonance | Env Amount | Poly Mod | Osc2 Detune | Sync | Release | Amp Attack | Amp Decay | Amp Sustain | Filter Attack | Filter Decay | Filter Sustain | LFO Rate | LFO Depth

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
cutoff_base = 2000.0
resonance = 1.0
env_amount = 3000.0
poly_mod = 0.0
osc2_detune = 1.01
sync = 0.0
release_time = 0.4

amp_a = 0.01
amp_d = 0.3
amp_s = 0.5
filt_a = 0.01
filt_d = 0.3
filt_s = 0.2

lfo_rate = 5.0
lfo_depth = 0.0

voices = {}
serial = 0
MAX_VOICES = 5

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
    global volume, cutoff_base, resonance, env_amount, poly_mod, osc2_detune, sync, release_time
    global amp_a, amp_d, amp_s, filt_a, filt_d, filt_s, lfo_rate, lfo_depth
    global serial
    
    k = key_of(channel, note_id, data0)
    
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        if len(voices) >= MAX_VOICES:
            steal_oldest()
            
        hz = synthio.midi_to_hz(data0 + value1)
        amp = volume * value0
        
        env = synthio.Envelope(attack_time=amp_a, decay_time=amp_d, release_time=release_time, attack_level=1.0, sustain_level=amp_s)
        
        env_tbl = env_shape_table(filt_a, filt_d, filt_s)
        f_sweep = synthio.LFO(waveform=env_tbl, once=True, rate=1.0/max(0.01, filt_a + filt_d), scale=env_amount, interpolate=True)
        
        lfo = synthio.LFO(rate=lfo_rate, scale=lfo_depth * 1000.0)
        
        cutoff = synthio.Math(synthio.MathOperation.SUM, cutoff_base, f_sweep, lfo)
        lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, cutoff, Q=resonance)
        
        o1 = synthio.Note(hz, waveform=SAW, envelope=env, filter=lp, amplitude=amp * 0.5)
        # Poly Mod: filter env routed to osc B frequency, approximated as a static detune offset
        actual_detune = osc2_detune * (1.0 + poly_mod * 0.1)
        # Oscillator Sync: synthio can't hard-reset osc2's phase from osc1 at audio rate, so
        # approximate the characteristic sync timbre by snapping osc2 toward an integer multiple
        # of osc1's frequency (the buzzy, harmonically-locked sound sync produces) and brightening
        # its waveform as sync increases.
        if sync > 0.01:
            ratio = round(actual_detune)
            if ratio < 1:
                ratio = 1
            sync_detune = actual_detune + (ratio - actual_detune) * sync
            o2_wave = SAW
        else:
            sync_detune = actual_detune
            o2_wave = SQUARE
        o2 = synthio.Note(hz * sync_detune, waveform=o2_wave, envelope=env, filter=lp, amplitude=amp * 0.5)

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
        elif data0 == 3: env_amount = value0 * 8000.0
        elif data0 == 4: poly_mod = value0
        elif data0 == 5: osc2_detune = 1.0 + (value0 - 0.5) * 0.1
        elif data0 == 6: sync = value0
        elif data0 == 7: release_time = 0.01 + value0 * 3.0
        elif data0 == 8: amp_a = 0.001 + value0 * 2.0
        elif data0 == 9: amp_d = 0.05 + value0 * 3.0
        elif data0 == 10: amp_s = value0
        elif data0 == 11: filt_a = 0.001 + value0 * 2.0
        elif data0 == 12: filt_d = 0.05 + value0 * 3.0
        elif data0 == 13: filt_s = value0
        elif data0 == 14: lfo_rate = 0.1 + value0 * 20.0
        elif data0 == 15: lfo_depth = value0

vstaudio.on_event(handle_event)
