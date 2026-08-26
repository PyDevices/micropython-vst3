# mpvst-macro-labels: Volume | PD Env Depth | PD Attack | PD Decay | Resonance (Fake) | Vibrato Rate | Vibrato Depth | Amp Attack | Amp Decay | Amp Sustain | Amp Release | Master Tune

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

# True phase distortion warps a sine read-pointer's speed rather than filtering a
# spectrum; synthio has no per-sample phase control, so we approximate the audible
# result (a harmonic-rich tone whose brightness sweeps like the DCW envelope) with
# a harmonic-rich sawtooth run through a swept resonant low-pass below.
WAVE_PD = make_table([(n, 1.0 / n) for n in range(1, 40)])
SINE = make_table(((1, 1.0),))
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
pd_depth = 4000.0
pd_a = 0.05
pd_d = 0.5
res = 1.0
vib_rate = 5.0
vib_depth = 0.0
amp_a = 0.01
amp_d = 0.5
amp_s = 0.5
amp_r = 0.3
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
    global volume, pd_depth, pd_a, pd_d, res, vib_rate, vib_depth
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
        
        # DCW envelope modulates the "distortion" (cutoff of the rich wave) with a
        # one-shot attack->decay->0 shape, mirroring the CZ's DCW envelope stage.
        env_tbl = env_shape_table(pd_a, pd_d, 0.0)
        f_sweep = synthio.LFO(waveform=env_tbl, once=True, rate=1.0/max(0.01, pd_a + pd_d), scale=pd_depth, interpolate=True)
        
        lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, synthio.Math(synthio.MathOperation.SUM, 200.0, f_sweep, 0.0), Q=res)
        
        vib_lfo = synthio.LFO(waveform=SINE, rate=vib_rate, scale=vib_depth * 0.025) if vib_depth > 0.01 else None
        
        n = synthio.Note(hz, waveform=WAVE_PD, envelope=env, filter=lp, amplitude=amp * 0.8, bend=vib_lfo)
        
        serial += 1
        voices[k] = ((n,), serial)
        synth.press(n)
            
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
        
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0: volume = value0
        elif data0 == 1: pd_depth = value0 * 8000.0
        elif data0 == 2: pd_a = 0.001 + value0 * 1.0
        elif data0 == 3: pd_d = 0.05 + value0 * 2.0
        elif data0 == 4: res = 0.5 + value0 * 3.5
        elif data0 == 5: vib_rate = 0.1 + value0 * 10.0
        elif data0 == 6: vib_depth = value0
        elif data0 == 7: amp_a = 0.001 + value0 * 2.0
        elif data0 == 8: amp_d = 0.05 + value0 * 3.0
        elif data0 == 9: amp_s = value0
        elif data0 == 10: amp_r = 0.01 + value0 * 4.0
        elif data0 == 11: master_tune = 0.95 + value0 * 0.1

# Patch 1 (Program Change 0) is the sound this script's module-level
# defaults describe, so a fresh instance and Patch 1 are the same thing.
# piece.py also reads it: a macro a composition does not set resolves here
# rather than to 0.5. Derived by tools/derive_patches.py - see that file
# before editing these numbers by hand.
PATCHES = {
    0: ("Init", (
        0.8, 0.5, 0.049, 0.225, 0.142857, 0.49, 0, 0.0045, 0.15, 0.5,
        0.0725, 0.5)),
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

