# mpvst-macro-labels: Level | Accent | BD Tune | BD Attack | BD Decay | SD Tune | SD Tone | SD Snappy | LT Tune | MT Tune | HT Tune | Tom Decay | Clap/Rim | CH Decay | OH Decay | Cymbal Tune

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
SQUARE = make_table([(n, 1.0 / n) for n in range(1, 23, 2)])
NOISE = noise_table(seed=909090)
NOISE_HZ = SR / 8192.0
FALL = array.array("h", (32767, 0))

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
vstaudio.output(synth)

# Master params
master_level = 0.8
accent_level = 0.5

# BD params
bd_tune = 50.0
bd_attack = 0.5
bd_decay = 0.4

# SD params
sd_tune = 180.0
sd_tone = 1500.0
sd_snappy = 0.5

# Toms
lt_tune = 90.0
mt_tune = 130.0
ht_tune = 180.0
tom_decay = 0.4

# Others
clap_rim_level = 0.5
ch_decay = 0.05
oh_decay = 0.4
cym_tune = 6000.0

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
    global master_level, accent_level, bd_tune, bd_attack, bd_decay
    global sd_tune, sd_tone, sd_snappy, lt_tune, mt_tune, ht_tune, tom_decay
    global clap_rim_level, ch_decay, oh_decay, cym_tune
    
    k = key_of(channel, note_id, data0)
    
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        pitch = data0
        vel = value0
        amp = master_level * (vel + accent_level * (1.0 if vel > 0.8 else 0.0))
        
        notes_to_play = []
        
        # BD (35, 36)
        if pitch in (35, 36):
            env = synthio.Envelope(attack_time=0.001, decay_time=bd_decay, release_time=0.05, attack_level=1.0, sustain_level=0.0)
            drop = synthio.LFO(waveform=FALL, once=True, rate=25.0, scale=0.8, interpolate=True)
            lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, bd_tune * 5.0, Q=0.7)
            body = synthio.Note(bd_tune, waveform=SINE, envelope=env, filter=lp, amplitude=amp, bend=drop)
            
            click_env = synthio.Envelope(attack_time=0.001, decay_time=0.015, release_time=0.01, attack_level=1.0, sustain_level=0.0)
            click_hp = synthio.Biquad(synthio.FilterMode.HIGH_PASS, 4000.0, Q=1.0)
            click = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=click_env, filter=click_hp, amplitude=amp * bd_attack)
            
            notes_to_play.extend([body, click])
            
        # SD (38, 40)
        elif pitch in (38, 40):
            body_env = synthio.Envelope(attack_time=0.001, decay_time=0.1, release_time=0.05, attack_level=1.0, sustain_level=0.0)
            drop = synthio.LFO(waveform=FALL, once=True, rate=35.0, scale=0.3, interpolate=True)
            body = synthio.Note(sd_tune, waveform=SINE, envelope=body_env, amplitude=amp*0.8, bend=drop)
            
            snare_env = synthio.Envelope(attack_time=0.001, decay_time=0.15, release_time=0.1, attack_level=1.0, sustain_level=0.0)
            snare_hp = synthio.Biquad(synthio.FilterMode.HIGH_PASS, sd_tone, Q=1.0)
            snare = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=snare_env, filter=snare_hp, amplitude=amp * sd_snappy)
            
            notes_to_play.extend([body, snare])
            
        # Toms (41, 43, 45, 47, 48, 50)
        elif pitch in (41, 43, 45, 47, 48, 50):
            if pitch in (41, 43):
                tune = lt_tune
            elif pitch in (45, 47):
                tune = mt_tune
            else:
                tune = ht_tune
            
            env = synthio.Envelope(attack_time=0.001, decay_time=tom_decay, release_time=0.1, attack_level=1.0, sustain_level=0.0)
            drop = synthio.LFO(waveform=FALL, once=True, rate=20.0, scale=0.4, interpolate=True)
            note = synthio.Note(tune, waveform=SINE, envelope=env, amplitude=amp, bend=drop)
            
            noise_env = synthio.Envelope(attack_time=0.001, decay_time=0.05, release_time=0.02, attack_level=1.0, sustain_level=0.0)
            noise_bp = synthio.Biquad(synthio.FilterMode.BAND_PASS, tune * 8.0, Q=1.0)
            noise_click = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=noise_env, filter=noise_bp, amplitude=amp * 0.2)
            
            notes_to_play.extend([note, noise_click])
            
        # Hats (42, 44, 46)
        elif pitch in (42, 44, 46):
            is_open = pitch == 46
            if not is_open:
                for ok in open_hat_keys:
                    release_voice(ok)
                open_hat_keys.clear()
                
            env = synthio.Envelope(attack_time=0.001, decay_time=oh_decay if is_open else ch_decay, release_time=0.05, attack_level=1.0, sustain_level=0.0)
            hp = synthio.Biquad(synthio.FilterMode.HIGH_PASS, cym_tune, Q=0.8)
            note = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env, filter=hp, amplitude=amp * 0.7)
            notes_to_play.append(note)
            if is_open:
                open_hat_keys.append(k)
                
        # Cymbals (Crash 49/57, Ride 51/59)
        elif pitch in (49, 51, 57, 59):
            is_ride = pitch in (51, 59)
            decay = 1.5 if is_ride else 0.8
            env = synthio.Envelope(attack_time=0.001, decay_time=decay, release_time=0.3, attack_level=1.0, sustain_level=0.0)
            bp = synthio.Biquad(synthio.FilterMode.BAND_PASS, cym_tune * (1.5 if is_ride else 1.0), Q=0.5)
            hp = synthio.Biquad(synthio.FilterMode.HIGH_PASS, 8000.0, Q=0.7)
            note1 = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env, filter=bp, amplitude=amp * 0.5)
            note2 = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env, filter=hp, amplitude=amp * 0.5)
            notes_to_play.extend([note1, note2])

        # Clap (39)
        elif pitch == 39:
            bp = synthio.Biquad(synthio.FilterMode.BAND_PASS, 1200.0, Q=1.0)
            for i, attack in enumerate([0.001, 0.015, 0.03]):
                env = synthio.Envelope(attack_time=attack, decay_time=0.3, release_time=0.1, attack_level=1.0, sustain_level=0.0)
                notes_to_play.append(synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env, filter=bp, amplitude=amp * clap_rim_level * (1.0 - i*0.2)))

        # Rimshot (37)
        elif pitch == 37:
            env = synthio.Envelope(attack_time=0.001, decay_time=0.05, release_time=0.02, attack_level=1.0, sustain_level=0.0)
            bp = synthio.Biquad(synthio.FilterMode.BAND_PASS, 1600.0, Q=2.0)
            note1 = synthio.Note(450.0, waveform=TRIANGLE, envelope=env, filter=bp, amplitude=amp * clap_rim_level * 0.5)
            note2 = synthio.Note(1600.0, waveform=TRIANGLE, envelope=env, filter=bp, amplitude=amp * clap_rim_level * 0.5)
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
        elif data0 == 1: accent_level = value0
        elif data0 == 2: bd_tune = logmap(value0, 40.0, 70.0)
        elif data0 == 3: bd_attack = value0
        elif data0 == 4: bd_decay = logmap(value0, 0.1, 1.0)
        elif data0 == 5: sd_tune = logmap(value0, 120.0, 300.0)
        elif data0 == 6: sd_tone = logmap(value0, 800.0, 3000.0)
        elif data0 == 7: sd_snappy = value0
        elif data0 == 8: lt_tune = logmap(value0, 60.0, 120.0)
        elif data0 == 9: mt_tune = logmap(value0, 100.0, 160.0)
        elif data0 == 10: ht_tune = logmap(value0, 140.0, 220.0)
        elif data0 == 11: tom_decay = logmap(value0, 0.1, 0.8)
        elif data0 == 12: clap_rim_level = value0
        elif data0 == 13: ch_decay = logmap(value0, 0.02, 0.15)
        elif data0 == 14: oh_decay = logmap(value0, 0.1, 0.8)
        elif data0 == 15: cym_tune = logmap(value0, 4000.0, 8000.0)


# Patch 1 (Program Change 0) is the sound this script's module-level
# defaults describe, so a fresh instance and Patch 1 are the same thing.
# piece.py also reads it: a macro a composition does not set resolves here
# rather than to 0.5. Derived by tools/derive_patches.py - see that file
# before editing these numbers by hand.
PATCHES = {
    0: ("Init", (
        0.8, 0.5, 0.398744, 0.5, 0.60206, 0.442507, 0.475586, 0.5,
        0.584963, 0.558218, 0.556024, 0.666667, 0.5, 0.454757,
        0.666667, 0.584963)),
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

