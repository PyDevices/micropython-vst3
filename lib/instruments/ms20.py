# mpvst-macro-labels: Volume | HPF Cutoff | HPF Peak | LPF Cutoff | LPF Peak | Osc2 Pitch | EG2 Sweep | EG2 Attack | EG2 Decay | EG2 Sustain | EG2 Release | Ring Mod | Noise Level | VCA Attack | VCA Release | Master Tune

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

def noise_table(length=8192, seed=1234567):
    out = array.array("h", bytearray(length * 2))
    state = seed
    for i in range(length):
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        out[i] = ((state >> 15) & 0xFFFF) - 32768
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
NOISE = noise_table()
NOISE_HZ = SR / 8192.0

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
vstaudio.output(synth)

# Macros
volume = 0.8
hpf_cutoff = 100.0
hpf_peak = 1.0
lpf_cutoff = 2000.0
lpf_peak = 1.0
osc2_pitch = 1.0
eg2_sweep = 3000.0
eg2_a = 0.01
eg2_d = 0.3
eg2_s = 0.5
eg2_r = 0.3
ring_mod = 0.0
noise_lvl = 0.0
vca_a = 0.01
vca_r = 0.3
master_tune = 1.0

voices = {}
serial = 0
MAX_VOICES = 1
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
    global volume, hpf_cutoff, hpf_peak, lpf_cutoff, lpf_peak, osc2_pitch, eg2_sweep
    global eg2_a, eg2_d, eg2_s, eg2_r, ring_mod, noise_lvl, vca_a, vca_r, master_tune
    global serial, last_pitch
    
    k = key_of(channel, note_id, data0)
    
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        if len(voices) >= MAX_VOICES:
            steal_oldest()
            
        hz = synthio.midi_to_hz(data0 + value1) * master_tune
        amp = volume * value0
        
        env = synthio.Envelope(attack_time=vca_a, decay_time=eg2_d, release_time=vca_r, attack_level=1.0, sustain_level=1.0)

        env_tbl = env_shape_table(eg2_a, eg2_d, eg2_s)
        f_sweep = synthio.LFO(waveform=env_tbl, once=True, rate=1.0/max(0.01, eg2_a + eg2_d), scale=eg2_sweep, interpolate=True)
        lpf_freq = synthio.Math(synthio.MathOperation.SUM, lpf_cutoff, f_sweep, 0.0)

        # The MS-20's iconic HPF -> LPF chain can't be built as a single
        # series filter per Note, so osc1 runs through the resonant LPF and
        # osc2 through the resonant HPF, mixed the way the real panel's two
        # filters would be blended.
        lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, lpf_freq, Q=lpf_peak)
        hp = synthio.Biquad(synthio.FilterMode.HIGH_PASS, hpf_cutoff, Q=hpf_peak)

        ring_wave = ring_depth_table(ring_mod) if ring_mod > 0.01 else None

        o1 = synthio.Note(hz, waveform=SAW, envelope=env, filter=lp, amplitude=amp * 0.5,
                           ring_frequency=hz, ring_waveform=ring_wave)
        o2 = synthio.Note(hz * osc2_pitch, waveform=SQUARE, envelope=env, filter=hp, amplitude=amp * 0.5,
                           ring_frequency=hz, ring_waveform=ring_wave)
        notes = [o1, o2]
        if noise_lvl > 0.01:
            notes.append(synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env, filter=lp,
                                       amplitude=amp * noise_lvl * 0.4))

        serial += 1
        voices[k] = (tuple(notes), serial)
        for n in notes:
            synth.press(n)
            
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
        
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0: volume = value0
        elif data0 == 1: hpf_cutoff = 20.0 * (100.0 ** value0)
        elif data0 == 2: hpf_peak = 0.5 + value0 * 5.0
        elif data0 == 3: lpf_cutoff = 50.0 * (100.0 ** value0)
        elif data0 == 4: lpf_peak = 0.5 + value0 * 8.0 # MS-20 is very resonant
        elif data0 == 5: osc2_pitch = 1.0 + (value0 - 0.5)
        elif data0 == 6: eg2_sweep = value0 * 8000.0
        elif data0 == 7: eg2_a = 0.001 + value0 * 2.0
        elif data0 == 8: eg2_d = 0.05 + value0 * 3.0
        elif data0 == 9: eg2_s = value0
        elif data0 == 10: eg2_r = 0.01 + value0 * 4.0
        elif data0 == 11: ring_mod = value0
        elif data0 == 12: noise_lvl = value0
        elif data0 == 13: vca_a = 0.001 + value0 * 2.0
        elif data0 == 14: vca_r = 0.01 + value0 * 4.0
        elif data0 == 15: master_tune = 0.95 + value0 * 0.1

vstaudio.on_event(handle_event)
