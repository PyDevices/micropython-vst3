# mpvst-macro-labels: Volume | Pluck Position | String Damping | Body Resonance | Pick Hardness | Decay | Master Tune

import array
import math

import synthio
import vstaudio

SR = vstaudio.sample_rate()
TAU = 2.0 * math.pi

def noise_table(length=8192, seed=1234):
    out = array.array("h", bytearray(length * 2))
    state = seed
    for i in range(length):
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        out[i] = ((state >> 15) & 0xFFFF) - 32768
    return out

NOISE = noise_table()
NOISE_HZ = SR / 8192.0

KS_TABLE_LEN = 8192 # bounds the per-note-on cost of the algorithm below

def karplus_strong_table(hz, damping, pluck_pos, seed=1234):
    # The real Karplus-Strong algorithm: fill a delay line (length = one
    # period at this pitch) with noise, then repeatedly read it back and
    # feed each sample into a leaky lowpass (average with the previous
    # sample) before writing it back into the same slot. High harmonics
    # get averaged away faster than the fundamental every time around the
    # loop, which is what produces the natural pitched pluck-and-decay -
    # a filtered noise burst alone can't reproduce that decay curve because
    # it never actually loops back through itself.
    delay_len = max(4, min(KS_TABLE_LEN, int(SR / hz)))
    state = seed
    buf = [0.0] * delay_len
    for i in range(delay_len):
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        buf[i] = (((state >> 15) & 0xFFFF) - 32768) / 32768.0
    # Pluck position: subtracting a delayed copy of the burst from itself
    # is the classic extended-KS "pick position" filter - it carves a comb
    # notch wherever the string was plucked, same as a real string being
    # picked nearer the bridge vs. the middle
    p = 1 + int(pluck_pos * (delay_len - 2))
    for i in range(delay_len):
        buf[i] -= 0.5 * buf[i - p]
    fb = 0.90 + damping * 0.09 # feedback loss per lap; closer to 1 rings longer
    out = array.array("h", bytearray(KS_TABLE_LEN * 2))
    idx = 0
    prev = buf[0]
    for i in range(KS_TABLE_LEN):
        cur = buf[idx]
        avg = (cur + prev) * 0.5 * fb
        buf[idx] = avg
        out[i] = int(max(-32000.0, min(32000.0, avg * 32000.0)))
        prev = cur
        idx += 1
        if idx >= delay_len:
            idx = 0
    return out

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
vstaudio.output(synth)

# Macros
volume = 0.8
pluck_pos = 0.5 # where along the string it's plucked (comb-filters the burst)
damping = 0.5 # how fast the delay loop's feedback dies out
body_res = 0.5
pick_hard = 0.5
decay_time = 2.0
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
    global volume, pluck_pos, damping, body_res, pick_hard, decay_time, master_tune
    global serial

    k = key_of(channel, note_id, data0)

    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        if len(voices) >= MAX_VOICES:
            steal_oldest()

        hz = synthio.midi_to_hz(data0 + value1) * master_tune
        amp = volume * value0

        # 1. The string itself: a genuine Karplus-Strong delay/feedback
        # loop rendered into a table, so the ring is real comb-filtered
        # decay, not a static harmonic wavetable
        ks_wave = karplus_strong_table(hz, damping, pluck_pos)
        env_body = synthio.Envelope(attack_time=0.001, decay_time=decay_time, release_time=0.3, attack_level=1.0, sustain_level=0.0)
        lp_body = synthio.Biquad(synthio.FilterMode.LOW_PASS, 400.0 + body_res * 3000.0, Q=1.0 + body_res * 2.0)

        # 2. The pick/strike transient (short noise burst, harder pick = brighter)
        env_pick = synthio.Envelope(attack_time=0.001, decay_time=0.02 + pluck_pos * 0.05, release_time=0.01, attack_level=1.0, sustain_level=0.0)
        hp_pick = synthio.Biquad(synthio.FilterMode.HIGH_PASS, 1000.0 + pick_hard * 4000.0, Q=0.5)

        notes = []
        notes.append(synthio.Note(hz, waveform=ks_wave, envelope=env_body, filter=lp_body, amplitude=amp * 0.8))
        if pick_hard > 0.01:
            notes.append(synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env_pick, filter=hp_pick, amplitude=amp * pick_hard * 0.3))

        serial += 1
        voices[k] = (tuple(notes), serial)
        for n in notes:
            synth.press(n)

    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)

    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0: volume = value0
        elif data0 == 1: pluck_pos = value0
        elif data0 == 2: damping = value0
        elif data0 == 3: body_res = value0
        elif data0 == 4: pick_hard = value0
        elif data0 == 5: decay_time = 0.5 + value0 * 4.0
        elif data0 == 6: master_tune = 0.95 + value0 * 0.1

vstaudio.on_event(handle_event)
