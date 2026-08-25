# mpvst-macro-labels: Level | Click Level | BD Pitch | BD Sweep | BD Decay | SD Pitch | SD Sweep | SD Decay | LT Pitch | MT Pitch | HT Pitch | Tom Sweep | Tom Decay | Noise Tone | Noise Level | Cymbal Decay

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


SINE = make_table(((1, 1.0),))
NOISE = noise_table(seed=135792468)
NOISE_HZ = SR / 8192.0
FALL = array.array("h", (32767, 0))

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
vstaudio.output(synth)

# Master params
master_level = 0.8
click_level = 0.6

# BD
bd_pitch = 50.0
bd_sweep = 0.8
bd_decay = 0.4

# SD
sd_pitch = 180.0
sd_sweep = 0.5
sd_decay = 0.3

# Toms
lt_pitch = 80.0
mt_pitch = 120.0
ht_pitch = 160.0
tom_sweep = 0.6
tom_decay = 0.5

# Noise / Cymbals
noise_tone = 3000.0
noise_level = 0.5
cymbal_decay = 0.8

voices = {}
serial = 0
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
    global master_level, click_level, bd_pitch, bd_sweep, bd_decay
    global sd_pitch, sd_sweep, sd_decay, lt_pitch, mt_pitch, ht_pitch
    global tom_sweep, tom_decay, noise_tone, noise_level, cymbal_decay
    
    k = key_of(channel, note_id, data0)
    
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        pitch = data0
        amp = master_level * value0
        
        notes_to_play = []
        
        click_env = synthio.Envelope(attack_time=0.001, decay_time=0.015, release_time=0.01, attack_level=1.0, sustain_level=0.0)
        click_hp = synthio.Biquad(synthio.FilterMode.HIGH_PASS, 3000.0, Q=1.0)
        
        # BD (35, 36)
        if pitch in (35, 36):
            env = synthio.Envelope(attack_time=0.001, decay_time=bd_decay, release_time=0.05, attack_level=1.0, sustain_level=0.0)
            drop = synthio.LFO(waveform=FALL, once=True, rate=15.0, scale=bd_sweep, interpolate=True)
            body = synthio.Note(bd_pitch, waveform=SINE, envelope=env, amplitude=amp, bend=drop)
            
            click = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=click_env, filter=click_hp, amplitude=amp * click_level)
            notes_to_play.extend([body, click])
            
        # SD (38, 40)
        elif pitch in (38, 40):
            env = synthio.Envelope(attack_time=0.001, decay_time=sd_decay, release_time=0.05, attack_level=1.0, sustain_level=0.0)
            drop = synthio.LFO(waveform=FALL, once=True, rate=20.0, scale=sd_sweep, interpolate=True)
            body = synthio.Note(sd_pitch, waveform=SINE, envelope=env, amplitude=amp * 0.7, bend=drop)
            
            noise_env = synthio.Envelope(attack_time=0.001, decay_time=sd_decay * 1.2, release_time=0.05, attack_level=1.0, sustain_level=0.0)
            noise_bp = synthio.Biquad(synthio.FilterMode.BAND_PASS, noise_tone, Q=1.0)
            noise_note = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=noise_env, filter=noise_bp, amplitude=amp * noise_level)
            
            click = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=click_env, filter=click_hp, amplitude=amp * click_level)
            notes_to_play.extend([body, noise_note, click])
            
        # Toms (41, 43, 45, 47, 48, 50)
        elif pitch in (41, 43, 45, 47, 48, 50):
            if pitch in (41, 43):
                tune = lt_pitch
            elif pitch in (45, 47):
                tune = mt_pitch
            else:
                tune = ht_pitch
            
            env = synthio.Envelope(attack_time=0.001, decay_time=tom_decay, release_time=0.05, attack_level=1.0, sustain_level=0.0)
            drop = synthio.LFO(waveform=FALL, once=True, rate=15.0, scale=tom_sweep, interpolate=True)
            body = synthio.Note(tune, waveform=SINE, envelope=env, amplitude=amp, bend=drop)
            
            noise_env = synthio.Envelope(attack_time=0.001, decay_time=tom_decay * 0.8, release_time=0.05, attack_level=1.0, sustain_level=0.0)
            noise_bp = synthio.Biquad(synthio.FilterMode.BAND_PASS, noise_tone * 0.8, Q=1.0)
            noise_note = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=noise_env, filter=noise_bp, amplitude=amp * noise_level * 0.5)
            
            click = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=click_env, filter=click_hp, amplitude=amp * click_level)
            notes_to_play.extend([body, noise_note, click])

        # Cymbals / Hats (42, 44, 46, 49, 51, 57, 59)
        elif pitch in (42, 44, 46, 49, 51, 57, 59):
            is_hat = pitch in (42, 44, 46)
            is_open = pitch == 46
            decay = cymbal_decay
            if is_hat:
                decay = 0.3 if is_open else 0.05
                
            env = synthio.Envelope(attack_time=0.001, decay_time=decay, release_time=0.1, attack_level=1.0, sustain_level=0.0)
            hp = synthio.Biquad(synthio.FilterMode.HIGH_PASS, noise_tone * (1.5 if is_hat else 1.0), Q=0.8)
            note = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env, filter=hp, amplitude=amp * noise_level)
            notes_to_play.append(note)

        # Fallback (other percussion)
        else:
            env = synthio.Envelope(attack_time=0.001, decay_time=0.1, release_time=0.05, attack_level=1.0, sustain_level=0.0)
            bp = synthio.Biquad(synthio.FilterMode.BAND_PASS, noise_tone, Q=1.0)
            note = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env, filter=bp, amplitude=amp * noise_level)
            click = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=click_env, filter=click_hp, amplitude=amp * click_level)
            notes_to_play.extend([note, click])

        if notes_to_play:
            trigger_voice(k, notes_to_play)

    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
            
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0: master_level = value0
        elif data0 == 1: click_level = value0
        elif data0 == 2: bd_pitch = logmap(value0, 30.0, 80.0)
        elif data0 == 3: bd_sweep = value0 * 2.0
        elif data0 == 4: bd_decay = logmap(value0, 0.1, 1.0)
        elif data0 == 5: sd_pitch = logmap(value0, 100.0, 300.0)
        elif data0 == 6: sd_sweep = value0 * 2.0
        elif data0 == 7: sd_decay = logmap(value0, 0.1, 0.8)
        elif data0 == 8: lt_pitch = logmap(value0, 50.0, 120.0)
        elif data0 == 9: mt_pitch = logmap(value0, 80.0, 160.0)
        elif data0 == 10: ht_pitch = logmap(value0, 120.0, 220.0)
        elif data0 == 11: tom_sweep = value0 * 2.0
        elif data0 == 12: tom_decay = logmap(value0, 0.1, 1.0)
        elif data0 == 13: noise_tone = logmap(value0, 1000.0, 8000.0)
        elif data0 == 14: noise_level = value0
        elif data0 == 15: cymbal_decay = logmap(value0, 0.2, 1.5)


vstaudio.on_event(handle_event)
