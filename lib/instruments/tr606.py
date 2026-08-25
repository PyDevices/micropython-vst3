# mpvst-macro-labels: Level | Accent | BD Level | BD Decay | BD Pitch | SD Level | SD Snappy | SD Pitch | LT Pitch | HT Pitch | Cym Level | Cym Decay | Cym Tone | Hat Level | CH Decay | OH Decay

import array
import math

import synthio
import vstaudio

try:
    from ulab import numpy as np
except ImportError:
    np = None

SR = vstaudio.sample_rate()
TAU = 2.0 * math.pi


def make_table(parts, length=2048, gain=32000):
    if np is not None:
        idx = np.arange(length)
        acc = np.zeros(length)
        for mult, amp in parts:
            acc = acc + amp * np.sin(idx * (TAU * mult / length))
        peak = np.max(acc * acc) ** 0.5
        if peak <= 0.0:
            peak = 1.0
        scaled = acc * (gain / peak)
        return array.array("h", [int(v) for v in scaled])
    vals = [0.0] * length
    for mult, amp in parts:
        step = TAU * mult / length
        for i in range(length):
            vals[i] += amp * math.sin(step * i)
    peak = 0.0
    for v in vals:
        a = v if v >= 0.0 else -v
        if a > peak:
            peak = a
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


def logmap(v, lo, hi):
    return lo * ((hi / lo) ** v)


SINE = make_table(((1, 1.0),))
TRIANGLE = make_table([(n, (1.0 / (n*n)) * (-1)**((n-1)//2)) for n in range(1, 11, 2)])
NOISE = noise_table(seed=606060)
NOISE_HZ = SR / 8192.0
FALL = array.array("h", (32767, 0))

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
vstaudio.output(synth)

# Master params
master_level = 0.8
accent_level = 0.5

# Voice Levels
bd_level = 1.0
sd_level = 1.0
cym_level = 0.8
hat_level = 0.8

# BD params
bd_decay = 0.3
bd_pitch = 60.0

# SD params
sd_snappy = 0.6
sd_pitch = 220.0

# Toms
lt_pitch = 100.0
ht_pitch = 160.0

# Others
cym_decay = 0.6
cym_tone = 6000.0
ch_decay = 0.05
oh_decay = 0.3

voices = {}
serial = 0
open_hat_keys = []
MAX_VOICES = 12


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


def trigger_voice(k, notes):
    global serial
    release_voice(k)
    while len(voices) + len(notes) >= MAX_VOICES:
        steal_oldest()
    serial += 1
    voices[k] = (tuple(notes), serial)
    for note in notes:
        synth.press(note)


def handle_event(event_type, channel, note_id, data0, value0, value1, sample_position):
    global master_level, accent_level
    global bd_level, bd_decay, bd_pitch
    global sd_level, sd_snappy, sd_pitch
    global lt_pitch, ht_pitch
    global cym_level, cym_decay, cym_tone, hat_level, ch_decay, oh_decay
    
    k = key_of(channel, note_id, data0)
    
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        pitch = data0
        vel = value0
        base_amp = master_level * (vel + accent_level * (1.0 if vel > 0.8 else 0.0))
        
        notes_to_play = []
        
        # BD (35, 36)
        if pitch in (35, 36):
            amp = base_amp * bd_level
            env = synthio.Envelope(attack_time=0.001, decay_time=bd_decay, release_time=0.05, attack_level=1.0, sustain_level=0.0)
            drop = synthio.LFO(waveform=FALL, once=True, rate=25.0, scale=0.3, interpolate=True)
            lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, bd_pitch * 4.0, Q=0.7)
            body = synthio.Note(bd_pitch, waveform=SINE, envelope=env, filter=lp, amplitude=amp, bend=drop)
            notes_to_play.append(body)
            
        # SD (38, 40)
        elif pitch in (38, 40):
            amp = base_amp * sd_level
            body_env = synthio.Envelope(attack_time=0.001, decay_time=0.1, release_time=0.05, attack_level=1.0, sustain_level=0.0)
            drop = synthio.LFO(waveform=FALL, once=True, rate=40.0, scale=0.15, interpolate=True)
            body = synthio.Note(sd_pitch, waveform=TRIANGLE, envelope=body_env, amplitude=amp*0.8, bend=drop)
            
            snare_env = synthio.Envelope(attack_time=0.001, decay_time=0.15, release_time=0.05, attack_level=1.0, sustain_level=0.0)
            snare_hp = synthio.Biquad(synthio.FilterMode.HIGH_PASS, 2000.0, Q=1.0)
            snare = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=snare_env, filter=snare_hp, amplitude=amp * sd_snappy)
            
            notes_to_play.extend([body, snare])
            
        # Toms (41, 43, 45, 47, 48, 50)
        elif pitch in (41, 43, 45, 47, 48, 50):
            amp = base_amp * 0.8
            tune = lt_pitch if pitch < 48 else ht_pitch
            
            env = synthio.Envelope(attack_time=0.001, decay_time=0.3, release_time=0.1, attack_level=1.0, sustain_level=0.0)
            drop = synthio.LFO(waveform=FALL, once=True, rate=20.0, scale=0.2, interpolate=True)
            note = synthio.Note(tune, waveform=SINE, envelope=env, amplitude=amp, bend=drop)
            notes_to_play.append(note)
            
        # Hats (42, 44, 46)
        elif pitch in (42, 44, 46):
            amp = base_amp * hat_level
            is_open = pitch == 46
            if not is_open:
                for ok in open_hat_keys:
                    release_voice(ok)
                open_hat_keys.clear()
                
            env = synthio.Envelope(attack_time=0.001, decay_time=oh_decay if is_open else ch_decay, release_time=0.05, attack_level=1.0, sustain_level=0.0)
            hp = synthio.Biquad(synthio.FilterMode.HIGH_PASS, cym_tone * 1.5, Q=0.8)
            note = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env, filter=hp, amplitude=amp * 0.7)
            notes_to_play.append(note)
            if is_open:
                open_hat_keys.append(k)
                
        # Cymbal (49, 51, 57, 59)
        elif pitch in (49, 51, 57, 59):
            amp = base_amp * cym_level
            env = synthio.Envelope(attack_time=0.001, decay_time=cym_decay, release_time=0.2, attack_level=1.0, sustain_level=0.0)
            bp = synthio.Biquad(synthio.FilterMode.BAND_PASS, cym_tone, Q=0.5)
            hp = synthio.Biquad(synthio.FilterMode.HIGH_PASS, cym_tone * 1.5, Q=0.7)
            note1 = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env, filter=bp, amplitude=amp * 0.5)
            note2 = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env, filter=hp, amplitude=amp * 0.5)
            notes_to_play.extend([note1, note2])

        # Fallback (other percussion)
        else:
            amp = base_amp * 0.6
            env = synthio.Envelope(attack_time=0.001, decay_time=0.1, release_time=0.05, attack_level=1.0, sustain_level=0.0)
            bp = synthio.Biquad(synthio.FilterMode.BAND_PASS, 3000.0, Q=1.0)
            note = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env, filter=bp, amplitude=amp)
            notes_to_play.append(note)

        if notes_to_play:
            trigger_voice(k, notes_to_play)

    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
        if k in open_hat_keys:
            open_hat_keys.remove(k)
            
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0: master_level = value0
        elif data0 == 1: accent_level = value0
        elif data0 == 2: bd_level = logmap(value0, 0.1, 2.0)
        elif data0 == 3: bd_decay = logmap(value0, 0.1, 1.0)
        elif data0 == 4: bd_pitch = logmap(value0, 40.0, 90.0)
        elif data0 == 5: sd_level = logmap(value0, 0.1, 2.0)
        elif data0 == 6: sd_snappy = value0
        elif data0 == 7: sd_pitch = logmap(value0, 150.0, 300.0)
        elif data0 == 8: lt_pitch = logmap(value0, 70.0, 140.0)
        elif data0 == 9: ht_pitch = logmap(value0, 120.0, 200.0)
        elif data0 == 10: cym_level = logmap(value0, 0.1, 2.0)
        elif data0 == 11: cym_decay = logmap(value0, 0.2, 1.5)
        elif data0 == 12: cym_tone = logmap(value0, 3000.0, 8000.0)
        elif data0 == 13: hat_level = logmap(value0, 0.1, 2.0)
        elif data0 == 14: ch_decay = logmap(value0, 0.02, 0.15)
        elif data0 == 15: oh_decay = logmap(value0, 0.1, 0.6)


vstaudio.on_event(handle_event)
