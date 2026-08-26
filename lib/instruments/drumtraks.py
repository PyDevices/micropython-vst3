# mpvst-macro-labels: Volume | Kick Pitch | Snare Pitch | HiHat Pitch | Tom Pitch | Crunch Level | Overall Decay | Master Tune

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
SQUARE = make_table([(n, 1.0/n) for n in range(1, 40, 2)])
NOISE = noise_table()
NOISE_HZ = SR / 8192.0
FALL = array.array("h", (32767, 0))

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
vstaudio.output(synth)

# Macros
volume = 0.8
kick_p = 0.5
snare_p = 0.5
hh_p = 0.5
tom_p = 0.5
crunch = 0.5
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
    global volume, kick_p, snare_p, hh_p, tom_p, crunch, decay_scale, master_tune
    global serial
    
    k = key_of(channel, note_id, data0)
    
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        
        amp = volume * value0 * (1.0 + crunch)
        notes = []
        
        # Drumtraks uses 8-bit companded PCM, sounded very gritty when pitched down
        c_filter = 8000.0 - crunch * 4000.0 # Simulate aliasing/bandwidth reduction
        lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, c_filter, Q=1.0)
        
        if data0 == 36: # Kick
            env = synthio.Envelope(attack_time=0.001, decay_time=0.2 * (1.0 + decay_scale), release_time=0.1, attack_level=1.0, sustain_level=0.0)
            bend = synthio.LFO(waveform=FALL, once=True, rate=1.0/0.05, scale=0.4)
            hz = 40.0 + kick_p * 60.0
            # Mix sine with some square for 8-bit grit
            notes.append(synthio.Note(hz * master_tune, waveform=SINE, envelope=env, filter=lp, amplitude=amp * 0.8, bend=bend))
            if crunch > 0.1:
                notes.append(synthio.Note(hz * master_tune, waveform=SQUARE, envelope=env, filter=lp, amplitude=amp * crunch * 0.2, bend=bend))
                
        elif data0 == 38: # Snare
            env_body = synthio.Envelope(attack_time=0.001, decay_time=0.15 * (1.0 + decay_scale), release_time=0.1, attack_level=1.0, sustain_level=0.0)
            env_snap = synthio.Envelope(attack_time=0.001, decay_time=0.2 * (1.0 + decay_scale), release_time=0.1, attack_level=1.0, sustain_level=0.0)
            hz = 150.0 + snare_p * 100.0
            
            hp_snap = synthio.Biquad(synthio.FilterMode.HIGH_PASS, 1000.0, Q=0.5)
            
            notes.append(synthio.Note(hz * master_tune, waveform=SQUARE, envelope=env_body, filter=lp, amplitude=amp * 0.4))
            notes.append(synthio.Note(NOISE_HZ * master_tune, waveform=NOISE, envelope=env_snap, filter=hp_snap, amplitude=amp * 0.6))
            
        elif data0 in (42, 46): # Closed / Open HH
            decay = 0.05 if data0 == 42 else 0.4 * (1.0 + decay_scale)
            env = synthio.Envelope(attack_time=0.001, decay_time=decay, release_time=0.1, attack_level=1.0, sustain_level=0.0)
            hp = synthio.Biquad(synthio.FilterMode.HIGH_PASS, 4000.0 + hh_p * 2000.0 - crunch * 2000.0, Q=1.0)
            notes.append(synthio.Note(NOISE_HZ * master_tune, waveform=NOISE, envelope=env, filter=hp, amplitude=amp * 0.5))
            
        elif data0 in (45, 47, 50): # Toms
            hz = (80.0 if data0 == 45 else (110.0 if data0 == 47 else 140.0)) + tom_p * 40.0
            env = synthio.Envelope(attack_time=0.001, decay_time=0.3 * (1.0 + decay_scale), release_time=0.1, attack_level=1.0, sustain_level=0.0)
            bend = synthio.LFO(waveform=FALL, once=True, rate=1.0/0.1, scale=0.2)
            notes.append(synthio.Note(hz * master_tune, waveform=SQUARE, envelope=env, filter=lp, amplitude=amp * 0.8, bend=bend))
            
        if notes:
            serial += 1
            voices[k] = (tuple(notes), serial)
            for n in notes:
                synth.press(n)
            
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        pass

    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0: volume = value0
        elif data0 == 1: kick_p = value0
        elif data0 == 2: snare_p = value0
        elif data0 == 3: hh_p = value0
        elif data0 == 4: tom_p = value0
        elif data0 == 5: crunch = value0
        elif data0 == 6: decay_scale = value0
        elif data0 == 7: master_tune = 0.95 + value0 * 0.1

# Patch 1 (Program Change 0) is the sound this script's module-level
# defaults describe, so a fresh instance and Patch 1 are the same thing.
# piece.py also reads it: a macro a composition does not set resolves here
# rather than to 0.5. Derived by tools/derive_patches.py - see that file
# before editing these numbers by hand.
PATCHES = {
    0: ("Init", (
        0.8, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5)),
}


def _apply_patch(index, channel=0, note_id=-1, sample_position=0):
    patch = PATCHES.get(index)
    if patch is None:
        return
    for macro_index, macro_value in enumerate(patch[1]):
        handle_event(vstaudio.EVENT_PARAMETER, channel, note_id,
                     macro_index, macro_value, 0.0, sample_position)


def _dispatch(event_type, channel, note_id, data0, value0, value1,
              sample_position):
    if event_type == vstaudio.EVENT_PROGRAM_CHANGE:
        _apply_patch(data0, channel, note_id, sample_position)
        return
    handle_event(event_type, channel, note_id, data0, value0, value1,
                 sample_position)


vstaudio.on_event(_dispatch)

