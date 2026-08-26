# mpvst-macro-labels: Volume | Breath Pressure | Embouchure | Growl Rate | Growl Depth | Attack | Decay | Sustain | Release | Master Tune

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

# Complex FM carrier base for wind modeling
WAVE_WIND = make_table(((1, 1.0), (2, 0.4), (3, 0.2), (4, 0.1)))
SINE = make_table(((1, 1.0),))

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
vstaudio.output(synth)

# Macros
volume = 0.8
breath = 0.8
embouchure = 0.5
# Normalised 0..1, not Hz: the macro sets this straight from value0 and the
# LFO reads rate = 1.0 + growl_rate * 20.0. Written as 5.0 it meant 5 Hz,
# which is both unreachable from the macro and a 101 Hz "growl". 0.2 gives
# the 5 Hz that was plainly intended.
growl_rate = 0.2
growl_depth = 0.0
amp_a = 0.1
amp_d = 0.5
amp_s = 0.8
amp_r = 0.3
master_tune = 1.0

voices = {}
serial = 0
MAX_VOICES = 1 # Wind instruments are monophonic

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
    global volume, breath, embouchure, growl_rate, growl_depth
    global amp_a, amp_d, amp_s, amp_r, master_tune
    global serial
    
    k = key_of(channel, note_id, data0)
    
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        if len(voices) >= MAX_VOICES:
            steal_oldest()
            
        hz = synthio.midi_to_hz(data0 + value1) * master_tune
        
        # Breath pressure affects volume and filter cutoff simultaneously
        actual_amp = volume * value0 * breath
        
        env = synthio.Envelope(attack_time=amp_a, decay_time=amp_d, release_time=amp_r, attack_level=1.0, sustain_level=amp_s)
        
        cutoff = 500.0 + breath * 4000.0
        lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, cutoff, Q=1.0 + embouchure * 2.0)
        
        # Growl is simulated via fast vibrato/FM
        growl_lfo = synthio.LFO(waveform=SINE, rate=1.0 + growl_rate * 20.0, scale=growl_depth * 0.1) if growl_depth > 0.01 else None
        
        # Embouchure affects pitch slightly and harmonic content (via another layered note)
        n1 = synthio.Note(hz, waveform=WAVE_WIND, envelope=env, filter=lp, amplitude=actual_amp * 0.7, bend=growl_lfo)
        n2 = synthio.Note(hz * 2.0, waveform=SINE, envelope=env, filter=lp, amplitude=actual_amp * embouchure * 0.3, bend=growl_lfo)
        
        serial += 1
        voices[k] = ((n1, n2), serial)
        synth.press(n1)
        synth.press(n2)
            
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)

    elif event_type in (vstaudio.EVENT_CHANNEL_PRESSURE, vstaudio.EVENT_POLY_PRESSURE):
        # The VL1 is a real physical-modeled wind instrument: it's played
        # with a breath controller, so ongoing breath pressure re-shapes
        # the tone of a note already sounding, not just its initial hit
        pressure = value0
        for voice in voices.values():
            for n in voice[0]:
                if n.filter is not None:
                    n.filter.frequency = 500.0 + breath * (2000.0 + pressure * 3000.0)

    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0: volume = value0
        elif data0 == 1: breath = value0
        elif data0 == 2: embouchure = value0
        elif data0 == 3: growl_rate = value0
        elif data0 == 4: growl_depth = value0
        elif data0 == 5: amp_a = 0.001 + value0 * 1.0
        elif data0 == 6: amp_d = 0.05 + value0 * 3.0
        elif data0 == 7: amp_s = value0
        elif data0 == 8: amp_r = 0.01 + value0 * 4.0
        elif data0 == 9: master_tune = 0.95 + value0 * 0.1

# Patch 1 (Program Change 0) is the sound this script's module-level
# defaults describe, so a fresh instance and Patch 1 are the same thing.
# piece.py also reads it: a macro a composition does not set resolves here
# rather than to 0.5. Derived by tools/derive_patches.py - see that file
# before editing these numbers by hand.
PATCHES = {
    0: ("Init", (
        0.8, 0.8, 0.5, 0.2, 0, 0.099, 0.15, 0.8, 0.0725, 0.5)),
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

