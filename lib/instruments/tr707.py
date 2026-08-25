# mpvst-macro-labels: Volume | Kick Level | Snare Level | Tom Level | HiHat Level | Crash Level | Overall Decay | Master Tune

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

SINE = make_table(((1, 1.0),))
# TR-707 used early PCM, so drums sound a bit metallic/FM-like compared to analog
FM_BELL = make_table(((1, 1.0), (3.14, 0.8), (5.5, 0.5)))
NOISE = noise_table()
NOISE_HZ = SR / 8192.0
FALL = array.array("h", (32767, 0))

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
vstaudio.output(synth)

# Macros
volume = 0.8
lvl_kick = 0.8
lvl_snare = 0.8
lvl_tom = 0.8
lvl_hh = 0.8
lvl_crash = 0.8
decay_scale = 0.5
master_tune = 1.0

voices = {}
serial = 0

def key_of(channel, note_id, pitch):
    return (channel, note_id if note_id >= 0 else pitch)

def release_voice(k):
    voice = voices.pop(k, None)
    if voice is not None:
        for note in voice[0]:
            synth.release(note)

def handle_event(event_type, channel, note_id, data0, value0, value1, sample_position):
    global volume, lvl_kick, lvl_snare, lvl_tom, lvl_hh, lvl_crash, decay_scale, master_tune
    global serial
    
    k = key_of(channel, note_id, data0)
    
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        
        amp = volume * value0
        notes = []
        
        if data0 == 36: # Kick
            env = synthio.Envelope(attack_time=0.001, decay_time=0.2 * (1.0 + decay_scale), release_time=0.1, attack_level=1.0, sustain_level=0.0)
            bend = synthio.LFO(waveform=FALL, once=True, rate=1.0/0.05, scale=0.3)
            notes.append(synthio.Note(60.0 * master_tune, waveform=SINE, envelope=env, amplitude=amp * lvl_kick, bend=bend))
                
        elif data0 == 38: # Snare
            env_body = synthio.Envelope(attack_time=0.001, decay_time=0.15 * (1.0 + decay_scale), release_time=0.1, attack_level=1.0, sustain_level=0.0)
            env_snap = synthio.Envelope(attack_time=0.001, decay_time=0.2 * (1.0 + decay_scale), release_time=0.1, attack_level=1.0, sustain_level=0.0)
            
            lp_body = synthio.Biquad(synthio.FilterMode.LOW_PASS, 1200.0, Q=1.0)
            hp_snap = synthio.Biquad(synthio.FilterMode.HIGH_PASS, 2000.0, Q=0.5)
            
            notes.append(synthio.Note(200.0 * master_tune, waveform=SINE, envelope=env_body, filter=lp_body, amplitude=amp * lvl_snare * 0.6))
            notes.append(synthio.Note(NOISE_HZ * master_tune, waveform=NOISE, envelope=env_snap, filter=hp_snap, amplitude=amp * lvl_snare * 0.4))
            
        elif data0 in (42, 46): # Closed / Open HH
            decay = 0.05 if data0 == 42 else 0.4 * (1.0 + decay_scale)
            env = synthio.Envelope(attack_time=0.001, decay_time=decay, release_time=0.1, attack_level=1.0, sustain_level=0.0)
            hp = synthio.Biquad(synthio.FilterMode.HIGH_PASS, 7000.0, Q=1.0)
            notes.append(synthio.Note(NOISE_HZ * master_tune, waveform=NOISE, envelope=env, filter=hp, amplitude=amp * lvl_hh * 0.5))
            
        elif data0 in (45, 47, 50): # Toms
            hz = 120.0 if data0 == 45 else (150.0 if data0 == 47 else 180.0)
            env = synthio.Envelope(attack_time=0.001, decay_time=0.3 * (1.0 + decay_scale), release_time=0.1, attack_level=1.0, sustain_level=0.0)
            bend = synthio.LFO(waveform=FALL, once=True, rate=1.0/0.1, scale=0.2)
            notes.append(synthio.Note(hz * master_tune, waveform=SINE, envelope=env, amplitude=amp * lvl_tom, bend=bend))
            
        elif data0 == 49: # Crash
            env = synthio.Envelope(attack_time=0.001, decay_time=1.5 * (1.0 + decay_scale), release_time=0.5, attack_level=1.0, sustain_level=0.0)
            bp = synthio.Biquad(synthio.FilterMode.BAND_PASS, 5000.0, Q=0.5)
            # Use FM bell for the metallic ringing of the crash
            notes.append(synthio.Note(1000.0 * master_tune, waveform=FM_BELL, envelope=env, filter=bp, amplitude=amp * lvl_crash * 0.5))
            notes.append(synthio.Note(NOISE_HZ * master_tune, waveform=NOISE, envelope=env, filter=bp, amplitude=amp * lvl_crash * 0.2))
            
        if notes:
            serial += 1
            voices[k] = (tuple(notes), serial)
            for n in notes:
                synth.press(n)
            
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        pass

    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0: volume = value0
        elif data0 == 1: lvl_kick = value0
        elif data0 == 2: lvl_snare = value0
        elif data0 == 3: lvl_tom = value0
        elif data0 == 4: lvl_hh = value0
        elif data0 == 5: lvl_crash = value0
        elif data0 == 6: decay_scale = value0
        elif data0 == 7: master_tune = 0.95 + value0 * 0.1

vstaudio.on_event(handle_event)
