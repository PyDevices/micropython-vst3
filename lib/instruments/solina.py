# mpvst-macro-labels: Volume | Violin Mix | Viola Mix | Cello Mix | Chorus Depth | Attack | Release | Crescendo | Master Tune

import array
import math
import random

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

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
vstaudio.output(synth)

# Macros
volume = 0.8
violin = 1.0
viola = 0.5
cello = 0.5
chorus_depth = 1.0
att = 0.1
rel = 0.5
crescendo = 0.0
master_tune = 1.0

voices = {}
serial = 0
MAX_VOICES = 6

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
    global volume, violin, viola, cello, chorus_depth, att, rel, crescendo, master_tune
    global serial
    
    k = key_of(channel, note_id, data0)
    
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        if len(voices) >= MAX_VOICES:
            steal_oldest()
            
        hz = synthio.midi_to_hz(data0 + value1) * master_tune
        amp = volume * value0
        
        # Crescendo makes attack slower based on velocity or macro
        actual_att = att + (crescendo * 2.0)
        env = synthio.Envelope(attack_time=actual_att, decay_time=0.1, release_time=rel, attack_level=1.0, sustain_level=1.0)
        
        lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, 5000.0, Q=0.5)
        
        notes = []
        
        # Solina ensemble chorus emulation (3-4 detuned/modulated saws per voice)
        # We apply slow separate LFOs to each to simulate BBD ensemble
        rates = [0.6, 6.0, 4.0]
        pans = [-0.5, 0.0, 0.5]
        
        for reg_mult, reg_vol in [(1.0, violin), (0.5, viola), (0.25, cello)]:
            if reg_vol > 0.01:
                for i in range(3):
                    mod_lfo = synthio.LFO(waveform=SINE, rate=rates[i], scale=chorus_depth * 0.008)
                    n = synthio.Note(hz * reg_mult, waveform=SAW, envelope=env, filter=lp, amplitude=amp * reg_vol * 0.15, bend=mod_lfo, panning=pans[i])
                    notes.append(n)
        
        serial += 1
        voices[k] = (tuple(notes), serial)
        for n in notes:
            synth.press(n)
            
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
        
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0: volume = value0
        elif data0 == 1: violin = value0
        elif data0 == 2: viola = value0
        elif data0 == 3: cello = value0
        elif data0 == 4: chorus_depth = value0
        elif data0 == 5: att = 0.001 + value0 * 2.0
        elif data0 == 6: rel = 0.01 + value0 * 4.0
        elif data0 == 7: crescendo = value0
        elif data0 == 8: master_tune = 0.95 + value0 * 0.1

# Patch 1 (Program Change 0) is the sound this script's module-level
# defaults describe, so a fresh instance and Patch 1 are the same thing.
# piece.py also reads it: a macro a composition does not set resolves here
# rather than to 0.5. Derived by tools/derive_patches.py - see that file
# before editing these numbers by hand.
PATCHES = {
    0: ("Init", (
        0.8, 1, 0.5, 0.5, 1, 0.0495, 0.1225, 0, 0.5)),
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

