# mpvst-macro-labels: Volume | Tine Level | Body Level | Tremolo Rate | Tremolo Depth | Overdrive | Tone | Amp Attack | Amp Decay | Amp Sustain | Amp Release | Key-Off Noise | Master Tune

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

def ring_depth_table(depth, length=256):
    # A ring-modulation waveform biased between unity (depth=0, no audible
    # effect) and a full bipolar sine (depth=1, true ring modulation). At
    # ring_frequency rates below ~20Hz this reads as tremolo.
    out = array.array("h", bytearray(length * 2))
    for i in range(length):
        s = math.sin(TAU * i / length)
        v = (1.0 - depth) + depth * s
        out[i] = int(32767 * v)
    return out


# Body (warm fundamental)
WAVE_BODY = make_table(((1, 1.0), (3, 0.1)))
# Tine (metallic bell attack)
WAVE_TINE = make_table(((1, 1.0), (4, 0.8), (7, 0.5), (14, 0.2)))
# Noise for key off
def noise_table(length=8192, seed=1234):
    out = array.array("h", bytearray(length * 2))
    state = seed
    for i in range(length):
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        out[i] = ((state >> 15) & 0xFFFF) - 32768
    return out

NOISE = noise_table()
NOISE_HZ = SR / 8192.0
SINE = make_table(((1, 1.0),))

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
vstaudio.output(synth)

# Macros
volume = 0.8
tine_lvl = 0.8
body_lvl = 1.0
trem_rate = 3.0
trem_depth = 0.0
overdrive = 1.0
tone = 3000.0
amp_a = 0.01
amp_d = 2.0
amp_s = 0.2
amp_r = 0.5
key_off = 0.1
master_tune = 1.0

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
        # play key off noise
        if key_off > 0.01:
            env = synthio.Envelope(attack_time=0.001, decay_time=0.1, release_time=0.1, attack_level=1.0, sustain_level=0.0)
            bp = synthio.Biquad(synthio.FilterMode.BAND_PASS, 500.0, Q=1.0)
            n = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env, filter=bp, amplitude=volume * key_off * 0.2)
            synth.press(n)
            synth.release(n) # let envelope play out

def steal_oldest():
    oldest = None
    for k in voices:
        if oldest is None or voices[k][1] < voices[oldest][1]:
            oldest = k
    if oldest is not None:
        release_voice(oldest)

def handle_event(event_type, channel, note_id, data0, value0, value1, sample_position):
    global volume, tine_lvl, body_lvl, trem_rate, trem_depth, overdrive, tone
    global amp_a, amp_d, amp_s, amp_r, key_off, master_tune
    global serial
    
    k = key_of(channel, note_id, data0)
    
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        if len(voices) >= MAX_VOICES:
            steal_oldest()
            
        hz = synthio.midi_to_hz(data0 + value1) * master_tune
        amp = volume * value0 * overdrive
        
        env = synthio.Envelope(attack_time=amp_a, decay_time=amp_d, release_time=amp_r, attack_level=1.0, sustain_level=amp_s)
        tine_env = synthio.Envelope(attack_time=0.001, decay_time=0.3, release_time=0.1, attack_level=1.0, sustain_level=0.0)
        
        lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, tone, Q=0.7)
        
        # True stereo tremolo needs per-channel phase; ring-mod tremolo on
        # a shared modulator plus opposite panning gets an auto-pan feel.
        trem_wave = ring_depth_table(trem_depth) if trem_depth > 0.01 else None
        
        # Note panning
        pan_l = -0.3
        pan_r = 0.3
        
        o_body = synthio.Note(hz, waveform=WAVE_BODY, envelope=env, filter=lp, amplitude=amp * body_lvl * 0.5, ring_frequency=trem_rate, ring_waveform=trem_wave, panning=pan_l)
        o_tine = synthio.Note(hz, waveform=WAVE_TINE, envelope=tine_env, filter=lp, amplitude=amp * tine_lvl * 0.4, ring_frequency=trem_rate, ring_waveform=trem_wave, panning=pan_r)
        
        serial += 1
        voices[k] = ((o_body, o_tine), serial)
        synth.press(o_body)
        synth.press(o_tine)
            
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
        
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0: volume = value0
        elif data0 == 1: tine_lvl = value0 * 2.0
        elif data0 == 2: body_lvl = value0 * 2.0
        elif data0 == 3: trem_rate = 0.1 + value0 * 10.0
        elif data0 == 4: trem_depth = value0
        elif data0 == 5: overdrive = 1.0 + value0 * 2.0
        elif data0 == 6: tone = 500.0 + value0 * 5000.0
        elif data0 == 7: amp_a = 0.001 + value0 * 0.5
        elif data0 == 8: amp_d = 0.5 + value0 * 4.0
        elif data0 == 9: amp_s = value0
        elif data0 == 10: amp_r = 0.1 + value0 * 2.0
        elif data0 == 11: key_off = value0
        elif data0 == 12: master_tune = 0.95 + value0 * 0.1

vstaudio.on_event(handle_event)
