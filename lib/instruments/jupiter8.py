# mpvst-macro-labels: Volume | Cutoff | Resonance | Env Depth | Cross Mod | Unison | LFO Rate | Amp Release | Amp Attack | Amp Decay | Amp Sustain | Filter Attack | Filter Decay | Filter Sustain | HPF Cutoff | PW

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

SAW = make_table([(n, 1.0 / n) for n in range(1, 40)])

def pulse_table(width, length=2048, gain=30000):
    # True variable-duty pulse wave for PWM, built as a direct duty-cycle
    # lookup rather than additive sine synthesis.
    n_hi = int(length * width)
    if n_hi < 1:
        n_hi = 1
    if n_hi > length - 1:
        n_hi = length - 1
    out = array.array("h", bytearray(length * 2))
    for i in range(length):
        out[i] = gain if i < n_hi else -gain
    return out

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
cutoff_base = 2500.0
resonance = 1.2
env_depth = 4000.0
cross_mod = 0.0
unison_spread = 0.0
lfo_rate = 5.0
release_time = 0.5
hpf_cutoff = 40.0
pw = 0.5

amp_a = 0.01
amp_d = 0.4
amp_s = 0.5
filt_a = 0.01
filt_d = 0.4
filt_s = 0.3

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
    global volume, cutoff_base, resonance, env_depth, cross_mod, unison_spread, lfo_rate, release_time
    global amp_a, amp_d, amp_s, filt_a, filt_d, filt_s, hpf_cutoff, pw
    global serial
    
    k = key_of(channel, note_id, data0)
    
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        if len(voices) >= MAX_VOICES:
            steal_oldest()
            
        hz = synthio.midi_to_hz(data0 + value1)
        amp = volume * value0
        
        env = synthio.Envelope(attack_time=amp_a, decay_time=amp_d, release_time=release_time, attack_level=1.0, sustain_level=amp_s)
        
        env_tbl = env_shape_table(filt_a, filt_d, filt_s)
        f_sweep = synthio.LFO(waveform=env_tbl, once=True, rate=1.0/max(0.01, filt_a + filt_d), scale=env_depth, interpolate=True)
        # LFO Rate: Jupiter-8's LFO can route to the VCF; give it a modest fixed depth here
        # since there's no separate LFO depth macro.
        filt_lfo = synthio.LFO(rate=lfo_rate, scale=250.0)

        cutoff = synthio.Math(synthio.MathOperation.SUM, cutoff_base, f_sweep, filt_lfo)
        lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, cutoff, Q=resonance)

        pw_wave = pulse_table(0.1 + pw * 0.8)

        # Jupiter 8 Unison creates massive sound
        if unison_spread > 0.01:
            o1 = synthio.Note(hz, waveform=SAW, envelope=env, filter=lp, amplitude=amp * 0.3, panning=-0.5)
            o2 = synthio.Note(hz * (1.0 + unison_spread * 0.02), waveform=SAW, envelope=env, filter=lp, amplitude=amp * 0.3, panning=0.5)
            o3 = synthio.Note(hz * (1.0 - unison_spread * 0.02), waveform=pw_wave, envelope=env, filter=lp, amplitude=amp * 0.3, panning=0.0)
            notes = [o1, o2, o3]
        else:
            o1 = synthio.Note(hz, waveform=SAW, envelope=env, filter=lp, amplitude=amp * 0.5)
            # Cross-modulation: synthio can't FM one oscillator's pitch from another's audio
            # signal, so approximate the warbling cross-mod character with a fast sub-audio
            # LFO bending osc2's pitch, scaled by the Cross Mod amount.
            cm_lfo = synthio.LFO(rate=max(20.0, hz * 0.25), scale=cross_mod * 0.4) if cross_mod > 0.01 else None
            o2 = synthio.Note(hz, waveform=pw_wave, envelope=env, filter=lp, amplitude=amp * 0.5, bend=cm_lfo)
            notes = [o1, o2]

        # The Jupiter-8 has no dedicated per-voice HPF; give the macro a real audible effect
        # by mixing in a quiet high-passed top-end layer whose brightness tracks HPF Cutoff
        # (single-filter-per-Note rules out a true series HPF -> VCF chain).
        hp = synthio.Biquad(synthio.FilterMode.HIGH_PASS, hpf_cutoff, Q=0.7)
        notes.append(synthio.Note(hz, waveform=SAW, envelope=env, filter=hp, amplitude=amp * 0.15))

        serial += 1
        voices[k] = (tuple(notes), serial)
        for n in notes:
            synth.press(n)
            
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
        
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0: volume = value0
        elif data0 == 1: cutoff_base = 50.0 * (100.0 ** value0)
        elif data0 == 2: resonance = 0.5 + value0 * 3.5
        elif data0 == 3: env_depth = value0 * 8000.0
        elif data0 == 4: cross_mod = value0 * 2.0
        elif data0 == 5: unison_spread = value0
        elif data0 == 6: lfo_rate = 0.1 + value0 * 20.0
        elif data0 == 7: release_time = 0.01 + value0 * 4.0
        elif data0 == 8: amp_a = 0.001 + value0 * 2.0
        elif data0 == 9: amp_d = 0.05 + value0 * 3.0
        elif data0 == 10: amp_s = value0
        elif data0 == 11: filt_a = 0.001 + value0 * 2.0
        elif data0 == 12: filt_d = 0.05 + value0 * 3.0
        elif data0 == 13: filt_s = value0
        elif data0 == 14: hpf_cutoff = 20.0 + value0 * 2000.0
        elif data0 == 15: pw = value0

vstaudio.on_event(handle_event)
