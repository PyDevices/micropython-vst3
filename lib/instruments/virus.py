# mpvst-macro-labels: Volume | Hypersaw Detune | Sub Osc | Cutoff | Resonance | Distortion | Env Depth | Amp Attack | Amp Decay | Amp Sustain | Amp Release | Master Tune

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
hs_detune = 0.2
sub_osc = 0.5
cutoff_val = 2000.0
res = 1.0
distortion = 1.0
env_depth = 4000.0
amp_a = 0.01
amp_d = 0.5
amp_s = 0.8
amp_r = 0.3
master_tune = 1.0

voices = {}
serial = 0
MAX_VOICES = 4 # Hypersaw is very taxing (up to 7 saws per voice)

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
    global volume, hs_detune, sub_osc, cutoff_val, res, distortion, env_depth
    global amp_a, amp_d, amp_s, amp_r, master_tune
    global serial
    
    k = key_of(channel, note_id, data0)
    
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        if len(voices) >= MAX_VOICES:
            steal_oldest()
            
        hz = synthio.midi_to_hz(data0 + value1) * master_tune
        amp = volume * value0 * (1.0 + distortion * 0.5)
        
        env = synthio.Envelope(attack_time=amp_a, decay_time=amp_d, release_time=amp_r, attack_level=1.0, sustain_level=amp_s)
        
        f_sweep = synthio.LFO(waveform=FALL, once=True, rate=1.0/amp_d, scale=env_depth, interpolate=True)
        cutoff = synthio.Math(synthio.MathOperation.SUM, cutoff_val, f_sweep, 0.0)
        
        lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, cutoff, Q=res)
        
        notes = []
        
        # Hypersaw emulation (5 saws)
        detunes = [0.0, hs_detune * 0.03, -hs_detune * 0.03, hs_detune * 0.06, -hs_detune * 0.06]
        pans = [0.0, 0.4, -0.4, 0.8, -0.8]
        
        base_a = amp * 0.2
        for i in range(5):
            notes.append(synthio.Note(hz * (1.0 + detunes[i]), waveform=SAW, envelope=env, filter=lp, amplitude=base_a, panning=pans[i]))
            
        if sub_osc > 0.01:
            notes.append(synthio.Note(hz * 0.5, waveform=SQUARE, envelope=env, filter=lp, amplitude=amp * sub_osc * 0.4))
            
        serial += 1
        voices[k] = (tuple(notes), serial)
        for n in notes:
            synth.press(n)
            
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
        
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0: volume = value0
        elif data0 == 1: hs_detune = value0
        elif data0 == 2: sub_osc = value0
        elif data0 == 3: cutoff_val = 50.0 * (100.0 ** value0)
        elif data0 == 4: res = 0.5 + value0 * 3.5
        elif data0 == 5: distortion = value0 * 2.0
        elif data0 == 6: env_depth = value0 * 8000.0
        elif data0 == 7: amp_a = 0.001 + value0 * 2.0
        elif data0 == 8: amp_d = 0.05 + value0 * 3.0
        elif data0 == 9: amp_s = value0
        elif data0 == 10: amp_r = 0.01 + value0 * 4.0
        elif data0 == 11: master_tune = 0.95 + value0 * 0.1

vstaudio.on_event(handle_event)
