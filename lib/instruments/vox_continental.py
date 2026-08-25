# mpvst-macro-labels: Volume | Drawbar 16 | Drawbar 8 | Drawbar 4 | Drawbar IV | Vibrato Rate | Vibrato Depth | Brilliance | Master Tune

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

# Transistor organs use a brighter, buzzier waveform than B3 sine waves
WAVE_TRANS = make_table(((1, 1.0), (2, 0.5), (3, 0.33), (4, 0.25)))
SINE = make_table(((1, 1.0),))

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
vstaudio.output(synth)

# Macros
volume = 0.8
db16 = 1.0
db8 = 1.0
db4 = 0.8
db_iv = 0.5
vib_rate = 6.0
vib_depth = 0.0
brilliance = 0.8
master_tune = 1.0

voices = {}
serial = 0
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

def handle_event(event_type, channel, note_id, data0, value0, value1, sample_position):
    global volume, db16, db8, db4, db_iv, vib_rate, vib_depth, brilliance, master_tune
    global serial
    
    k = key_of(channel, note_id, data0)
    
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        if len(voices) >= MAX_VOICES:
            steal_oldest()
            
        hz = synthio.midi_to_hz(data0 + value1) * master_tune
        amp = volume * value0
        
        env = synthio.Envelope(attack_time=0.01, decay_time=0.1, release_time=0.1, attack_level=1.0, sustain_level=1.0)
        
        cutoff = 1000.0 + (brilliance * 6000.0)
        lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, cutoff, Q=0.5)
        
        vib_lfo = synthio.LFO(waveform=SINE, rate=vib_rate, scale=vib_depth * 0.03) if vib_depth > 0.01 else None
        
        notes = []
        if db16 > 0.01: notes.append(synthio.Note(hz * 0.5, waveform=WAVE_TRANS, envelope=env, filter=lp, amplitude=amp * db16 * 0.25, bend=vib_lfo))
        if db8 > 0.01: notes.append(synthio.Note(hz, waveform=WAVE_TRANS, envelope=env, filter=lp, amplitude=amp * db8 * 0.25, bend=vib_lfo))
        if db4 > 0.01: notes.append(synthio.Note(hz * 2.0, waveform=WAVE_TRANS, envelope=env, filter=lp, amplitude=amp * db4 * 0.25, bend=vib_lfo))
        if db_iv > 0.01: notes.append(synthio.Note(hz * 2.99, waveform=WAVE_TRANS, envelope=env, filter=lp, amplitude=amp * db_iv * 0.25, bend=vib_lfo))
        
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
        elif data0 == 4: db_iv = value0
        elif data0 == 5: vib_rate = 0.1 + value0 * 10.0
        elif data0 == 6: vib_depth = value0
        elif data0 == 7: brilliance = value0
        elif data0 == 8: master_tune = 0.95 + value0 * 0.1

vstaudio.on_event(handle_event)
