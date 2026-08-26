# mpvst-macro-labels: Volume | Pluck Attack | Mellow Tone | Decay Time | Vibrato Rate | Vibrato Depth | Amp Attack | Amp Sustain | Amp Release | Master Tune

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

SINE = make_table(((1, 1.0),))
WAVE_PIANET = make_table(((1, 1.0), (3, 0.2)))
WAVE_PLUCK = make_table(((1, 1.0), (2, 0.8), (3, 0.6), (4, 0.4), (5, 0.2)))

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
vstaudio.output(synth)

# Macros
volume = 0.8
pluck_attack = 0.5
mellow_tone = 0.5
decay_time = 1.5
vib_rate = 5.0
vib_depth = 0.0
amp_a = 0.01
amp_s = 0.1
amp_r = 0.4
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

def steal_oldest():
    oldest = None
    for k in voices:
        if oldest is None or voices[k][1] < voices[oldest][1]:
            oldest = k
    if oldest is not None:
        release_voice(oldest)

def handle_event(event_type, channel, note_id, data0, value0, value1, sample_position):
    global volume, pluck_attack, mellow_tone, decay_time, vib_rate, vib_depth
    global amp_a, amp_s, amp_r, master_tune
    global serial
    
    k = key_of(channel, note_id, data0)
    
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        if len(voices) >= MAX_VOICES:
            steal_oldest()
            
        hz = synthio.midi_to_hz(data0 + value1) * master_tune
        amp = volume * value0
        
        env = synthio.Envelope(attack_time=amp_a, decay_time=decay_time, release_time=amp_r, attack_level=1.0, sustain_level=amp_s)
        pluck_env = synthio.Envelope(attack_time=0.001, decay_time=0.1, release_time=0.05, attack_level=1.0, sustain_level=0.0)
        
        cutoff = 1000.0 + ((1.0 - mellow_tone) * 4000.0)
        lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, cutoff, Q=0.7)
        
        vib_lfo = synthio.LFO(waveform=SINE, rate=vib_rate, scale=vib_depth * 0.025) if vib_depth > 0.01 else None
        
        o_body = synthio.Note(hz, waveform=WAVE_PIANET, envelope=env, filter=lp, amplitude=amp * 0.7, bend=vib_lfo)
        o_pluck = synthio.Note(hz, waveform=WAVE_PLUCK, envelope=pluck_env, filter=lp, amplitude=amp * pluck_attack * 0.4, bend=vib_lfo)
        
        serial += 1
        voices[k] = ((o_body, o_pluck), serial)
        synth.press(o_body)
        synth.press(o_pluck)
            
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
        
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0: volume = value0
        elif data0 == 1: pluck_attack = value0
        elif data0 == 2: mellow_tone = value0
        elif data0 == 3: decay_time = 0.5 + value0 * 3.0
        elif data0 == 4: vib_rate = 0.1 + value0 * 10.0
        elif data0 == 5: vib_depth = value0
        elif data0 == 6: amp_a = 0.001 + value0 * 0.2
        elif data0 == 7: amp_s = value0
        elif data0 == 8: amp_r = 0.05 + value0 * 2.0
        elif data0 == 9: master_tune = 0.95 + value0 * 0.1

vstaudio.on_event(handle_event)
