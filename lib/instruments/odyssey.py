# mpvst-macro-labels: Volume | Cutoff | Resonance | Ring Mod | LFO Rate | Env Sweep | Osc 2 Detune | Sync | Attack | Decay | Sustain | Release | HPF Cutoff | PPC | Master Tune | Glide

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

def ring_depth_table(depth, length=256):
    # Biased between unity (depth=0, inaudible) and a full bipolar sine
    # (depth=1, true ring modulation).
    out = array.array("h", bytearray(length * 2))
    for i in range(length):
        s = math.sin(TAU * i / length)
        v = (1.0 - depth) + depth * s
        out[i] = int(32767 * v)
    return out

SAW = make_table([(n, 1.0 / n) for n in range(1, 40)])
SQUARE = make_table([(n, 1.0 / n) for n in range(1, 40, 2)])
FALL = array.array("h", (32767, 0))

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
vstaudio.output(synth)

# Macros
volume = 0.8
cutoff_base = 2500.0
resonance = 1.0
ring_mod = 0.0
lfo_rate = 5.0
env_sweep = 3000.0
osc2_detune = 1.01
sync = 0.0
amp_a = 0.01
amp_d = 0.3
amp_s = 0.5
amp_r = 0.3
hpf_cutoff = 40.0
ppc = 0.0
master_tune = 1.0
glide = 0.0

voices = {}
serial = 0
MAX_VOICES = 2 # Duophonic
last_pitch = None

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
    global volume, cutoff_base, resonance, ring_mod, lfo_rate, env_sweep, osc2_detune, sync
    global amp_a, amp_d, amp_s, amp_r, hpf_cutoff, ppc, master_tune, glide
    global serial, last_pitch

    k = key_of(channel, note_id, data0)

    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        if len(voices) >= MAX_VOICES:
            steal_oldest()

        hz = synthio.midi_to_hz(data0 + value1) * master_tune
        amp = volume * value0

        # Glide: the Odyssey's portamento is a bend LFO ramping from the last note's pitch
        # down to 0, same one-shot-LFO trick as the Minimoog's glide.
        bend = None
        if last_pitch is not None and glide > 0.001:
            last_hz = synthio.midi_to_hz(last_pitch) * master_tune
            ratio = last_hz / hz
            glide_table = array.array("h", (int(32767 * (ratio - 1.0)), 0))
            bend = synthio.LFO(waveform=glide_table, once=True, rate=1.0 / (0.02 + glide * 0.6), interpolate=True)
        last_pitch = data0

        env = synthio.Envelope(attack_time=amp_a, decay_time=amp_d, release_time=amp_r, attack_level=1.0, sustain_level=amp_s)

        f_sweep = synthio.LFO(waveform=FALL, once=True, rate=1.0/amp_d, scale=env_sweep, interpolate=True)
        # LFO Rate: the Odyssey's LFO can route to the VCF, given a modest fixed depth since
        # there's no separate LFO depth macro.
        filt_lfo = synthio.LFO(rate=lfo_rate, scale=200.0)
        cutoff = synthio.Math(synthio.MathOperation.SUM, cutoff_base, f_sweep, filt_lfo)

        lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, cutoff, Q=resonance)
        # The real HPF sits before the resonant VCF on the whole mix; synthio allows only one
        # filter per Note, so approximate it by high-passing osc2 (thinning its low end as
        # cutoff rises) while osc1 keeps the full swept VCF.
        hp = synthio.Biquad(synthio.FilterMode.HIGH_PASS, hpf_cutoff, Q=0.7)

        # Sync: true audio-rate hard sync of osc2 to osc1 isn't achievable in synthio (no
        # per-sample phase reset), so approximate its buzzy, harmonically-locked character by
        # snapping osc2 toward an integer multiple of osc1's frequency as Sync increases.
        if sync > 0.01:
            ratio = round(osc2_detune)
            if ratio < 1:
                ratio = 1
            sync_detune = osc2_detune + (ratio - osc2_detune) * sync
        else:
            sync_detune = osc2_detune

        # Ring Mod: the Odyssey's dedicated ring modulator multiplies osc1 and osc2; use real
        # ring_frequency/ring_waveform rather than an amplitude trick.
        ring_wave = ring_depth_table(ring_mod) if ring_mod > 0.01 else None

        o1 = synthio.Note(hz, waveform=SAW, envelope=env, filter=lp, amplitude=amp * 0.5, bend=bend,
                           ring_frequency=hz * sync_detune, ring_waveform=ring_wave)
        o2 = synthio.Note(hz * sync_detune, waveform=SQUARE, envelope=env, filter=hp, amplitude=amp * 0.5, bend=bend)

        serial += 1
        voices[k] = ((o1, o2), serial)
        synth.press(o1)
        synth.press(o2)

    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)

    elif event_type == vstaudio.EVENT_CHANNEL_PRESSURE:
        # PPC (Proportional Pitch Control): the Odyssey's touch-sensitive pitch strip isn't
        # representable without a continuous X/Y controller, so approximate its "push harder
        # to bend" character with channel aftertouch driving pitch bend on the held voices.
        for notes, _ in voices.values():
            for note in notes:
                note.bend = ppc * value0 * 0.5

    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0: volume = value0
        elif data0 == 1: cutoff_base = 50.0 * (100.0 ** value0)
        elif data0 == 2: resonance = 0.5 + value0 * 3.5
        elif data0 == 3: ring_mod = value0
        elif data0 == 4: lfo_rate = 0.1 + value0 * 20.0
        elif data0 == 5: env_sweep = value0 * 8000.0
        elif data0 == 6: osc2_detune = 1.0 + (value0 - 0.5) * 0.03
        elif data0 == 7: sync = value0
        elif data0 == 8: amp_a = 0.001 + value0 * 2.0
        elif data0 == 9: amp_d = 0.05 + value0 * 3.0
        elif data0 == 10: amp_s = value0
        elif data0 == 11: amp_r = 0.01 + value0 * 4.0
        elif data0 == 12: hpf_cutoff = 20.0 + value0 * 2000.0
        elif data0 == 13: ppc = value0
        elif data0 == 14: master_tune = 0.95 + value0 * 0.1
        elif data0 == 15: glide = value0

# Patch 1 (Program Change 0) is the sound this script's module-level
# defaults describe, so a fresh instance and Patch 1 are the same thing.
# piece.py also reads it: a macro a composition does not set resolves here
# rather than to 0.5. Derived by tools/derive_patches.py - see that file
# before editing these numbers by hand.
PATCHES = {
    0: ("Init", (
        0.8, 0.849485, 0.142857, 0, 0.245, 0.375, 0.833333, 0, 0.0045,
        0.083333, 0.5, 0.0725, 0.01, 0, 0.5, 0)),
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

