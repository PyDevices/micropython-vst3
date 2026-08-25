# mpvst-macro-labels: Volume | Breath Noise | Tone Brilliance | Attack | Decay | Sustain | Release | Vibrato Rate | Vibrato Depth | Filter Env | Master Tune

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

def noise_table(length=8192, seed=1234):
    out = array.array("h", bytearray(length * 2))
    state = seed
    for i in range(length):
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        out[i] = ((state >> 15) & 0xFFFF) - 32768
    return out

# "Shakuhachi" type wave
WAVE_FLUTE = make_table(((1, 1.0), (3, 0.4), (5, 0.1), (7, 0.05)))
NOISE = noise_table()
NOISE_HZ = SR / 8192.0
SINE = make_table(((1, 1.0),))
FALL = array.array("h", (32767, 0))

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
vstaudio.output(synth)

# Macros
volume = 0.8
breath = 0.5
brilliance = 0.5
amp_a = 0.1
amp_d = 0.5
amp_s = 0.8
amp_r = 0.5
vib_rate = 5.0
vib_depth = 0.0
f_env = 0.5
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
    global volume, breath, brilliance, amp_a, amp_d, amp_s, amp_r
    global vib_rate, vib_depth, f_env, master_tune
    global serial
    
    k = key_of(channel, note_id, data0)
    
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        if len(voices) >= MAX_VOICES:
            steal_oldest()
            
        hz = synthio.midi_to_hz(data0 + value1) * master_tune
        amp = volume * value0
        
        env = synthio.Envelope(attack_time=amp_a, decay_time=amp_d, release_time=amp_r, attack_level=1.0, sustain_level=amp_s)
        env_breath = synthio.Envelope(attack_time=amp_a*0.5, decay_time=0.2, release_time=amp_r, attack_level=1.0, sustain_level=0.0)
        
        # Emulator II has 27kHz sample rate, creating a slightly muffled/aliased top end
        cutoff = 2000.0 + brilliance * 4000.0
        
        f_sweep = synthio.LFO(waveform=FALL, once=True, rate=1.0/amp_d, scale=f_env * 4000.0, interpolate=True)
        actual_c = synthio.Math(synthio.MathOperation.SUM, cutoff, f_sweep, 0.0)
        lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, actual_c, Q=1.0)
        
        vib_lfo = synthio.LFO(waveform=SINE, rate=vib_rate, scale=vib_depth * 0.03) if vib_depth > 0.01 else None
        
        notes = []
        notes.append(synthio.Note(hz, waveform=WAVE_FLUTE, envelope=env, filter=lp, amplitude=amp * 0.7, bend=vib_lfo))
        if breath > 0.01:
            bp_noise = synthio.Biquad(synthio.FilterMode.BAND_PASS, 3000.0, Q=2.0)
            notes.append(synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env_breath, filter=bp_noise, amplitude=amp * breath * 0.3))
            
        serial += 1
        voices[k] = (tuple(notes), serial)
        for n in notes:
            synth.press(n)
            
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
        
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0: volume = value0
        elif data0 == 1: breath = value0
        elif data0 == 2: brilliance = value0
        elif data0 == 3: amp_a = 0.001 + value0 * 2.0
        elif data0 == 4: amp_d = 0.05 + value0 * 3.0
        elif data0 == 5: amp_s = value0
        elif data0 == 6: amp_r = 0.01 + value0 * 4.0
        elif data0 == 7: vib_rate = 0.1 + value0 * 10.0
        elif data0 == 8: vib_depth = value0
        elif data0 == 9: f_env = value0
        elif data0 == 10: master_tune = 0.95 + value0 * 0.1

vstaudio.on_event(handle_event)
