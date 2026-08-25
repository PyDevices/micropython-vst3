# mpvst-macro-labels: Volume | Tuning | Cutoff | Resonance | Env Mod | Decay | Accent | Overdrive | Master Tune

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

SAW = make_table([(n, 1.0 / n) for n in range(1, 40)])
FALL = array.array("h", (32767, 0))

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
vstaudio.output(synth)

# Macros
volume = 0.8
tuning = 1.0
cutoff_val = 500.0
res = 2.0
env_mod = 4000.0
decay_time = 0.5
accent = 0.0
overdrive = 1.0
master_tune = 1.0

voices = {}
serial = 0
MAX_VOICES = 1 # Monosynth

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
    global volume, tuning, cutoff_val, res, env_mod, decay_time, accent, overdrive, master_tune
    global serial
    
    k = key_of(channel, note_id, data0)
    
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        if len(voices) >= MAX_VOICES:
            steal_oldest()
            
        hz = synthio.midi_to_hz(data0 + value1) * master_tune * tuning
        
        # Accent alters decay and env mod depth
        actual_decay = decay_time * (0.2 if accent > 0.5 else 1.0)
        actual_env_mod = env_mod * (1.5 if accent > 0.5 else 1.0)
        
        amp = volume * value0 * overdrive * (1.2 if accent > 0.5 else 1.0)
        
        env = synthio.Envelope(attack_time=0.01, decay_time=actual_decay, release_time=0.1, attack_level=1.0, sustain_level=0.1)
        
        f_sweep = synthio.LFO(waveform=FALL, once=True, rate=1.0/actual_decay, scale=actual_env_mod, interpolate=True)
        cutoff = synthio.Math(synthio.MathOperation.SUM, cutoff_val, f_sweep, 0.0)
        
        lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, cutoff, Q=res)
        
        n = synthio.Note(hz, waveform=SAW, envelope=env, filter=lp, amplitude=amp * 0.5)
        
        serial += 1
        voices[k] = ((n,), serial)
        synth.press(n)
            
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
        
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0: volume = value0
        elif data0 == 1: tuning = 0.5 + value0
        elif data0 == 2: cutoff_val = 50.0 * (100.0 ** value0)
        elif data0 == 3: res = 0.5 + value0 * 4.5
        elif data0 == 4: env_mod = value0 * 8000.0
        elif data0 == 5: decay_time = 0.05 + value0 * 2.0
        elif data0 == 6: accent = value0
        elif data0 == 7: overdrive = 1.0 + value0 * 3.0
        elif data0 == 8: master_tune = 0.95 + value0 * 0.1

vstaudio.on_event(handle_event)
