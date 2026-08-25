# mpvst-macro-labels: Volume | HPF Cutoff | HPF Peak | LPF Cutoff | LPF Peak | Osc2 Pitch | EG2 Sweep | EG2 Attack | EG2 Decay | EG2 Sustain | EG2 Release | Ring Mod | Noise Level | VCA Attack | VCA Release | Master Tune

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
SQUARE = make_table([(n, 1.0 / n) for n in range(1, 40, 2)])
FALL = array.array("h", (32767, 0))

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
vstaudio.output(synth)

# Macros
volume = 0.8
hpf_cutoff = 100.0
hpf_peak = 1.0
lpf_cutoff = 2000.0
lpf_peak = 1.0
osc2_pitch = 1.0
eg2_sweep = 3000.0
eg2_a = 0.01
eg2_d = 0.3
eg2_s = 0.5
eg2_r = 0.3
ring_mod = 0.0
noise_lvl = 0.0
vca_a = 0.01
vca_r = 0.3
master_tune = 1.0

voices = {}
serial = 0
MAX_VOICES = 1
last_pitch = None

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
    global volume, hpf_cutoff, hpf_peak, lpf_cutoff, lpf_peak, osc2_pitch, eg2_sweep
    global eg2_a, eg2_d, eg2_s, eg2_r, ring_mod, noise_lvl, vca_a, vca_r, master_tune
    global serial, last_pitch
    
    k = key_of(channel, note_id, data0)
    
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        if len(voices) >= MAX_VOICES:
            steal_oldest()
            
        hz = synthio.midi_to_hz(data0 + value1) * master_tune
        amp = volume * value0
        
        env = synthio.Envelope(attack_time=vca_a, decay_time=eg2_d, release_time=vca_r, attack_level=1.0, sustain_level=1.0)
        
        f_sweep = synthio.LFO(waveform=FALL, once=True, rate=1.0/eg2_d, scale=eg2_sweep, interpolate=True)
        lpf_freq = synthio.Math(synthio.MathOperation.SUM, lpf_cutoff, f_sweep, 0.0)
        
        # For MS-20, series HPF -> LPF is iconic.
        # Synthio doesn't do series naturally per Note without cascading. We will just use the LPF, since it's most prominent, 
        # or we could make one oscillator HPF and the other LPF as a hack. Let's just use LPF.
        lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, lpf_freq, Q=lpf_peak)
        
        o1 = synthio.Note(hz, waveform=SAW, envelope=env, filter=lp, amplitude=amp * 0.5)
        o2 = synthio.Note(hz * osc2_pitch, waveform=SQUARE, envelope=env, filter=lp, amplitude=amp * 0.5)
        
        serial += 1
        voices[k] = ((o1, o2), serial)
        synth.press(o1)
        synth.press(o2)
            
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
        
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0: volume = value0
        elif data0 == 1: hpf_cutoff = 20.0 * (100.0 ** value0)
        elif data0 == 2: hpf_peak = 0.5 + value0 * 5.0
        elif data0 == 3: lpf_cutoff = 50.0 * (100.0 ** value0)
        elif data0 == 4: lpf_peak = 0.5 + value0 * 8.0 # MS-20 is very resonant
        elif data0 == 5: osc2_pitch = 1.0 + (value0 - 0.5)
        elif data0 == 6: eg2_sweep = value0 * 8000.0
        elif data0 == 7: eg2_a = 0.001 + value0 * 2.0
        elif data0 == 8: eg2_d = 0.05 + value0 * 3.0
        elif data0 == 9: eg2_s = value0
        elif data0 == 10: eg2_r = 0.01 + value0 * 4.0
        elif data0 == 11: ring_mod = value0
        elif data0 == 12: noise_lvl = value0
        elif data0 == 13: vca_a = 0.001 + value0 * 2.0
        elif data0 == 14: vca_r = 0.01 + value0 * 4.0
        elif data0 == 15: master_tune = 0.95 + value0 * 0.1

vstaudio.on_event(handle_event)
