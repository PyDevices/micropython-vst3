# mpvst-macro-labels: Volume | Kick Pitch | Kick Ring | Snare Pitch | Snare Snap | Hihat Pitch | SP Crunch | Master Tune

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
PULSE = make_table([(n, 1.0/n if n%2!=0 else 0) for n in range(1, 40)])
NOISE = noise_table()
NOISE_HZ = SR / 8192.0
FALL = array.array("h", (32767, 0))

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
vstaudio.output(synth)

# Macros
volume = 0.8
kick_p = 0.5
kick_ring = 0.5
snare_p = 0.5
snare_snap = 0.5
hh_p = 0.5
crunch = 0.5
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
    global volume, kick_p, kick_ring, snare_p, snare_snap, hh_p, crunch, master_tune
    global serial
    
    k = key_of(channel, note_id, data0)
    
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        
        amp = volume * value0 * (1.0 + crunch) # Crunch adds volume
        notes = []
        
        # SP-1200 pitch envelope effect (usually samples are pitched down, causing crunch/aliasing)
        # We simulate the crunch by using hard clipped waveforms (pulse) and noise mixed in
        
        if data0 == 36: # Kick
            env = synthio.Envelope(attack_time=0.001, decay_time=0.4 + kick_ring * 0.4, release_time=0.1, attack_level=1.0, sustain_level=0.0)
            bend = synthio.LFO(waveform=FALL, once=True, rate=1.0/0.1, scale=0.5)
            hz = (40.0 + kick_p * 60.0) * master_tune
            lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, 400.0 + crunch * 1000.0, Q=1.0)
            notes.append(synthio.Note(hz, waveform=SINE, envelope=env, filter=lp, amplitude=amp * 0.8, bend=bend))
            if crunch > 0.1:
                notes.append(synthio.Note(hz, waveform=PULSE, envelope=env, filter=lp, amplitude=amp * crunch * 0.2, bend=bend))
                
        elif data0 == 38: # Snare
            env_body = synthio.Envelope(attack_time=0.001, decay_time=0.15, release_time=0.1, attack_level=1.0, sustain_level=0.0)
            env_snap = synthio.Envelope(attack_time=0.001, decay_time=0.2 + snare_snap * 0.2, release_time=0.1, attack_level=1.0, sustain_level=0.0)
            hz = (150.0 + snare_p * 100.0) * master_tune
            lp_body = synthio.Biquad(synthio.FilterMode.LOW_PASS, 1000.0 + crunch * 2000.0, Q=1.0)
            hp_snap = synthio.Biquad(synthio.FilterMode.HIGH_PASS, 1500.0, Q=0.5)
            notes.append(synthio.Note(hz, waveform=PULSE, envelope=env_body, filter=lp_body, amplitude=amp * 0.6))
            notes.append(synthio.Note(NOISE_HZ * master_tune, waveform=NOISE, envelope=env_snap, filter=hp_snap, amplitude=amp * 0.4))
            
        elif data0 in (42, 46): # Closed / Open HH
            decay = 0.05 if data0 == 42 else 0.4
            env = synthio.Envelope(attack_time=0.001, decay_time=decay, release_time=0.1, attack_level=1.0, sustain_level=0.0)
            hp = synthio.Biquad(synthio.FilterMode.HIGH_PASS, 5000.0 - hh_p * 2000.0 - crunch * 1000.0, Q=1.0)
            # The crunch makes the hi-hat lower bandwidth (pitched down)
            notes.append(synthio.Note(NOISE_HZ * master_tune, waveform=NOISE, envelope=env, filter=hp, amplitude=amp * 0.5))
            
        if notes:
            serial += 1
            voices[k] = (tuple(notes), serial)
            for n in notes:
                synth.press(n)
            
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        pass # Drum machine, ignore note off mostly unless we want to choke, but SP usually plays out

    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0: volume = value0
        elif data0 == 1: kick_p = value0
        elif data0 == 2: kick_ring = value0
        elif data0 == 3: snare_p = value0
        elif data0 == 4: snare_snap = value0
        elif data0 == 5: hh_p = value0
        elif data0 == 6: crunch = value0
        elif data0 == 7: master_tune = 0.95 + value0 * 0.1

vstaudio.on_event(handle_event)
