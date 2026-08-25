# mpvst-macro-labels: Volume | Wavetable Index | Cutoff | Resonance | Env Amount | Filter Attack | Filter Decay | Amp Attack | Amp Sustain | Amp Release | Detune | Master Tune

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

# PPG Wave 2.2 style digital waveforms
WAVE_A = make_table(((1, 1.0), (2, 0.5), (4, 0.25)))
WAVE_B = make_table(((1, 1.0), (3, 0.7), (5, 0.4), (7, 0.2)))
def env_shape_table(attack, decay, sustain, length=96):
    # One-shot LFO waveform: ramps 0 -> peak over the attack fraction, then
    # peak -> sustain over the decay fraction, holding sustain afterwards
    # (once=True freezes at the table's last sample).
    total = attack + decay
    n_a = 1 if total <= 0.0 else int(length * attack / total)
    if n_a < 1:
        n_a = 1
    if n_a > length - 1:
        n_a = length - 1
    sustain_level = int(32767 * sustain)
    out = array.array("h", bytearray(length * 2))
    for i in range(n_a):
        out[i] = int(32767 * (i + 1) / n_a)
    span = length - n_a
    for i in range(span):
        out[n_a + i] = int(32767 + (sustain_level - 32767) * (i + 1) / span)
    return out


synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
vstaudio.output(synth)

# Macros
volume = 0.8
wt_index = 0.5
cutoff_base = 2000.0
res = 1.5
env_amount = 3000.0
f_a = 0.01
f_d = 0.3
amp_a = 0.01
amp_s = 0.8
amp_r = 0.5
detune = 0.01
master_tune = 1.0

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
    global volume, wt_index, cutoff_base, res, env_amount
    global f_a, f_d, amp_a, amp_s, amp_r, detune, master_tune
    global serial
    
    k = key_of(channel, note_id, data0)
    
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        if len(voices) >= MAX_VOICES:
            steal_oldest()
            
        hz = synthio.midi_to_hz(data0 + value1) * master_tune
        amp = volume * value0
        
        env = synthio.Envelope(attack_time=amp_a, decay_time=f_d, release_time=amp_r, attack_level=1.0, sustain_level=amp_s)
        
        env_tbl = env_shape_table(f_a, f_d, 0.0)
        f_sweep = synthio.LFO(waveform=env_tbl, once=True, rate=1.0/max(0.01, f_a + f_d), scale=env_amount, interpolate=True)
        cutoff = synthio.Math(synthio.MathOperation.SUM, cutoff_base, f_sweep, 0.0)

        lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, cutoff, Q=res)

        # PPG's signature is the wavetable position moving through the table, not
        # sitting still; scan from wave A up to the Wavetable Index target over the
        # same attack/decay contour as the filter envelope, then hold - the classic
        # "wave envelope follows filter envelope" PPG factory-patch behavior.
        scan_tbl = env_shape_table(f_a, f_d, 1.0)
        scan_lfo = synthio.LFO(waveform=scan_tbl, once=True, rate=1.0/max(0.01, f_a + f_d), scale=wt_index, interpolate=True)
        amp_a_expr = synthio.Math(synthio.MathOperation.SCALE_OFFSET, scan_lfo, -(amp * 0.4), amp * 0.4)
        amp_b_expr = synthio.Math(synthio.MathOperation.SCALE_OFFSET, scan_lfo, amp * 0.4, 0.0)

        notes = [
            synthio.Note(hz, waveform=WAVE_A, envelope=env, filter=lp, amplitude=amp_a_expr, panning=-0.2),
            synthio.Note(hz * (1.0 + detune), waveform=WAVE_A, envelope=env, filter=lp, amplitude=amp_a_expr, panning=0.2),
            synthio.Note(hz, waveform=WAVE_B, envelope=env, filter=lp, amplitude=amp_b_expr, panning=-0.2),
            synthio.Note(hz * (1.0 + detune), waveform=WAVE_B, envelope=env, filter=lp, amplitude=amp_b_expr, panning=0.2),
        ]

        serial += 1
        voices[k] = (tuple(notes), serial)
        for n in notes:
            synth.press(n)
            
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
        
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0: volume = value0
        elif data0 == 1: wt_index = value0
        elif data0 == 2: cutoff_base = 50.0 * (100.0 ** value0)
        elif data0 == 3: res = 0.5 + value0 * 3.5
        elif data0 == 4: env_amount = value0 * 8000.0
        elif data0 == 5: f_a = 0.001 + value0 * 2.0
        elif data0 == 6: f_d = 0.05 + value0 * 4.0
        elif data0 == 7: amp_a = 0.001 + value0 * 2.0
        elif data0 == 8: amp_s = value0
        elif data0 == 9: amp_r = 0.01 + value0 * 4.0
        elif data0 == 10: detune = value0 * 0.05
        elif data0 == 11: master_tune = 0.95 + value0 * 0.1

vstaudio.on_event(handle_event)
