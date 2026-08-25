# mpvst-macro-labels: Volume | Patch Select | Bitcrush Approx | Attack | Decay | Sustain | Release | Pitch Env Depth | Filter Env | Master Tune

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

# Arr1 (Breathy Choir) approx
WAVE_ARR1 = make_table(((1, 1.0), (2, 0.6), (3, 0.4), (5, 0.3), (7, 0.1), (9, 0.05)))
# Orch5 (Orchestra Hit) approx
WAVE_ORCH5 = make_table([(n, 1.0 / math.sqrt(n)) for n in range(1, 20)])
FALL = array.array("h", (32767, 0))

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
vstaudio.output(synth)

# Macros
volume = 0.8
patch = 0.0 # < 0.5 = Arr1, > 0.5 = Orch5
bitcrush = 0.0
amp_a = 0.1
amp_d = 0.5
amp_s = 0.8
amp_r = 0.5
pitch_env = 0.0
f_env = 0.0
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
    global volume, patch, bitcrush, amp_a, amp_d, amp_s, amp_r, pitch_env, f_env, master_tune
    global serial
    
    k = key_of(channel, note_id, data0)
    
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        if len(voices) >= MAX_VOICES:
            steal_oldest()
            
        hz = synthio.midi_to_hz(data0 + value1) * master_tune
        amp = volume * value0
        
        is_orch = patch > 0.5
        
        # Orch5 has a very specific tight envelope and pitch envelope
        actual_a = 0.01 if is_orch else amp_a
        actual_d = 0.5 if is_orch else amp_d
        actual_s = 0.0 if is_orch else amp_s
        actual_r = 0.1 if is_orch else amp_r
        
        env = synthio.Envelope(attack_time=actual_a, decay_time=actual_d, release_time=actual_r, attack_level=1.0, sustain_level=actual_s)
        
        wave = WAVE_ORCH5 if is_orch else WAVE_ARR1
        
        # Pitch envelope (for Orch5 "whack")
        actual_pitch_env = 0.5 if is_orch and pitch_env == 0.0 else pitch_env
        bend = synthio.LFO(waveform=FALL, once=True, rate=1.0/0.1, scale=actual_pitch_env) if actual_pitch_env > 0.01 else None
        
        # Fairlight aliasing approximation via a fixed low-pass filter (anti-aliasing filter was weak/stepped)
        c_base = 3000.0 if bitcrush > 0.5 else 8000.0
        
        # Filter envelope
        f_sweep = synthio.LFO(waveform=FALL, once=True, rate=1.0/actual_d, scale=f_env * 5000.0, interpolate=True)
        lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, synthio.Math(synthio.MathOperation.SUM, c_base, f_sweep, 0.0), Q=1.0)
        
        notes = []
        notes.append(synthio.Note(hz, waveform=wave, envelope=env, filter=lp, amplitude=amp * 0.7, bend=bend))
        
        serial += 1
        voices[k] = (tuple(notes), serial)
        for n in notes:
            synth.press(n)
            
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
        
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0: volume = value0
        elif data0 == 1: patch = value0
        elif data0 == 2: bitcrush = value0
        elif data0 == 3: amp_a = 0.001 + value0 * 2.0
        elif data0 == 4: amp_d = 0.05 + value0 * 3.0
        elif data0 == 5: amp_s = value0
        elif data0 == 6: amp_r = 0.01 + value0 * 4.0
        elif data0 == 7: pitch_env = value0
        elif data0 == 8: f_env = value0
        elif data0 == 9: master_tune = 0.95 + value0 * 0.1

vstaudio.on_event(handle_event)
