# mpvst-macro-labels: Volume | Tuning | Cutoff | Resonance | Env Mod | Decay | Accent | Overdrive | Master Tune

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
FALL = array.array("h", (32767, 0))

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
vstaudio.output(synth)

# Macros
volume = 0.8
tuning = 1.0
cutoff_val = 500.0
res = 2.0
env_mod = 4000.0
decay_time = 0.5
accent = 0.0
overdrive = 1.0
master_tune = 1.0

voices = {}
serial = 0
MAX_VOICES = 1 # Monosynth

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
    global volume, tuning, cutoff_val, res, env_mod, decay_time, accent, overdrive, master_tune
    global serial
    
    k = key_of(channel, note_id, data0)
    
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        if len(voices) >= MAX_VOICES:
            steal_oldest()
            
        hz = synthio.midi_to_hz(data0 + value1) * master_tune * tuning
        
        # The 303's accent circuit feeds extra voltage into both the VCF envelope
        # generator and the VCA at once, snapping the filter open harder and louder
        # together - scale continuously with the accent knob, not a hard switch.
        actual_decay = decay_time * (1.0 - 0.7 * accent)
        actual_env_mod = env_mod * (1.0 + 1.2 * accent)

        amp = volume * value0 * overdrive * (1.0 + 0.5 * accent)
        
        env = synthio.Envelope(attack_time=0.01, decay_time=actual_decay, release_time=0.1, attack_level=1.0, sustain_level=0.1)
        
        f_sweep = synthio.LFO(waveform=FALL, once=True, rate=1.0/actual_decay, scale=actual_env_mod, interpolate=True)
        cutoff = synthio.Math(synthio.MathOperation.SUM, cutoff_val, f_sweep, 0.0)
        
        lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, cutoff, Q=res)
        
        n = synthio.Note(hz, waveform=SAW, envelope=env, filter=lp, amplitude=amp * 0.5)
        
        serial += 1
        voices[k] = ((n,), serial)
        synth.press(n)
            
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
        
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0: volume = value0
        elif data0 == 1: tuning = 0.5 + value0
        elif data0 == 2: cutoff_val = 50.0 * (100.0 ** value0)
        elif data0 == 3: res = 0.5 + value0 * 4.5
        elif data0 == 4: env_mod = value0 * 8000.0
        elif data0 == 5: decay_time = 0.05 + value0 * 2.0
        elif data0 == 6: accent = value0
        elif data0 == 7: overdrive = 1.0 + value0 * 3.0
        elif data0 == 8: master_tune = 0.95 + value0 * 0.1

# Patch 1 (Program Change 0) is the sound this script's module-level
# defaults describe, so a fresh instance and Patch 1 are the same thing.
# piece.py also reads it: a macro a composition does not set resolves here
# rather than to 0.5. Derived by tools/derive_patches.py - see that file
# before editing these numbers by hand.
PATCHES = {
    0: ("Init", (
        0.8, 0.5, 0.5, 0.333333, 0.5, 0.225, 0, 0, 0.5)),
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

