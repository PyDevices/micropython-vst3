# mpvst-macro-labels: Volume | Bite | Bark | Tremolo Rate | Tremolo Depth | Amp Attack | Amp Decay | Amp Sustain | Amp Release | Master Tune

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

# Reeds are grittier than tines
WAVE_REED = make_table(((1, 1.0), (2, 0.4), (3, 0.2), (4, 0.1), (5, 0.05)))
WAVE_BITE = make_table(((1, 1.0), (3, 0.8), (5, 0.6), (7, 0.4), (9, 0.2)))
SINE = make_table(((1, 1.0),))

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
vstaudio.output(synth)

# Macros
volume = 0.8
bite = 0.5
bark = 0.5
trem_rate = 4.0
trem_depth = 0.0
amp_a = 0.01
amp_d = 1.5
amp_s = 0.2
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
    global volume, bite, bark, trem_rate, trem_depth
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
        bite_env = synthio.Envelope(attack_time=0.001, decay_time=0.2, release_time=0.1, attack_level=1.0, sustain_level=0.0)
        
        # Velocity affects filter cutoff heavily for the "bark"
        cutoff = 1000.0 + (value0 * bark * 5000.0)
        lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, cutoff, Q=0.8)
        
        trem_lfo = synthio.LFO(waveform=SINE, rate=trem_rate, scale=trem_depth) if trem_depth > 0.01 else None
        
        o_reed = synthio.Note(hz, waveform=WAVE_REED, envelope=env, filter=lp, amplitude=amp * 0.6, ring_mod=trem_lfo)
        o_bite = synthio.Note(hz, waveform=WAVE_BITE, envelope=bite_env, filter=lp, amplitude=amp * bite * 0.4, ring_mod=trem_lfo)
        
        serial += 1
        voices[k] = ((o_reed, o_bite), serial)
        synth.press(o_reed)
        synth.press(o_bite)
            
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
        
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0: volume = value0
        elif data0 == 1: bite = value0 * 2.0
        elif data0 == 2: bark = value0
        elif data0 == 3: trem_rate = 0.1 + value0 * 10.0
        elif data0 == 4: trem_depth = value0
        elif data0 == 5: amp_a = 0.001 + value0 * 0.5
        elif data0 == 6: amp_d = 0.5 + value0 * 3.0
        elif data0 == 7: amp_s = value0
        elif data0 == 8: amp_r = 0.1 + value0 * 2.0
        elif data0 == 9: master_tune = 0.95 + value0 * 0.1

vstaudio.on_event(handle_event)
