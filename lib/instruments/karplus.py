# mpvst-macro-labels: Volume | Pluck Position | String Damping | Body Resonance | Pick Hardness | Decay | Master Tune

import array
import math

import synthio
import vstaudio

SR = vstaudio.sample_rate()
TAU = 2.0 * math.pi

def noise_table(length=8192, seed=1234):
    out = array.array("h", bytearray(length * 2))
    state = seed
    for i in range(length):
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        out[i] = ((state >> 15) & 0xFFFF) - 32768
    return out

NOISE = noise_table()
NOISE_HZ = SR / 8192.0

# For Karplus-Strong without a true delay line, we simulate the "ring" 
# using a highly resonant comb filter equivalent, or by striking a very precise bandpass.
# Actually, we can use a harmonic series with a rapid decay envelope on the higher harmonics,
# which is mathematically equivalent to the low-pass filtering in a Karplus delay loop!

def make_harmonic_table(length=2048, gain=32000):
    vals = [0.0] * length
    # Create all harmonics up to nyquist
    for mult in range(1, 40):
        amp = 1.0 / mult
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

PLUCK_BASE = make_harmonic_table()
FALL = array.array("h", (32767, 0))

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
vstaudio.output(synth)

# Macros
volume = 0.8
pluck_pos = 0.5 # Changes the "strike" tone (simulated via LP cutoff on noise)
damping = 0.5 # How fast high frequencies decay
body_res = 0.5
pick_hard = 0.5
decay_time = 2.0
master_tune = 1.0

voices = {}
serial = 0
MAX_VOICES = 6

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
    global volume, pluck_pos, damping, body_res, pick_hard, decay_time, master_tune
    global serial
    
    k = key_of(channel, note_id, data0)
    
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        if len(voices) >= MAX_VOICES:
            steal_oldest()
            
        hz = synthio.midi_to_hz(data0 + value1) * master_tune
        amp = volume * value0
        
        # 1. The Body/String (Sustained, but low-pass filtered over time to simulate damping)
        env_body = synthio.Envelope(attack_time=0.001, decay_time=decay_time, release_time=0.5, attack_level=1.0, sustain_level=0.0)
        
        # Damping is simulated by sweeping a lowpass filter down
        f_sweep = synthio.LFO(waveform=FALL, once=True, rate=1.0/(decay_time * (1.0 - damping * 0.8)), scale=10000.0, interpolate=True)
        lp_body = synthio.Biquad(synthio.FilterMode.LOW_PASS, synthio.Math(synthio.MathOperation.SUM, 200.0 + body_res * 400.0, f_sweep, 0.0), Q=1.0 + body_res)
        
        # 2. The Pick/Strike (Noise burst)
        env_pick = synthio.Envelope(attack_time=0.001, decay_time=0.02 + pluck_pos * 0.05, release_time=0.01, attack_level=1.0, sustain_level=0.0)
        hp_pick = synthio.Biquad(synthio.FilterMode.HIGH_PASS, 1000.0 + pick_hard * 4000.0, Q=0.5)
        
        notes = []
        notes.append(synthio.Note(hz, waveform=PLUCK_BASE, envelope=env_body, filter=lp_body, amplitude=amp * 0.8))
        if pick_hard > 0.01:
            notes.append(synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env_pick, filter=hp_pick, amplitude=amp * pick_hard * 0.3))
            
        serial += 1
        voices[k] = (tuple(notes), serial)
        for n in notes:
            synth.press(n)
            
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
        
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0: volume = value0
        elif data0 == 1: pluck_pos = value0
        elif data0 == 2: damping = value0
        elif data0 == 3: body_res = value0
        elif data0 == 4: pick_hard = value0
        elif data0 == 5: decay_time = 0.5 + value0 * 4.0
        elif data0 == 6: master_tune = 0.95 + value0 * 0.1

vstaudio.on_event(handle_event)
