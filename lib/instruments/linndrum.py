# mpvst-macro-labels: Level | BD Pitch | BD Decay | SD Pitch | SD Snappy | Rim Pitch | Clap Decay | LT Pitch | MT Pitch | HT Pitch | Conga Pitch | Cowbell | Tambourine | Cabasa | CH Decay | OH Decay

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


SINE = make_table(((1, 1.0), (2, 0.2)))
TRIANGLE = make_table([(n, (1.0 / (n*n)) * (-1)**((n-1)//2)) for n in range(1, 11, 2)])
SQUARE = make_table([(n, 1.0 / n) for n in range(1, 15, 2)])
NOISE = noise_table(seed=13579)
NOISE_HZ = SR / 8192.0
FALL = array.array("h", (32767, 0))

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
vstaudio.output(synth)

# Master params
master_level = 0.8

# BD
bd_pitch = 65.0
bd_decay = 0.35

# SD
sd_pitch = 190.0
sd_snappy = 0.6

# Rim
rim_pitch = 800.0

# Clap
clap_decay = 0.3

# Toms
lt_pitch = 100.0
mt_pitch = 140.0
ht_pitch = 190.0

# Congas
conga_pitch = 280.0

# Percussion
cowbell_pitch = 900.0
tamb_level = 0.8
cabasa_level = 0.8

# Hats
ch_decay = 0.05
oh_decay = 0.4

voices = {}
serial = 0
open_hat_keys = []
MAX_VOICES = 16


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
    global master_level, bd_pitch, bd_decay, sd_pitch, sd_snappy, rim_pitch, clap_decay
    global lt_pitch, mt_pitch, ht_pitch, conga_pitch
    global cowbell_pitch, tamb_level, cabasa_level, ch_decay, oh_decay
    
    k = key_of(channel, note_id, data0)
    
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        pitch = data0
        amp = master_level * value0
        
        notes_to_play = []
        
        # BD (35, 36)
        if pitch in (35, 36):
            env = synthio.Envelope(attack_time=0.001, decay_time=bd_decay, release_time=0.05, attack_level=1.0, sustain_level=0.0)
            drop = synthio.LFO(waveform=FALL, once=True, rate=30.0, scale=0.4, interpolate=True)
            lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, bd_pitch * 4.0, Q=0.8)
            note = synthio.Note(bd_pitch, waveform=SINE, envelope=env, filter=lp, amplitude=amp, bend=drop)
            notes_to_play.append(note)
            
        # SD (38, 40)
        elif pitch in (38, 40):
            body_env = synthio.Envelope(attack_time=0.001, decay_time=0.15, release_time=0.05, attack_level=1.0, sustain_level=0.0)
            body = synthio.Note(sd_pitch, waveform=TRIANGLE, envelope=body_env, amplitude=amp * 0.7)
            
            snare_env = synthio.Envelope(attack_time=0.001, decay_time=0.2, release_time=0.05, attack_level=1.0, sustain_level=0.0)
            snare_hp = synthio.Biquad(synthio.FilterMode.HIGH_PASS, 1200.0, Q=1.0)
            snare = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=snare_env, filter=snare_hp, amplitude=amp * sd_snappy)
            
            notes_to_play.extend([body, snare])
            
        # Rimshot (37)
        elif pitch == 37:
            env = synthio.Envelope(attack_time=0.001, decay_time=0.05, release_time=0.02, attack_level=1.0, sustain_level=0.0)
            bp = synthio.Biquad(synthio.FilterMode.BAND_PASS, rim_pitch, Q=2.0)
            note = synthio.Note(rim_pitch, waveform=SQUARE, envelope=env, filter=bp, amplitude=amp)
            notes_to_play.append(note)
            
        # Clap (39)
        elif pitch == 39:
            bp = synthio.Biquad(synthio.FilterMode.BAND_PASS, 1400.0, Q=1.0)
            for i, attack in enumerate([0.001, 0.015, 0.03]):
                env = synthio.Envelope(attack_time=attack, decay_time=clap_decay, release_time=0.1, attack_level=1.0, sustain_level=0.0)
                notes_to_play.append(synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env, filter=bp, amplitude=amp * (1.0 - i*0.2)))
                
        # Toms (41, 43, 45, 47, 48, 50)
        elif pitch in (41, 43, 45, 47, 48, 50):
            if pitch in (41, 43):
                tune = lt_pitch
            elif pitch in (45, 47):
                tune = mt_pitch
            else:
                tune = ht_pitch
            
            env = synthio.Envelope(attack_time=0.002, decay_time=0.4, release_time=0.1, attack_level=1.0, sustain_level=0.0)
            drop = synthio.LFO(waveform=FALL, once=True, rate=25.0, scale=0.15, interpolate=True)
            note = synthio.Note(tune, waveform=TRIANGLE, envelope=env, amplitude=amp, bend=drop)
            notes_to_play.append(note)
            
        # Congas (62, 63, 64)
        elif pitch in (62, 63, 64):
            offset = 1.0 if pitch == 62 else (0.8 if pitch == 63 else 0.6)
            env = synthio.Envelope(attack_time=0.001, decay_time=0.25, release_time=0.1, attack_level=1.0, sustain_level=0.0)
            note = synthio.Note(conga_pitch * offset, waveform=SINE, envelope=env, amplitude=amp * 0.9)
            notes_to_play.append(note)
            
        # Cowbell (56)
        elif pitch == 56:
            env = synthio.Envelope(attack_time=0.001, decay_time=0.3, release_time=0.1, attack_level=1.0, sustain_level=0.0)
            bp = synthio.Biquad(synthio.FilterMode.BAND_PASS, cowbell_pitch * 2.0, Q=1.0)
            note1 = synthio.Note(cowbell_pitch, waveform=SQUARE, envelope=env, filter=bp, amplitude=amp * 0.5)
            note2 = synthio.Note(cowbell_pitch * 1.3, waveform=SQUARE, envelope=env, filter=bp, amplitude=amp * 0.5)
            notes_to_play.extend([note1, note2])
            
        # Tambourine (54) & Cabasa (69)
        elif pitch in (54, 69):
            is_tamb = pitch == 54
            a = amp * (tamb_level if is_tamb else cabasa_level)
            env = synthio.Envelope(attack_time=0.001, decay_time=0.15, release_time=0.05, attack_level=1.0, sustain_level=0.0)
            hp = synthio.Biquad(synthio.FilterMode.HIGH_PASS, 6000.0 if is_tamb else 8000.0, Q=0.8)
            note = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env, filter=hp, amplitude=a)
            notes_to_play.append(note)

        # Hats (42, 44, 46)
        elif pitch in (42, 44, 46):
            is_open = pitch == 46
            if not is_open:
                for ok in open_hat_keys:
                    release_voice(ok)
                open_hat_keys.clear()
                
            env = synthio.Envelope(attack_time=0.001, decay_time=oh_decay if is_open else ch_decay, release_time=0.05, attack_level=1.0, sustain_level=0.0)
            hp = synthio.Biquad(synthio.FilterMode.HIGH_PASS, 7000.0, Q=0.8)
            note = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env, filter=hp, amplitude=amp * 0.7)
            notes_to_play.append(note)
            if is_open:
                open_hat_keys.append(k)
                
        # Cymbals (49, 51, 57, 59)
        elif pitch in (49, 51, 57, 59):
            env = synthio.Envelope(attack_time=0.001, decay_time=1.2, release_time=0.3, attack_level=1.0, sustain_level=0.0)
            bp = synthio.Biquad(synthio.FilterMode.BAND_PASS, 4500.0, Q=0.5)
            hp = synthio.Biquad(synthio.FilterMode.HIGH_PASS, 8000.0, Q=0.7)
            note1 = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env, filter=bp, amplitude=amp * 0.5)
            note2 = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env, filter=hp, amplitude=amp * 0.4)
            notes_to_play.extend([note1, note2])

        # Fallback (other percussion)
        else:
            env = synthio.Envelope(attack_time=0.001, decay_time=0.1, release_time=0.05, attack_level=1.0, sustain_level=0.0)
            bp = synthio.Biquad(synthio.FilterMode.BAND_PASS, 3000.0, Q=1.0)
            note = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env, filter=bp, amplitude=amp * 0.5)
            notes_to_play.append(note)

        if notes_to_play:
            trigger_voice(k, notes_to_play)

    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
        if k in open_hat_keys:
            open_hat_keys.remove(k)
            
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0: master_level = value0
        elif data0 == 1: bd_pitch = logmap(value0, 40.0, 100.0)
        elif data0 == 2: bd_decay = logmap(value0, 0.1, 1.0)
        elif data0 == 3: sd_pitch = logmap(value0, 120.0, 300.0)
        elif data0 == 4: sd_snappy = value0
        elif data0 == 5: rim_pitch = logmap(value0, 400.0, 1200.0)
        elif data0 == 6: clap_decay = logmap(value0, 0.1, 0.8)
        elif data0 == 7: lt_pitch = logmap(value0, 60.0, 140.0)
        elif data0 == 8: mt_pitch = logmap(value0, 100.0, 180.0)
        elif data0 == 9: ht_pitch = logmap(value0, 140.0, 250.0)
        elif data0 == 10: conga_pitch = logmap(value0, 150.0, 450.0)
        elif data0 == 11: cowbell_pitch = logmap(value0, 500.0, 1500.0)
        elif data0 == 12: tamb_level = value0
        elif data0 == 13: cabasa_level = value0
        elif data0 == 14: ch_decay = logmap(value0, 0.02, 0.15)
        elif data0 == 15: oh_decay = logmap(value0, 0.1, 0.8)


vstaudio.on_event(handle_event)
