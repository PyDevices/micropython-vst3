# mpvst-macro-labels: Volume | Vowel A | Vowel B | Morph Speed | FM Index | Brightness | Amp Attack | Amp Decay | Amp Sustain | Amp Release | Master Tune

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

# Complex FM carrier base
WAVE_FM = make_table(((1, 1.0), (2, 0.5), (3, 0.2), (4, 0.1), (7, 0.05)))
FALL = array.array("h", (32767, 0))
SINE = make_table(((1, 1.0),))

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
vstaudio.output(synth)

# Macros
volume = 0.8
vowel_a = 0.0 # 0=A, 1=E, 2=I, 3=O, 4=U (simplified mapping)
vowel_b = 1.0
morph_speed = 0.5
fm_idx = 0.5
brightness = 0.8
amp_a = 0.05
amp_d = 1.0
amp_s = 0.8
amp_r = 1.0
master_tune = 1.0

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

def get_formant_freq(vowel_idx):
    # Rough approximation of A, E, I, O, U
    v = vowel_idx * 4.0
    if v < 1.0: return 800.0 # A
    elif v < 2.0: return 400.0 # E
    elif v < 3.0: return 300.0 # I
    elif v < 4.0: return 500.0 # O
    else: return 350.0 # U

def get_formant_freq2(vowel_idx):
    v = vowel_idx * 4.0
    if v < 1.0: return 1200.0
    elif v < 2.0: return 2000.0
    elif v < 3.0: return 2500.0
    elif v < 4.0: return 800.0
    else: return 600.0

def handle_event(event_type, channel, note_id, data0, value0, value1, sample_position):
    global volume, vowel_a, vowel_b, morph_speed, fm_idx, brightness
    global amp_a, amp_d, amp_s, amp_r, master_tune
    global serial
    
    k = key_of(channel, note_id, data0)
    
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        if len(voices) >= MAX_VOICES:
            steal_oldest()
            
        hz = synthio.midi_to_hz(data0 + value1) * master_tune
        amp = volume * value0
        
        env = synthio.Envelope(attack_time=amp_a, decay_time=amp_d, release_time=amp_r, attack_level=1.0, sustain_level=amp_s)
        
        # We morph from Vowel A to Vowel B using an LFO FALL
        f1_start = get_formant_freq(vowel_a)
        f1_end = get_formant_freq(vowel_b)
        f2_start = get_formant_freq2(vowel_a)
        f2_end = get_formant_freq2(vowel_b)
        
        diff1 = f1_end - f1_start
        diff2 = f2_end - f2_start
        
        # FALL ramps 1.0 -> 0.0 once, so output = end + (start - end) * FALL
        # sweeps from f_start at note-on down to f_end over morph_speed
        morph_lfo = synthio.LFO(waveform=FALL, once=True, rate=1.0 / max(0.01, morph_speed * 4.0), scale=1.0, interpolate=True)
        
        c1 = synthio.Math(synthio.MathOperation.SUM, f1_end, synthio.Math(synthio.MathOperation.SCALE_OFFSET, morph_lfo, diff1, 0.0), 0.0)
        c2 = synthio.Math(synthio.MathOperation.SUM, f2_end, synthio.Math(synthio.MathOperation.SCALE_OFFSET, morph_lfo, diff2, 0.0), 0.0)
        
        bp1 = synthio.Biquad(synthio.FilterMode.BAND_PASS, c1, Q=6.0)
        bp2 = synthio.Biquad(synthio.FilterMode.BAND_PASS, c2, Q=6.0)
        
        # True FM operators/algorithms aren't in reach here, so the FM engine
        # is approximated as: fast pitch modulation (sideband generation,
        # like real FM) run through formant filters (the real FS1R's actual
        # party trick). Brightness raises the modulation index rather than
        # just the volume, since a brighter FM tone is a harder-modulated one.
        fm_mod = synthio.LFO(waveform=SINE, rate=hz * 2.0, scale=fm_idx * (0.04 + brightness * 0.18)) if fm_idx > 0.01 else None

        n1 = synthio.Note(hz, waveform=WAVE_FM, envelope=env, filter=bp1, amplitude=amp * 0.6, bend=fm_mod, panning=-0.3)
        n2 = synthio.Note(hz, waveform=WAVE_FM, envelope=env, filter=bp2, amplitude=amp * 0.6, bend=fm_mod, panning=0.3)
        
        serial += 1
        voices[k] = ((n1, n2), serial)
        synth.press(n1)
        synth.press(n2)
            
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
        
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0: volume = value0
        elif data0 == 1: vowel_a = value0
        elif data0 == 2: vowel_b = value0
        elif data0 == 3: morph_speed = value0
        elif data0 == 4: fm_idx = value0
        elif data0 == 5: brightness = value0 * 2.0
        elif data0 == 6: amp_a = 0.001 + value0 * 2.0
        elif data0 == 7: amp_d = 0.05 + value0 * 4.0
        elif data0 == 8: amp_s = value0
        elif data0 == 9: amp_r = 0.01 + value0 * 4.0
        elif data0 == 10: master_tune = 0.95 + value0 * 0.1

vstaudio.on_event(handle_event)
