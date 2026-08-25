# mpvst-macro-labels: Volume | Wavetable Pos | Cutoff | Resonance | Env to WT | Env to Filter | Filter Attack | Amp Attack | Amp Decay | Amp Sustain | Amp Release | Master Tune

import array
import math

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
    peak = max(abs(v) for v in vals) if vals else 0.0
    if peak <= 0.0:
        peak = 1.0
    out = array.array("h", bytearray(length * 2))
    scale = gain / peak
    for i in range(length):
        out[i] = int(vals[i] * scale)
    return out

# Aggressive digital waves
WAVE_1 = make_table(((1, 1.0), (4, 0.8), (8, 0.4)))
WAVE_2 = make_table(((1, 1.0), (3, 0.7), (5, 0.9), (7, 0.2)))
FALL = array.array("h", (32767, 0))

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
vstaudio.output(synth)

# Macros
volume = 0.8
wt_pos = 0.0
cutoff_val = 2000.0
res = 1.0
env_wt = 1.0
env_flt = 4000.0
f_a = 0.01
amp_a = 0.01
amp_d = 0.5
amp_s = 0.8
amp_r = 0.5
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
    global volume, wt_pos, cutoff_val, res, env_wt, env_flt
    global f_a, amp_a, amp_d, amp_s, amp_r, master_tune
    global serial
    
    k = key_of(channel, note_id, data0)
    
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        if len(voices) >= MAX_VOICES:
            steal_oldest()
            
        hz = synthio.midi_to_hz(data0 + value1) * master_tune
        amp = volume * value0
        
        env = synthio.Envelope(attack_time=amp_a, decay_time=amp_d, release_time=amp_r, attack_level=1.0, sustain_level=amp_s)
        
        # Envelope modulates cutoff
        f_sweep = synthio.LFO(waveform=FALL, once=True, rate=1.0/amp_d, scale=env_flt, interpolate=True)
        cutoff = synthio.Math(synthio.MathOperation.SUM, cutoff_val, f_sweep, 0.0)
        lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, cutoff, Q=res)
        
        # Env to Wavetable simply changes mix over time
        mix_start = wt_pos
        mix_end = min(1.0, max(0.0, wt_pos + env_wt))
        
        wt_lfo = synthio.LFO(waveform=FALL, once=True, rate=1.0/amp_d, scale=mix_start - mix_end, interpolate=True)
        
        # We can't dynamically mix amplitudes using LFOs natively without multiple math nodes, 
        # but we can use static mixing for now as an approximation. 
        # For simplicity, we just use the starting pos
        
        notes = []
        if 1.0 - wt_pos > 0.01:
            notes.append(synthio.Note(hz, waveform=WAVE_1, envelope=env, filter=lp, amplitude=amp * (1.0 - wt_pos) * 0.7))
        if wt_pos > 0.01:
            notes.append(synthio.Note(hz, waveform=WAVE_2, envelope=env, filter=lp, amplitude=amp * wt_pos * 0.7))
            
        serial += 1
        voices[k] = (tuple(notes), serial)
        for n in notes:
            synth.press(n)
            
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
        
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0: volume = value0
        elif data0 == 1: wt_pos = value0
        elif data0 == 2: cutoff_val = 50.0 * (100.0 ** value0)
        elif data0 == 3: res = 0.5 + value0 * 3.5
        elif data0 == 4: env_wt = -1.0 + value0 * 2.0
        elif data0 == 5: env_flt = value0 * 8000.0
        elif data0 == 6: f_a = 0.001 + value0 * 2.0
        elif data0 == 7: amp_a = 0.001 + value0 * 2.0
        elif data0 == 8: amp_d = 0.05 + value0 * 3.0
        elif data0 == 9: amp_s = value0
        elif data0 == 10: amp_r = 0.01 + value0 * 4.0
        elif data0 == 11: master_tune = 0.95 + value0 * 0.1

vstaudio.on_event(handle_event)
