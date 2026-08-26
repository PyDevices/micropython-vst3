# mpvst-macro-labels: Level | Accent | BD Decay | BD Pitch | SD Snappy | SD Pitch | Rim Level | Bongo Hi | Bongo Lo | Claves Level | Cowbell Level | Guiro Level | Tamb Level | Maracas Level | Metal Beat | Hat Tone

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
SQUARE = make_table([(n, 1.0 / n) for n in range(1, 15, 2)])
NOISE = noise_table(seed=13579)
NOISE_HZ = SR / 8192.0
FALL = array.array("h", (32767, 0))

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
vstaudio.output(synth)

# Master params
master_level = 0.8
accent_level = 0.5

# Params
bd_decay = 0.2
bd_pitch = 65.0
sd_snappy = 0.4
sd_pitch = 240.0
rim_level = 0.8
bongo_hi = 450.0
bongo_lo = 280.0
claves_level = 0.8
cowbell_level = 0.8
guiro_level = 0.8
tamb_level = 0.8
maracas_level = 0.8
metal_beat = 0.8
hat_tone = 7000.0

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
    global master_level, accent_level, bd_decay, bd_pitch, sd_snappy, sd_pitch
    global rim_level, bongo_hi, bongo_lo, claves_level, cowbell_level
    global guiro_level, tamb_level, maracas_level, metal_beat, hat_tone
    
    k = key_of(channel, note_id, data0)
    
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        pitch = data0
        vel = value0
        amp = master_level * (vel + accent_level * (1.0 if vel > 0.8 else 0.0))
        
        notes_to_play = []
        
        # BD
        if pitch in (35, 36):
            env = synthio.Envelope(attack_time=0.001, decay_time=bd_decay, release_time=0.05, attack_level=1.0, sustain_level=0.0)
            lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, bd_pitch * 2.0, Q=0.8)
            note = synthio.Note(bd_pitch, waveform=SINE, envelope=env, filter=lp, amplitude=amp)
            notes_to_play.append(note)
            
        # SD
        elif pitch in (38, 40):
            body_env = synthio.Envelope(attack_time=0.001, decay_time=0.08, release_time=0.05, attack_level=1.0, sustain_level=0.0)
            body = synthio.Note(sd_pitch, waveform=SQUARE, envelope=body_env, amplitude=amp*0.5)
            
            snare_env = synthio.Envelope(attack_time=0.001, decay_time=0.1, release_time=0.05, attack_level=1.0, sustain_level=0.0)
            snare_hp = synthio.Biquad(synthio.FilterMode.HIGH_PASS, 3000.0, Q=1.0)
            snare = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=snare_env, filter=snare_hp, amplitude=amp * sd_snappy)
            
            notes_to_play.extend([body, snare])
            
        # Bongos (High 60, Low 61)
        elif pitch in (60, 61):
            tune = bongo_hi if pitch == 60 else bongo_lo
            env = synthio.Envelope(attack_time=0.001, decay_time=0.2, release_time=0.05, attack_level=1.0, sustain_level=0.0)
            note = synthio.Note(tune, waveform=SINE, envelope=env, amplitude=amp)
            notes_to_play.append(note)
            
        # Rim (37)
        elif pitch == 37:
            env = synthio.Envelope(attack_time=0.001, decay_time=0.02, release_time=0.02, attack_level=1.0, sustain_level=0.0)
            bp = synthio.Biquad(synthio.FilterMode.BAND_PASS, 1200.0, Q=2.0)
            note = synthio.Note(1200.0, waveform=SQUARE, envelope=env, filter=bp, amplitude=amp * rim_level)
            notes_to_play.append(note)

        # Claves (75)
        elif pitch == 75:
            env = synthio.Envelope(attack_time=0.001, decay_time=0.05, release_time=0.02, attack_level=1.0, sustain_level=0.0)
            bp = synthio.Biquad(synthio.FilterMode.BAND_PASS, 2200.0, Q=3.0)
            note = synthio.Note(2200.0, waveform=SINE, envelope=env, filter=bp, amplitude=amp * claves_level)
            notes_to_play.append(note)

        # Cowbell (56)
        elif pitch == 56:
            env = synthio.Envelope(attack_time=0.001, decay_time=0.2, release_time=0.1, attack_level=1.0, sustain_level=0.0)
            bp = synthio.Biquad(synthio.FilterMode.BAND_PASS, 800.0, Q=1.5)
            note = synthio.Note(800.0, waveform=SQUARE, envelope=env, filter=bp, amplitude=amp * cowbell_level)
            notes_to_play.append(note)

        # Guiro (58) - a scraping ratchet, not a single swell: stack short
        # staggered noise clicks so the ridges of the scrape are audible
        elif pitch == 58:
            bp = synthio.Biquad(synthio.FilterMode.BAND_PASS, 3500.0, Q=1.0)
            for i, attack in enumerate((0.001, 0.02, 0.04, 0.06, 0.08)):
                env = synthio.Envelope(attack_time=attack, decay_time=0.03, release_time=0.02, attack_level=1.0, sustain_level=0.0)
                notes_to_play.append(synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env, filter=bp, amplitude=amp * guiro_level * (1.0 - i * 0.12)))

        # Tambourine (54)
        elif pitch == 54:
            env = synthio.Envelope(attack_time=0.001, decay_time=0.15, release_time=0.05, attack_level=1.0, sustain_level=0.0)
            hp = synthio.Biquad(synthio.FilterMode.HIGH_PASS, 6000.0, Q=0.8)
            note = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env, filter=hp, amplitude=amp * tamb_level)
            notes_to_play.append(note)
            
        # Maracas (70)
        elif pitch == 70:
            env = synthio.Envelope(attack_time=0.001, decay_time=0.05, release_time=0.02, attack_level=1.0, sustain_level=0.0)
            hp = synthio.Biquad(synthio.FilterMode.HIGH_PASS, 5000.0, Q=1.0)
            note = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env, filter=hp, amplitude=amp * maracas_level)
            notes_to_play.append(note)

        # Metal Beat (e.g. 55)
        elif pitch == 55:
            env = synthio.Envelope(attack_time=0.001, decay_time=0.08, release_time=0.02, attack_level=1.0, sustain_level=0.0)
            hp = synthio.Biquad(synthio.FilterMode.HIGH_PASS, 4000.0, Q=1.5)
            note = synthio.Note(600.0, waveform=SQUARE, envelope=env, filter=hp, amplitude=amp * metal_beat)
            notes_to_play.append(note)
            
        # Hats / Cymbal (42, 44, 46, 49, 51)
        elif pitch in (42, 44, 46, 49, 51, 57, 59):
            if pitch in (42, 44):
                decay = 0.05
            elif pitch == 46:
                decay = 0.3
            else:
                decay = 0.8
            env = synthio.Envelope(attack_time=0.001, decay_time=decay, release_time=0.1, attack_level=1.0, sustain_level=0.0)
            hp = synthio.Biquad(synthio.FilterMode.HIGH_PASS, hat_tone, Q=0.7)
            note = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env, filter=hp, amplitude=amp * 0.7)
            notes_to_play.append(note)
            
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
            
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0: master_level = value0
        elif data0 == 1: accent_level = value0
        elif data0 == 2: bd_decay = logmap(value0, 0.1, 0.6)
        elif data0 == 3: bd_pitch = logmap(value0, 40.0, 90.0)
        elif data0 == 4: sd_snappy = value0
        elif data0 == 5: sd_pitch = logmap(value0, 150.0, 400.0)
        elif data0 == 6: rim_level = value0
        elif data0 == 7: bongo_hi = logmap(value0, 300.0, 600.0)
        elif data0 == 8: bongo_lo = logmap(value0, 200.0, 400.0)
        elif data0 == 9: claves_level = value0
        elif data0 == 10: cowbell_level = value0
        elif data0 == 11: guiro_level = value0
        elif data0 == 12: tamb_level = value0
        elif data0 == 13: maracas_level = value0
        elif data0 == 14: metal_beat = value0
        elif data0 == 15: hat_tone = logmap(value0, 4000.0, 10000.0)


# Patch 1 (Program Change 0) is the sound this script's module-level
# defaults describe, so a fresh instance and Patch 1 are the same thing.
# piece.py also reads it: a macro a composition does not set resolves here
# rather than to 0.5. Derived by tools/derive_patches.py - see that file
# before editing these numbers by hand.
PATCHES = {
    0: ("Init", (
        0.8, 0.5, 0.386853, 0.598705, 0.4, 0.47919, 0.8, 0.584963,
        0.485427, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.61074)),
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

