# mpvst-macro-labels: Volume | Pulse Width | Sub-Osc Level | Cutoff | Resonance | Env Depth | Fast Decay | Master Tune

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
    peak = max(abs(v) for v in vals) if vals else 0.0
    if peak <= 0.0:
        peak = 1.0
    out = array.array("h", bytearray(length * 2))
    scale = gain / peak
    for i in range(length):
        out[i] = int(vals[i] * scale)
    return out

def make_pulse_table(duty, length=2048, gain=32000, harmonics=32):
    # Band-limited rectangular pulse via its Fourier series so the duty cycle
    # actually reshapes the harmonic content (true PWM), not just a naive
    # sample-and-hold pulse that would alias badly at pitch.
    parts = [(n, (2.0 / (n * math.pi)) * math.sin(n * math.pi * duty)) for n in range(1, harmonics)]
    return make_table(parts, length, gain)

SAW = make_table([(n, 1.0 / n) for n in range(1, 40)])
SQUARE = make_table([(n, 1.0 / n) for n in range(1, 40, 2)])
FALL = array.array("h", (32767, 0))

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
vstaudio.output(synth)

# Macros
volume = 0.8
pw = 0.5
sub_osc = 0.8
cutoff_val = 1500.0
res = 1.0
env_depth = 3000.0
fast_decay = 0.2
master_tune = 1.0

voices = {}
serial = 0
MAX_VOICES = 1

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
    global volume, pw, sub_osc, cutoff_val, res, env_depth, fast_decay, master_tune
    global serial
    
    k = key_of(channel, note_id, data0)
    
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        if len(voices) >= MAX_VOICES:
            steal_oldest()
            
        hz = synthio.midi_to_hz(data0 + value1) * master_tune
        amp = volume * value0
        
        env = synthio.Envelope(attack_time=0.01, decay_time=fast_decay, release_time=0.1, attack_level=1.0, sustain_level=0.1)
        
        f_sweep = synthio.LFO(waveform=FALL, once=True, rate=1.0/fast_decay, scale=env_depth, interpolate=True)
        cutoff = synthio.Math(synthio.MathOperation.SUM, cutoff_val, f_sweep, 0.0)
        
        lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, cutoff, Q=res)
        
        # SH-101's main VCO is a pulse wave with a real PWM control; rebuild the
        # duty-cycle table per note-on from the current Pulse Width macro.
        duty = 0.05 + pw * 0.9
        pulse_wave = make_pulse_table(duty)
        n1 = synthio.Note(hz, waveform=pulse_wave, envelope=env, filter=lp, amplitude=amp * 0.5)
        n_sub = synthio.Note(hz * 0.5, waveform=SQUARE, envelope=env, filter=lp, amplitude=amp * sub_osc * 0.5)
        
        serial += 1
        voices[k] = ((n1, n_sub), serial)
        synth.press(n1)
        synth.press(n_sub)
            
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
        
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0: volume = value0
        elif data0 == 1: pw = value0
        elif data0 == 2: sub_osc = value0
        elif data0 == 3: cutoff_val = 50.0 * (100.0 ** value0)
        elif data0 == 4: res = 0.5 + value0 * 3.5
        elif data0 == 5: env_depth = value0 * 6000.0
        elif data0 == 6: fast_decay = 0.05 + value0 * 1.0
        elif data0 == 7: master_tune = 0.95 + value0 * 0.1

# Patch 1 (Program Change 0) is the sound this script's module-level
# defaults describe, so a fresh instance and Patch 1 are the same thing.
# piece.py also reads it: a macro a composition does not set resolves here
# rather than to 0.5. Derived by tools/derive_patches.py - see that file
# before editing these numbers by hand.
PATCHES = {
    0: ("Init", (
        0.8, 0.5, 0.8, 0.738561, 0.142857, 0.5, 0.15, 0.5)),
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

