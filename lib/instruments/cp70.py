# mpvst-macro-labels: Volume | Hammer Strike | String Body | Tremolo Rate | Tremolo Depth | Chorus | Decay | Brilliance | Master Tune

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

def ring_depth_table(depth, length=256):
    # A ring-modulation waveform biased between unity (depth=0, no audible
    # effect) and a full bipolar sine (depth=1, true ring modulation). At
    # ring_frequency rates below ~20Hz this reads as tremolo.
    out = array.array("h", bytearray(length * 2))
    for i in range(length):
        s = math.sin(TAU * i / length)
        v = (1.0 - depth) + depth * s
        out[i] = int(32767 * v)
    return out


WAVE_HAMMER = make_table(((1, 1.0), (3, 0.8), (5, 0.5), (9, 0.2)))
WAVE_STRING = make_table([(n, 1.0 / n) for n in range(1, 40)])
SINE = make_table(((1, 1.0),))

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
vstaudio.output(synth)

# Macros
volume = 0.8
hammer_lvl = 0.8
string_lvl = 1.0
trem_rate = 5.0
trem_depth = 0.0
chorus = 0.5
decay = 2.0
brilliance = 0.8
master_tune = 1.0

voices = {}
serial = 0
MAX_VOICES = 12

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
    global volume, hammer_lvl, string_lvl, trem_rate, trem_depth, chorus, decay, brilliance, master_tune
    global serial
    
    k = key_of(channel, note_id, data0)
    
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        if len(voices) >= MAX_VOICES:
            steal_oldest()
            
        hz = synthio.midi_to_hz(data0 + value1) * master_tune
        amp = volume * value0
        
        env = synthio.Envelope(attack_time=0.005, decay_time=decay, release_time=0.4, attack_level=1.0, sustain_level=0.0)
        hammer_env = synthio.Envelope(attack_time=0.001, decay_time=0.1, release_time=0.05, attack_level=1.0, sustain_level=0.0)
        
        cutoff = 500.0 + (brilliance * 8000.0)
        lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, cutoff, Q=0.7)
        
        trem_wave = ring_depth_table(trem_depth) if trem_depth > 0.01 else None
        
        notes = []
        # Chorus simulation
        if chorus > 0.01:
            n1 = synthio.Note(hz, waveform=WAVE_STRING, envelope=env, filter=lp, amplitude=amp * string_lvl * 0.4, ring_frequency=trem_rate, ring_waveform=trem_wave, panning=-0.3)
            n2 = synthio.Note(hz * (1.0 + chorus * 0.005), waveform=WAVE_STRING, envelope=env, filter=lp, amplitude=amp * string_lvl * 0.4, ring_frequency=trem_rate, ring_waveform=trem_wave, panning=0.3)
            notes.extend([n1, n2])
        else:
            notes.append(synthio.Note(hz, waveform=WAVE_STRING, envelope=env, filter=lp, amplitude=amp * string_lvl * 0.8, ring_frequency=trem_rate, ring_waveform=trem_wave))
            
        notes.append(synthio.Note(hz, waveform=WAVE_HAMMER, envelope=hammer_env, filter=lp, amplitude=amp * hammer_lvl * 0.6, ring_frequency=trem_rate, ring_waveform=trem_wave))
        
        serial += 1
        voices[k] = (tuple(notes), serial)
        for n in notes:
            synth.press(n)
            
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
        
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0: volume = value0
        elif data0 == 1: hammer_lvl = value0 * 2.0
        elif data0 == 2: string_lvl = value0 * 2.0
        elif data0 == 3: trem_rate = 0.1 + value0 * 10.0
        elif data0 == 4: trem_depth = value0
        elif data0 == 5: chorus = value0
        elif data0 == 6: decay = 0.5 + value0 * 4.0
        elif data0 == 7: brilliance = value0
        elif data0 == 8: master_tune = 0.95 + value0 * 0.1

# Patch 1 (Program Change 0) is the sound this script's module-level
# defaults describe, so a fresh instance and Patch 1 are the same thing.
# piece.py also reads it: a macro a composition does not set resolves here
# rather than to 0.5. Derived by tools/derive_patches.py - see that file
# before editing these numbers by hand.
PATCHES = {
    0: ("Init", (
        0.8, 0.4, 0.5, 0.49, 0, 0.5, 0.375, 0.8, 0.5)),
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

