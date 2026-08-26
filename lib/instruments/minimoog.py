# mpvst-macro-labels: Volume | Cutoff | Resonance | Env Amount | Glide | Osc2 Detune | Osc3 Detune | Noise Mix | Amp Attack | Amp Decay | Amp Sustain | Amp Release | Filter Attack | Filter Decay | Filter Sustain | Overdrive

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
    # Additive-harmonic tables (up to ~40 partials) are a real hot spot for the plain-Python
    # nested loop; use ulab when it's available (real engine) and fall back to it when not
    # (desktop test harness).
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

def noise_table(length=8192, seed=1234567):
    out = array.array("h", bytearray(length * 2))
    state = seed
    for i in range(length):
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        out[i] = ((state >> 15) & 0xFFFF) - 32768
    return out

def logmap(v, lo, hi):
    return lo * ((hi / lo) ** v)

SAW = make_table([(n, 1.0 / n) for n in range(1, 40)])
SQUARE = make_table([(n, 1.0 / n) for n in range(1, 40, 2)])
NOISE = noise_table()
NOISE_HZ = SR / 8192.0
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
cutoff_base = 2000.0
resonance = 1.0
env_amount = 3000.0
glide = 0.05
osc2_detune = 1.01
osc3_detune = 0.99
noise_mix = 0.0

amp_a = 0.01
amp_d = 0.3
amp_s = 0.5
amp_r = 0.3

filt_a = 0.01
filt_d = 0.3
filt_s = 0.2
overdrive = 1.0

# Patches: index -> (name, 16 macro values in mpvst-macro-labels order).
# Selected by MIDI Program Change (0-127); see handle_event's
# EVENT_PROGRAM_CHANGE branch below.
PATCHES = {
    0: ("Init", (0.8, 0.35, 0.25, 0.4, 0.05, 0.51, 0.49, 0.0,
                0.05, 0.4, 0.5, 0.35, 0.05, 0.4, 0.2, 0.0)),
    1: ("Deep Bass", (0.9, 0.2, 0.35, 0.55, 0.0, 0.52, 0.48, 0.0,
                      0.02, 0.3, 0.8, 0.2, 0.02, 0.25, 0.7, 0.15)),
    2: ("Screaming Lead", (0.85, 0.55, 0.75, 0.7, 0.15, 0.58, 0.44, 0.05,
                          0.01, 0.2, 0.9, 0.4, 0.01, 0.15, 0.6, 0.6)),
}

voices = {}
serial = 0
last_pitch = None
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
    global volume, cutoff_base, resonance, env_amount, glide, osc2_detune, osc3_detune, noise_mix
    global amp_a, amp_d, amp_s, amp_r, filt_a, filt_d, filt_s, overdrive
    global serial, last_pitch
    
    k = key_of(channel, note_id, data0)
    
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        if len(voices) >= MAX_VOICES:
            steal_oldest()
            
        hz = synthio.midi_to_hz(data0 + value1)
        
        bend = None
        if last_pitch is not None and glide > 0.001:
            last_hz = synthio.midi_to_hz(last_pitch)
            ratio = last_hz / hz
            # Gliding from last_hz to hz.  The bend table is int16, and one
            # full-scale step is one octave, so an interval wider than an
            # octave has to clamp - the real Model D's glide can't outrun
            # its own portamento circuit either.  Without the clamp a
            # downward leap of more than an octave overflows array("h").
            depth = int(32767 * (ratio - 1.0))
            if depth > 32767:
                depth = 32767
            elif depth < -32767:
                depth = -32767
            glide_table = array.array("h", (depth, 0))
            bend = synthio.LFO(waveform=glide_table, once=True, rate=1.0/glide, interpolate=True)
            
        last_pitch = data0
        
        env = synthio.Envelope(attack_time=amp_a, decay_time=amp_d, release_time=amp_r, attack_level=1.0, sustain_level=amp_s)
        
        env_tbl = env_shape_table(filt_a, filt_d, filt_s)
        f_sweep = synthio.LFO(waveform=env_tbl, once=True, rate=1.0/max(0.01, filt_a + filt_d), scale=env_amount, interpolate=True)
        
        cutoff = synthio.Math(synthio.MathOperation.SUM, cutoff_base, f_sweep, 0.0)
        lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, cutoff, Q=resonance)

        amp = volume * value0 * overdrive

        o1 = synthio.Note(hz, waveform=SAW, envelope=env, filter=lp, amplitude=amp * 0.4, bend=bend)
        o2 = synthio.Note(hz * osc2_detune, waveform=SAW, envelope=env, filter=lp, amplitude=amp * 0.4, bend=bend)
        o3 = synthio.Note(hz * osc3_detune, waveform=SQUARE, envelope=env, filter=lp, amplitude=amp * 0.3, bend=bend)
        n = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env, filter=lp, amplitude=amp * noise_mix * 0.3)

        serial += 1
        voices[k] = ((o1, o2, o3, n), serial)
        synth.press(o1)
        synth.press(o2)
        synth.press(o3)
        if noise_mix > 0.01:
            synth.press(n)
            
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
        
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0: volume = value0
        elif data0 == 1: cutoff_base = logmap(value0, 50.0, 10000.0)
        elif data0 == 2: resonance = logmap(value0, 0.5, 4.0)
        elif data0 == 3: env_amount = logmap(value0, 100.0, 8000.0)
        elif data0 == 4: glide = logmap(value0, 0.001, 1.0)
        elif data0 == 5: osc2_detune = 1.0 + (value0 - 0.5) * 0.05
        elif data0 == 6: osc3_detune = 1.0 + (value0 - 0.5) * 0.05
        elif data0 == 7: noise_mix = value0
        elif data0 == 8: amp_a = logmap(value0, 0.001, 2.0)
        elif data0 == 9: amp_d = logmap(value0, 0.05, 3.0)
        elif data0 == 10: amp_s = value0
        elif data0 == 11: amp_r = logmap(value0, 0.01, 3.0)
        elif data0 == 12: filt_a = logmap(value0, 0.001, 2.0)
        elif data0 == 13: filt_d = logmap(value0, 0.05, 3.0)
        elif data0 == 14: filt_s = value0
        elif data0 == 15: overdrive = logmap(value0, 1.0, 3.0)

    elif event_type == vstaudio.EVENT_PROGRAM_CHANGE:
        patch = PATCHES.get(data0)
        if patch is not None:
            for macro_index, macro_value in enumerate(patch[1]):
                handle_event(vstaudio.EVENT_PARAMETER, channel, note_id,
                             macro_index, macro_value, 0.0, sample_position)

vstaudio.on_event(handle_event)
