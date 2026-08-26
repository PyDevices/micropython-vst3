# mpvst-macro-labels: Volume | Wavetable Pos | Cutoff | Resonance | Env to WT | Env to Filter | Filter Attack | Amp Attack | Amp Decay | Amp Sustain | Amp Release | Master Tune

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

# Aggressive digital waves
WAVE_1 = make_table(((1, 1.0), (4, 0.8), (8, 0.4)))
WAVE_2 = make_table(((1, 1.0), (3, 0.7), (5, 0.9), (7, 0.2)))
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
wt_pos = 0.0
cutoff_val = 2000.0
res = 1.0
env_wt = 1.0
env_flt = 4000.0
f_a = 0.01
amp_a = 0.01
amp_d = 0.5
amp_s = 0.8
amp_r = 0.5
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
    global volume, wt_pos, cutoff_val, res, env_wt, env_flt
    global f_a, amp_a, amp_d, amp_s, amp_r, master_tune
    global serial
    
    k = key_of(channel, note_id, data0)
    
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        if len(voices) >= MAX_VOICES:
            steal_oldest()
            
        hz = synthio.midi_to_hz(data0 + value1) * master_tune
        amp = volume * value0
        
        env = synthio.Envelope(attack_time=amp_a, decay_time=amp_d, release_time=amp_r, attack_level=1.0, sustain_level=amp_s)
        
        # Envelope modulates cutoff
        env_tbl = env_shape_table(f_a, amp_d, 0.0)
        f_sweep = synthio.LFO(waveform=env_tbl, once=True, rate=1.0/max(0.01, f_a + amp_d), scale=env_flt, interpolate=True)
        cutoff = synthio.Math(synthio.MathOperation.SUM, cutoff_val, f_sweep, 0.0)
        lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, cutoff, Q=res)
        
        # Env to Wavetable: the mix position sweeps from wt_pos to mix_end
        # over the amp decay time, driven by a live Math crossfade (Note
        # amplitude accepts a BlockInput, so this actually animates).
        mix_end = min(1.0, max(0.0, wt_pos + env_wt))

        ramp = synthio.LFO(waveform=array.array("h", (0, 32767)), once=True,
                            rate=1.0 / max(0.01, amp_d), interpolate=True)
        mix_pos = synthio.Math(synthio.MathOperation.LERP, wt_pos, mix_end, ramp)
        inv_pos = synthio.Math(synthio.MathOperation.ADD_SUB, 1.0, 0.0, mix_pos)
        amp1 = synthio.Math(synthio.MathOperation.PRODUCT, inv_pos, amp * 0.7, 1.0)
        amp2 = synthio.Math(synthio.MathOperation.PRODUCT, mix_pos, amp * 0.7, 1.0)

        notes = [
            synthio.Note(hz, waveform=WAVE_1, envelope=env, filter=lp, amplitude=amp1),
            synthio.Note(hz, waveform=WAVE_2, envelope=env, filter=lp, amplitude=amp2),
        ]

        serial += 1
        voices[k] = (tuple(notes), serial)
        for n in notes:
            synth.press(n)
            
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
        
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0: volume = value0
        elif data0 == 1: wt_pos = value0
        elif data0 == 2: cutoff_val = 50.0 * (100.0 ** value0)
        elif data0 == 3: res = 0.5 + value0 * 3.5
        elif data0 == 4: env_wt = -1.0 + value0 * 2.0
        elif data0 == 5: env_flt = value0 * 8000.0
        elif data0 == 6: f_a = 0.001 + value0 * 2.0
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
        0.8, 0, 0.80103, 0.142857, 1, 0.5, 0.0045, 0.0045, 0.15, 0.8,
        0.1225, 0.5)),
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

