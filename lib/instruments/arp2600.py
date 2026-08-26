# mpvst-macro-labels: Volume | VCF Cutoff | Resonance | FM Amount | Reverb Mix | Osc 2 Detune | Osc 3 Detune | Env 1 Attack | Env 1 Release | Env 2 Attack | Env 2 Decay | Env 2 Sustain | Env 2 Release | VCA Attack | VCA Release | Master Tune

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
SQUARE = make_table([(n, 1.0 / n) for n in range(1, 40, 2)])
TRIANGLE = make_table([(n, (1.0 / (n*n)) * (-1)**((n-1)//2)) for n in range(1, 11, 2)])
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
fm_amt = 0.0
reverb_mix = 0.0
osc2_detune = 1.0
osc3_detune = 0.5

e1_a = 0.01
e1_r = 0.5
e2_a = 0.01
e2_d = 0.3
e2_s = 0.5
e2_r = 0.3
vca_a = 0.01
vca_r = 0.3
master_tune = 1.0

voices = {}
serial = 0
MAX_VOICES = 1

def key_of(channel, note_id, pitch):
    return (channel, note_id if note_id >= 0 else pitch)

def release_voice(k):
    voice = voices.pop(k, None)
    if voice is not None:
        notes, _, filt_release, filtered_notes = voice
        if filt_release is not None:
            base_cutoff, sustain_delta, release_time, q = filt_release
            rel_lfo = synthio.LFO(waveform=array.array("h", (32767, 0)), once=True,
                                  rate=1.0 / max(0.01, release_time), interpolate=True)
            rel_cutoff = synthio.Math(synthio.MathOperation.SCALE_OFFSET, rel_lfo,
                                      sustain_delta, base_cutoff)
            rel_filter = synthio.Biquad(synthio.FilterMode.LOW_PASS, rel_cutoff, Q=q)
            for note in filtered_notes:
                note.filter = rel_filter
        for note in notes:
            synth.release(note)

def steal_oldest():
    oldest = None
    for k in voices:
        if oldest is None or voices[k][1] < voices[oldest][1]:
            oldest = k
    if oldest is not None:
        release_voice(oldest)

def handle_event(event_type, channel, note_id, data0, value0, value1, sample_position):
    global volume, cutoff_base, resonance, fm_amt, reverb_mix, osc2_detune, osc3_detune
    global e1_a, e1_r, e2_a, e2_d, e2_s, e2_r, vca_a, vca_r, master_tune
    global serial
    
    k = key_of(channel, note_id, data0)
    
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        if len(voices) >= MAX_VOICES:
            steal_oldest()
            
        hz = synthio.midi_to_hz(data0 + value1) * master_tune
        amp = volume * value0
        
        env = synthio.Envelope(attack_time=vca_a, decay_time=e2_d, release_time=vca_r, attack_level=1.0, sustain_level=1.0)

        env_tbl = env_shape_table(e2_a, e2_d, e2_s)
        f_sweep = synthio.LFO(waveform=env_tbl, once=True, rate=1.0/max(0.01, e2_a + e2_d), scale=4000.0, interpolate=True)
        cutoff = synthio.Math(synthio.MathOperation.SUM, cutoff_base, f_sweep, 0.0)

        lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, cutoff, Q=resonance)

        o1 = synthio.Note(hz, waveform=SAW, envelope=env, filter=lp, amplitude=amp * 0.4)
        o2 = synthio.Note(hz * osc2_detune, waveform=SQUARE, envelope=env, filter=lp, amplitude=amp * 0.3)
        # Env 1 (Attack/Release) patched to osc3's pitch input, scaled by FM Amount: the ARP
        # 2600 is semi-modular, and "envelope -> VCO frequency" is one of its classic patches
        # (laser/zap sounds). synthio can't do audio-rate FM, so approximate it as a one-shot
        # pitch-bend sweep shaped by Env 1.
        fm_tbl = env_shape_table(e1_a, e1_r, 0.0)
        fm_lfo = synthio.LFO(waveform=fm_tbl, once=True, rate=1.0/max(0.01, e1_a + e1_r), scale=fm_amt * 2.0, interpolate=True) if fm_amt > 0.01 else None
        o3 = synthio.Note(hz * osc3_detune, waveform=TRIANGLE, envelope=env, filter=lp, amplitude=amp * 0.3, bend=fm_lfo)

        filtered_notes = [o1, o2, o3]
        notes = list(filtered_notes)

        # Reverb Mix: the 2600 itself is dry; approximate a reverb-style tail with a quietly
        # mixed, softly filtered, longer-release copy of the voice rather than true convolution.
        if reverb_mix > 0.01:
            wash_env = synthio.Envelope(attack_time=vca_a, decay_time=e2_d, release_time=vca_r + reverb_mix * 2.0, attack_level=1.0, sustain_level=1.0)
            wash_filt = synthio.Biquad(synthio.FilterMode.LOW_PASS, cutoff_base * 0.4, Q=0.7)
            wash = synthio.Note(hz * 1.003, waveform=TRIANGLE, envelope=wash_env, filter=wash_filt, amplitude=amp * reverb_mix * 0.25, panning=0.6)
            notes.append(wash)

        # Env 2 Release: retarget o1/o2/o3's shared filter to a real release
        # sweep at note-off (Note.filter is mutable post-construction), since
        # the one-shot attack/decay LFO above can't represent an indefinite
        # sustain hold followed by a release triggered by an unknown-in-
        # advance note-off time.
        filt_release = (cutoff_base, 4000.0 * e2_s, e2_r, resonance)

        serial += 1
        voices[k] = (tuple(notes), serial, filt_release, tuple(filtered_notes))
        for n in notes:
            synth.press(n)

    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
        
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0: volume = value0
        elif data0 == 1: cutoff_base = 50.0 * (100.0 ** value0)
        elif data0 == 2: resonance = 0.5 + value0 * 3.5
        elif data0 == 3: fm_amt = value0
        elif data0 == 4: reverb_mix = value0
        elif data0 == 5: osc2_detune = 0.5 + value0
        elif data0 == 6: osc3_detune = 0.25 + value0
        elif data0 == 7: e1_a = 0.001 + value0 * 2.0
        elif data0 == 8: e1_r = 0.01 + value0 * 4.0
        elif data0 == 9: e2_a = 0.001 + value0 * 2.0
        elif data0 == 10: e2_d = 0.05 + value0 * 3.0
        elif data0 == 11: e2_s = value0
        elif data0 == 12: e2_r = 0.01 + value0 * 4.0
        elif data0 == 13: vca_a = 0.001 + value0 * 2.0
        elif data0 == 14: vca_r = 0.01 + value0 * 4.0
        elif data0 == 15: master_tune = 0.95 + value0 * 0.1

# Patch 1 (Program Change 0) is the sound this script's module-level
# defaults describe, so a fresh instance and Patch 1 are the same thing.
# piece.py also reads it: a macro a composition does not set resolves here
# rather than to 0.5. Derived by tools/derive_patches.py - see that file
# before editing these numbers by hand.
PATCHES = {
    0: ("Init", (
        0.8, 0.80103, 0.142857, 0, 0, 0.5, 0.25, 0.0045, 0.1225,
        0.0045, 0.083333, 0.5, 0.0725, 0.0045, 0.0725, 0.5)),
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

