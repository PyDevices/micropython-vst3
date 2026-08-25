# mpvst-macro-labels: Volume | Cutoff | Resonance | Sub Level | Noise Level | Chorus Depth | Chorus Rate | HPF | PWM Amount | LFO Rate | Env Depth | Amp Attack | Amp Decay | Amp Sustain | Amp Release | Filter Decay

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

def noise_table(length=8192, seed=1234567):
    out = array.array("h", bytearray(length * 2))
    state = seed
    for i in range(length):
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        out[i] = ((state >> 15) & 0xFFFF) - 32768
    return out

SAW = make_table([(n, 1.0 / n) for n in range(1, 40)])
SQUARE = make_table([(n, 1.0 / n) for n in range(1, 40, 2)])
NOISE = noise_table()
NOISE_HZ = SR / 8192.0
FALL = array.array("h", (32767, 0))

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
vstaudio.output(synth)

# Macros
volume = 0.8
cutoff_base = 2000.0
resonance = 1.2
sub_level = 0.5
noise_level = 0.0
chorus_depth = 0.5
chorus_rate = 1.0
hpf_cutoff = 40.0
pwm_amount = 0.5
lfo_rate = 5.0
env_depth = 3000.0

amp_a = 0.01
amp_d = 0.3
amp_s = 0.5
amp_r = 0.3
filt_d = 0.3

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
    global volume, cutoff_base, resonance, sub_level, noise_level, chorus_depth, chorus_rate
    global hpf_cutoff, pwm_amount, lfo_rate, env_depth, amp_a, amp_d, amp_s, amp_r, filt_d
    global serial
    
    k = key_of(channel, note_id, data0)
    
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        if len(voices) >= MAX_VOICES:
            steal_oldest()
            
        hz = synthio.midi_to_hz(data0 + value1)
        amp = volume * value0
        
        env = synthio.Envelope(attack_time=amp_a, decay_time=amp_d, release_time=amp_r, attack_level=1.0, sustain_level=amp_s)
        
        f_sweep = synthio.LFO(waveform=FALL, once=True, rate=1.0/filt_d, scale=env_depth, interpolate=True)
        
        cutoff = synthio.Math(synthio.MathOperation.SUM, cutoff_base, f_sweep, 0.0)
        lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, cutoff, Q=resonance)
        
        # Chorus simulation via wide panning and slight detune
        detune = chorus_depth * 0.01
        
        o_saw = synthio.Note(hz, waveform=SAW, envelope=env, filter=lp, amplitude=amp * 0.4, panning=-chorus_depth)
        o_sq = synthio.Note(hz * (1.0 + detune), waveform=SQUARE, envelope=env, filter=lp, amplitude=amp * 0.4 * pwm_amount, panning=chorus_depth)
        o_sub = synthio.Note(hz * 0.5, waveform=SQUARE, envelope=env, filter=lp, amplitude=amp * sub_level * 0.4, panning=0.0)
        n = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env, filter=lp, amplitude=amp * noise_level * 0.2)
        
        notes = [o_saw, o_sq, o_sub]
        if noise_level > 0.01:
            notes.append(n)
        
        serial += 1
        voices[k] = (tuple(notes), serial)
        for note in notes:
            synth.press(note)
            
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
        
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0: volume = value0
        elif data0 == 1: cutoff_base = 50.0 * (100.0 ** value0)
        elif data0 == 2: resonance = 0.5 + value0 * 3.5
        elif data0 == 3: sub_level = value0
        elif data0 == 4: noise_level = value0
        elif data0 == 5: chorus_depth = value0
        elif data0 == 6: chorus_rate = 0.1 + value0 * 5.0
        elif data0 == 7: hpf_cutoff = 20.0 + value0 * 1000.0
        elif data0 == 8: pwm_amount = value0
        elif data0 == 9: lfo_rate = 0.1 + value0 * 20.0
        elif data0 == 10: env_depth = value0 * 8000.0
        elif data0 == 11: amp_a = 0.001 + value0 * 2.0
        elif data0 == 12: amp_d = 0.05 + value0 * 3.0
        elif data0 == 13: amp_s = value0
        elif data0 == 14: amp_r = 0.01 + value0 * 4.0
        elif data0 == 15: filt_d = 0.05 + value0 * 3.0

vstaudio.on_event(handle_event)
