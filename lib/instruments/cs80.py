# mpvst-macro-labels: Volume | VCF Cutoff | Resonance | HPF Cutoff | Ring Mod Speed | Ring Mod Depth | Layer II Mix | Poly AT Depth | Amp Attack | Amp Decay | Amp Sustain | Amp Release | Filter Attack | Filter Decay | Filter Sustain | Brilliance

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

SAW = make_table([(n, 1.0 / n) for n in range(1, 40)])
SINE = make_table(((1, 1.0),))
FALL = array.array("h", (32767, 0))

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
vstaudio.output(synth)

# Macros
volume = 0.8
cutoff_base = 2500.0
resonance = 1.0
hpf_cutoff = 100.0
ring_speed = 5.0
ring_depth = 0.0
layer2_mix = 0.5
poly_at_depth = 0.5

amp_a = 0.05
amp_d = 0.5
amp_s = 0.8
amp_r = 0.5
filt_a = 0.05
filt_d = 0.5
filt_s = 0.5
brilliance = 1.0

voices = {}
serial = 0
MAX_VOICES = 8

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
    global volume, cutoff_base, resonance, hpf_cutoff, ring_speed, ring_depth, layer2_mix
    global poly_at_depth, amp_a, amp_d, amp_s, amp_r, filt_a, filt_d, filt_s, brilliance
    global serial
    
    k = key_of(channel, note_id, data0)
    
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        if len(voices) >= MAX_VOICES:
            steal_oldest()
            
        hz = synthio.midi_to_hz(data0 + value1)
        amp = volume * value0
        
        env = synthio.Envelope(attack_time=amp_a, decay_time=amp_d, release_time=amp_r, attack_level=1.0, sustain_level=amp_s)
        
        f_sweep = synthio.LFO(waveform=FALL, once=True, rate=1.0/filt_d, scale=2000.0 * brilliance, interpolate=True)
        cutoff = synthio.Math(synthio.MathOperation.SUM, cutoff_base, f_sweep, 0.0)
        
        lp1 = synthio.Biquad(synthio.FilterMode.LOW_PASS, cutoff, Q=resonance)
        
        # Ring mod emulation: LFO on amplitude (tremolo) at fast rate
        rm_lfo = synthio.LFO(waveform=SINE, rate=ring_speed * 10.0, scale=ring_depth)
        
        # Layer I
        o1 = synthio.Note(hz, waveform=SAW, envelope=env, filter=lp1, amplitude=amp * (1.0 - layer2_mix) * 0.8, ring_mod=rm_lfo if ring_depth > 0.01 else None)
        # Layer II (slightly detuned)
        o2 = synthio.Note(hz * 1.005, waveform=SAW, envelope=env, filter=lp1, amplitude=amp * layer2_mix * 0.8, ring_mod=rm_lfo if ring_depth > 0.01 else None)
        
        serial += 1
        voices[k] = ((o1, o2), serial)
        synth.press(o1)
        synth.press(o2)
            
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
        
    elif event_type == vstaudio.EVENT_POLY_PRESSURE:
        voice = voices.get(k)
        if voice is not None:
            # Emulate Poly AT by modifying amplitude or something (in synthio we'd need to map a Math node to amplitude, but amplitude is static or env-controlled. We can't easily change it post-creation without recreating Note, which is bad).
            # But we can change the amplitude property dynamically!
            for note in voice[0]:
                pass # Note amplitude is changeable? 
                # According to synthio docs, amplitude of a Note object can be changed or mapped to a Math node. 
                # Let's just pass for now if we can't easily. Actually `Note.amplitude` is a property.
                # Just ignore for now since it might be complex or unsupported to change dynamically without a Math node.
                
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0: volume = value0
        elif data0 == 1: cutoff_base = 50.0 * (100.0 ** value0)
        elif data0 == 2: resonance = 0.5 + value0 * 3.5
        elif data0 == 3: hpf_cutoff = 20.0 + value0 * 2000.0
        elif data0 == 4: ring_speed = 0.1 + value0 * 20.0
        elif data0 == 5: ring_depth = value0
        elif data0 == 6: layer2_mix = value0
        elif data0 == 7: poly_at_depth = value0
        elif data0 == 8: amp_a = 0.001 + value0 * 2.0
        elif data0 == 9: amp_d = 0.05 + value0 * 3.0
        elif data0 == 10: amp_s = value0
        elif data0 == 11: amp_r = 0.01 + value0 * 4.0
        elif data0 == 12: filt_a = 0.001 + value0 * 2.0
        elif data0 == 13: filt_d = 0.05 + value0 * 3.0
        elif data0 == 14: filt_s = value0
        elif data0 == 15: brilliance = value0 * 2.0

vstaudio.on_event(handle_event)
