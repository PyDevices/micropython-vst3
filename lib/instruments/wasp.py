# mpvst-macro-labels: Volume | Filter Mode | Cutoff | Resonance | Noise Level | Amp Attack | Amp Decay | Amp Sustain | Amp Release | Master Tune

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

def noise_table(length=8192, seed=1234):
    out = array.array("h", bytearray(length * 2))
    state = seed
    for i in range(length):
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        out[i] = ((state >> 15) & 0xFFFF) - 32768
    return out

NOISE = noise_table()
NOISE_HZ = SR / 8192.0
# The Wasp's two VCOs are digital (CMOS) square-wave oscillators, not analog saws -
# odd harmonics only gives the thin, buzzy character real to the hardware.
WAVE_DIGI = make_table([(n, 1.0 / n) for n in range(1, 40, 2)])

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
vstaudio.output(synth)

# Macros
volume = 0.8
filter_mode = 0.0 # 0=LP, 1=HP
cutoff_val = 2000.0
res = 1.5
noise_lvl = 0.0
amp_a = 0.01
amp_d = 0.3
amp_s = 0.5
amp_r = 0.3
master_tune = 1.0

voices = {}
serial = 0
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
    global volume, filter_mode, cutoff_val, res, noise_lvl
    global amp_a, amp_d, amp_s, amp_r, master_tune
    global serial
    
    k = key_of(channel, note_id, data0)
    
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        if len(voices) >= MAX_VOICES:
            steal_oldest()
            
        hz = synthio.midi_to_hz(data0 + value1) * master_tune
        amp = volume * value0
        
        env = synthio.Envelope(attack_time=amp_a, decay_time=amp_d, release_time=amp_r, attack_level=1.0, sustain_level=amp_s)
        
        # Real Wasp filter is a 3-position switch (LP/BP/HP), not a 2-way toggle.
        if filter_mode < 0.33:
            fm = synthio.FilterMode.LOW_PASS
        elif filter_mode < 0.66:
            fm = synthio.FilterMode.BAND_PASS
        else:
            fm = synthio.FilterMode.HIGH_PASS
        flt = synthio.Biquad(fm, cutoff_val, Q=res)

        notes = []
        # Two digital square VCOs, detuned, for the raw doubled-oscillator Wasp tone.
        notes.append(synthio.Note(hz, waveform=WAVE_DIGI, envelope=env, filter=flt, amplitude=amp * 0.45))
        notes.append(synthio.Note(hz * 1.007, waveform=WAVE_DIGI, envelope=env, filter=flt, amplitude=amp * 0.45))

        if noise_lvl > 0.01:
            notes.append(synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env, filter=flt, amplitude=amp * noise_lvl * 0.2))
            
        serial += 1
        voices[k] = (tuple(notes), serial)
        for n in notes:
            synth.press(n)
            
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
        
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0: volume = value0
        elif data0 == 1: filter_mode = value0
        elif data0 == 2: cutoff_val = 50.0 * (100.0 ** value0)
        elif data0 == 3: res = 0.5 + value0 * 7.5 # pushes into self-oscillation like the real unstable filter
        elif data0 == 4: noise_lvl = value0
        elif data0 == 5: amp_a = 0.001 + value0 * 2.0
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
        0.8, 0, 0.80103, 0.133333, 0, 0.0045, 0.083333, 0.5, 0.0725,
        0.5)),
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

