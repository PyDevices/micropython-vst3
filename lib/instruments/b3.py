# mpvst-macro-labels: Volume | Drawbar 16 | Drawbar 8 | Drawbar 4 | Drawbar 2 | Perc Level | Perc Decay | Key Click | Leslie Fast | Overdrive | Master Tune

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


def noise_table(length=8192, seed=1234):
    out = array.array("h", bytearray(length * 2))
    state = seed
    for i in range(length):
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        out[i] = ((state >> 15) & 0xFFFF) - 32768
    return out

SINE = make_table(((1, 1.0),))
NOISE = noise_table()
NOISE_HZ = SR / 8192.0

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
vstaudio.output(synth)

# Macros
volume = 0.8
db16 = 1.0
db8 = 1.0
db4 = 0.5
db2 = 0.2
perc_lvl = 0.5
perc_dec = 0.3
key_click = 0.3
leslie_fast = 0.0
overdrive = 1.0
master_tune = 1.0

voices = {}
serial = 0
MAX_VOICES = 8 # B3 has heavy polyphony usually, but we need to limit to avoid CPU overload due to additive oscillators

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

def handle_event(event_type, channel, note_id, data0, value0, value1, sample_position):
    global volume, db16, db8, db4, db2, perc_lvl, perc_dec, key_click, leslie_fast, overdrive, master_tune
    global serial
    
    k = key_of(channel, note_id, data0)
    
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        if len(voices) >= MAX_VOICES:
            steal_oldest()
            
        hz = synthio.midi_to_hz(data0 + value1) * master_tune
        amp = volume * value0 * overdrive
        
        env = synthio.Envelope(attack_time=0.01, decay_time=0.1, release_time=0.05, attack_level=1.0, sustain_level=1.0)
        perc_env = synthio.Envelope(attack_time=0.001, decay_time=perc_dec, release_time=0.05, attack_level=1.0, sustain_level=0.0)
        click_env = synthio.Envelope(attack_time=0.001, decay_time=0.02, release_time=0.02, attack_level=1.0, sustain_level=0.0)
        
        leslie_rate = 6.0 if leslie_fast > 0.5 else 1.0
        leslie_wave = ring_depth_table(0.3)
        leslie_vib = synthio.LFO(waveform=SINE, rate=leslie_rate * 1.1, scale=0.02)
        
        notes = []
        # Drawbars: 16' (sub), 8' (fund), 4' (2nd harm), 2' (4th harm)
        if db16 > 0.01: notes.append(synthio.Note(hz * 0.5, waveform=SINE, envelope=env, amplitude=amp * db16 * 0.25, ring_frequency=leslie_rate, ring_waveform=leslie_wave, bend=leslie_vib, panning=-0.2))
        if db8 > 0.01: notes.append(synthio.Note(hz, waveform=SINE, envelope=env, amplitude=amp * db8 * 0.25, ring_frequency=leslie_rate, ring_waveform=leslie_wave, bend=leslie_vib, panning=0.2))
        if db4 > 0.01: notes.append(synthio.Note(hz * 2.0, waveform=SINE, envelope=env, amplitude=amp * db4 * 0.2, ring_frequency=leslie_rate, ring_waveform=leslie_wave, bend=leslie_vib, panning=-0.1))
        if db2 > 0.01: notes.append(synthio.Note(hz * 4.0, waveform=SINE, envelope=env, amplitude=amp * db2 * 0.15, ring_frequency=leslie_rate, ring_waveform=leslie_wave, bend=leslie_vib, panning=0.1))
        
        # 3rd harmonic percussion
        if perc_lvl > 0.01: notes.append(synthio.Note(hz * 3.0, waveform=SINE, envelope=perc_env, amplitude=amp * perc_lvl * 0.4, ring_frequency=leslie_rate, ring_waveform=leslie_wave, bend=leslie_vib))
        
        # Key click
        if key_click > 0.01:
            hp = synthio.Biquad(synthio.FilterMode.HIGH_PASS, 5000.0, Q=1.0)
            notes.append(synthio.Note(NOISE_HZ, waveform=NOISE, envelope=click_env, filter=hp, amplitude=amp * key_click * 0.3))
        
        serial += 1
        voices[k] = (tuple(notes), serial)
        for n in notes:
            synth.press(n)
            
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
        
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0: volume = value0
        elif data0 == 1: db16 = value0
        elif data0 == 2: db8 = value0
        elif data0 == 3: db4 = value0
        elif data0 == 4: db2 = value0
        elif data0 == 5: perc_lvl = value0
        elif data0 == 6: perc_dec = 0.05 + value0 * 1.0
        elif data0 == 7: key_click = value0
        elif data0 == 8: leslie_fast = value0
        elif data0 == 9: overdrive = 1.0 + value0 * 2.0
        elif data0 == 10: master_tune = 0.95 + value0 * 0.1

vstaudio.on_event(handle_event)
