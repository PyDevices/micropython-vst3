# mpvst-macro-labels: Volume | FM Amount | Mod Ratio | Feedback | Env 1 Decay | Env 2 Decay | Env 3 Decay | Release Time | Alg Mix | Attack Time | Brightness | Tremolo Depth | Vibrato Depth | Tremolo Rate | Vibrato Rate | Master Tune

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

# In DX7 emulation via synthio, we cannot easily do true FM (modulating pitch of a Note at audio rate).
# However, we can approximate the iconic "E.Piano 1" sound using additive sine harmonics that decay at different rates.
SINE = make_table(((1, 1.0),))
EP_HARM_1 = make_table(((1, 1.0), (3, 0.4), (5, 0.2)))
EP_HARM_2 = make_table(((2, 1.0), (4, 0.5), (6, 0.25), (14, 0.1)))
EP_HARM_3 = make_table(((8, 1.0), (9, 0.8), (11, 0.5), (15, 0.3))) # Metallic tines

def ring_depth_table(depth, length=256):
    # Biased between unity (depth=0, inaudible) and a full bipolar sine
    # (depth=1, true ring modulation); at tremolo-range rates this reads
    # as tremolo.
    out = array.array("h", bytearray(length * 2))
    for i in range(length):
        s = math.sin(TAU * i / length)
        v = (1.0 - depth) + depth * s
        out[i] = int(32767 * v)
    return out

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
vstaudio.output(synth)

# Macros
volume = 0.8
fm_amount = 0.5
mod_ratio = 1.0
feedback = 0.0
e1_d = 1.5
e2_d = 0.8
e3_d = 0.2
rel_t = 0.5
alg_mix = 0.5
att_t = 0.01
brightness = 0.8
trem_depth = 0.0
vib_depth = 0.0
trem_rate = 2.0
vib_rate = 5.0
master_tune = 1.0

voices = {}
serial = 0
MAX_VOICES = 16

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
    global volume, fm_amount, mod_ratio, feedback, e1_d, e2_d, e3_d, rel_t
    global alg_mix, att_t, brightness, trem_depth, vib_depth, trem_rate, vib_rate, master_tune
    global serial
    
    k = key_of(channel, note_id, data0)
    
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        if len(voices) >= MAX_VOICES:
            steal_oldest()
            
        hz = synthio.midi_to_hz(data0 + value1) * master_tune
        amp = volume * value0
        
        # We simulate the FM modulators by having multiple carriers with different waveforms and decay times.
        # This gives the dynamic harmonic shift typical of DX7 EPiano.
        
        env1 = synthio.Envelope(attack_time=att_t, decay_time=e1_d, release_time=rel_t, attack_level=1.0, sustain_level=0.0)
        env2 = synthio.Envelope(attack_time=att_t, decay_time=e2_d, release_time=rel_t, attack_level=1.0, sustain_level=0.0)
        env3 = synthio.Envelope(attack_time=att_t, decay_time=e3_d, release_time=rel_t, attack_level=1.0, sustain_level=0.0)
        
        vib_lfo = synthio.LFO(waveform=SINE, rate=vib_rate, scale=vib_depth * 0.02) if vib_depth > 0.01 else None
        trem_wave = ring_depth_table(trem_depth) if trem_depth > 0.01 else None

        # Feedback: the DX7's self-modulating operator adds upper-harmonic
        # bite, so scale it into the metallic tine layer.
        # Alg mix: crossfades between the mellow (o1) and bright/metallic
        # (o3) layers, approximating an algorithm change.
        o1 = synthio.Note(hz, waveform=EP_HARM_1, envelope=env1, amplitude=amp * 0.6 * (1.0 - alg_mix),
                           ring_frequency=trem_rate, ring_waveform=trem_wave, bend=vib_lfo)
        o2 = synthio.Note(hz * mod_ratio, waveform=EP_HARM_2, envelope=env2, amplitude=amp * 0.3 * fm_amount,
                           ring_frequency=trem_rate, ring_waveform=trem_wave, bend=vib_lfo)
        o3 = synthio.Note(hz, waveform=EP_HARM_3, envelope=env3, amplitude=amp * 0.4 * brightness * (alg_mix + feedback),
                           ring_frequency=trem_rate, ring_waveform=trem_wave, bend=vib_lfo)

        notes = [o1, o2, o3]
        serial += 1
        voices[k] = (tuple(notes), serial)
        for n in notes:
            synth.press(n)
            
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
        
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0: volume = value0
        elif data0 == 1: fm_amount = value0 * 2.0
        elif data0 == 2: mod_ratio = 1.0 + math.floor(value0 * 10.0)
        elif data0 == 3: feedback = value0
        elif data0 == 4: e1_d = 0.1 + value0 * 4.0
        elif data0 == 5: e2_d = 0.05 + value0 * 2.0
        elif data0 == 6: e3_d = 0.01 + value0 * 1.0
        elif data0 == 7: rel_t = 0.05 + value0 * 2.0
        elif data0 == 8: alg_mix = value0
        elif data0 == 9: att_t = 0.001 + value0 * 1.0
        elif data0 == 10: brightness = value0 * 2.0
        elif data0 == 11: trem_depth = value0
        elif data0 == 12: vib_depth = value0
        elif data0 == 13: trem_rate = 0.1 + value0 * 10.0
        elif data0 == 14: vib_rate = 0.1 + value0 * 15.0
        elif data0 == 15: master_tune = 0.95 + value0 * 0.1

# Patch 1 (Program Change 0) is the sound this script's module-level
# defaults describe, so a fresh instance and Patch 1 are the same thing.
# piece.py also reads it: a macro a composition does not set resolves here
# rather than to 0.5. Derived by tools/derive_patches.py - see that file
# before editing these numbers by hand.
PATCHES = {
    0: ("Init", (
        0.8, 0.25, 0, 0, 0.35, 0.375, 0.19, 0.225, 0.5, 0.009, 0.4, 0,
        0, 0.19, 0.326667, 0.5)),
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

