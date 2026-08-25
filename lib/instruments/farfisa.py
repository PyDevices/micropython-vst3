# mpvst-macro-labels: Volume | Bass | Strings | Flute | Oboe | Trumpet | Multi-Tone Booster | Vibrato Rate | Vibrato Depth | Master Tune

import array
import math

import synthio
import vstaudio

SR = vstaudio.sample_rate()
TAU = 2.0 * math.pi

def make_table(parts, length=2048, gain=32000, asym=0.0):
    vals = [0.0] * length
    for mult, amp in parts:
        step = TAU * mult / length
        for i in range(length):
            vals[i] += amp * math.sin(step * i)
    if asym:
        # Multi-Tone Booster is a transistor overdrive stage, not just an
        # EQ swap: it clips the waveform asymmetrically for that fuzzy growl.
        for i in range(length):
            v = vals[i]
            vals[i] = v + asym * v * abs(v)
    peak = max(abs(v) for v in vals) if vals else 0.0
    if peak <= 0.0:
        peak = 1.0
    out = array.array("h", bytearray(length * 2))
    scale = gain / peak
    for i in range(length):
        out[i] = int(vals[i] * scale)
    return out

# Various Farfisa-like transistor waves
WAVE_STR = make_table([(n, 1.0 / n) for n in range(1, 40)])
WAVE_FLUTE = make_table(((1, 1.0), (3, 0.2)))
WAVE_OBOE = make_table([(n, 1.0 / n) for n in range(1, 40, 2)])
WAVE_TRUMPET = make_table(((1, 1.0), (2, 0.8), (3, 0.6), (4, 0.4)))
SINE = make_table(((1, 1.0),))

# Boosted (Multi-Tone Booster engaged) versions with asymmetric clipping
WAVE_STR_BOOST = make_table([(n, 1.0 / n) for n in range(1, 40)], asym=0.3)
WAVE_FLUTE_BOOST = make_table(((1, 1.0), (3, 0.2)), asym=0.3)
WAVE_OBOE_BOOST = make_table([(n, 1.0 / n) for n in range(1, 40, 2)], asym=0.3)
WAVE_TRUMPET_BOOST = make_table(((1, 1.0), (2, 0.8), (3, 0.6), (4, 0.4)), asym=0.3)

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
vstaudio.output(synth)

# Macros
volume = 0.8
bass = 1.0
strings = 1.0
flute = 1.0
oboe = 0.5
trumpet = 0.5
multi_tone = 0.0
vib_rate = 6.0
vib_depth = 0.0
master_tune = 1.0

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
    global volume, bass, strings, flute, oboe, trumpet, multi_tone, vib_rate, vib_depth, master_tune
    global serial
    
    k = key_of(channel, note_id, data0)
    
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        if len(voices) >= MAX_VOICES:
            steal_oldest()
            
        hz = synthio.midi_to_hz(data0 + value1) * master_tune
        amp = volume * value0
        
        env = synthio.Envelope(attack_time=0.01, decay_time=0.1, release_time=0.1, attack_level=1.0, sustain_level=1.0)
        
        # Multi-tone booster is a gritty overdrive stage (asymmetric clip
        # waveforms) that also brightens the tone with a hotter highpass
        boosted = multi_tone > 0.5
        cutoff = 5000.0 if boosted else 15000.0
        filter_mode = synthio.FilterMode.HIGH_PASS if boosted else synthio.FilterMode.LOW_PASS
        lp = synthio.Biquad(filter_mode, cutoff, Q=1.0)

        vib_lfo = synthio.LFO(waveform=SINE, rate=vib_rate, scale=vib_depth * 0.03) if vib_depth > 0.01 else None

        w_str = WAVE_STR_BOOST if boosted else WAVE_STR
        w_flute = WAVE_FLUTE_BOOST if boosted else WAVE_FLUTE
        w_oboe = WAVE_OBOE_BOOST if boosted else WAVE_OBOE
        w_trumpet = WAVE_TRUMPET_BOOST if boosted else WAVE_TRUMPET

        notes = []
        if bass > 0.01: notes.append(synthio.Note(hz * 0.5, waveform=w_str, envelope=env, filter=lp, amplitude=amp * bass * 0.2, bend=vib_lfo))
        if strings > 0.01: notes.append(synthio.Note(hz, waveform=w_str, envelope=env, filter=lp, amplitude=amp * strings * 0.2, bend=vib_lfo))
        if flute > 0.01: notes.append(synthio.Note(hz, waveform=w_flute, envelope=env, filter=lp, amplitude=amp * flute * 0.2, bend=vib_lfo))
        if oboe > 0.01: notes.append(synthio.Note(hz, waveform=w_oboe, envelope=env, filter=lp, amplitude=amp * oboe * 0.2, bend=vib_lfo))
        if trumpet > 0.01: notes.append(synthio.Note(hz, waveform=w_trumpet, envelope=env, filter=lp, amplitude=amp * trumpet * 0.2, bend=vib_lfo))
        
        serial += 1
        voices[k] = (tuple(notes), serial)
        for n in notes:
            synth.press(n)
            
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
        
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0: volume = value0
        elif data0 == 1: bass = value0
        elif data0 == 2: strings = value0
        elif data0 == 3: flute = value0
        elif data0 == 4: oboe = value0
        elif data0 == 5: trumpet = value0
        elif data0 == 6: multi_tone = value0
        elif data0 == 7: vib_rate = 0.1 + value0 * 10.0
        elif data0 == 8: vib_depth = value0
        elif data0 == 9: master_tune = 0.95 + value0 * 0.1

vstaudio.on_event(handle_event)
