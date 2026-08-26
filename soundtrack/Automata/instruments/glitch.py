# mpvst-macro-labels: Echo
#
# Glitch percussion, three flavors by pitch: below 40 a ring-swept zap,
# 40-59 a crushed noise burst, 60 and up a bare tick. A tempo-synced
# echo (via vstaudio.transport) turns single hits into stutters; macro 1
# is the echo send.

import array
import math

import audiodelays
import audiofilters
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
    peak = 0.0
    for v in vals:
        a = v if v >= 0.0 else -v
        if a > peak:
            peak = a
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


def logmap(v, lo, hi):
    return lo * ((hi / lo) ** v)


SQUARE = make_table([(n, 1.0 / n) for n in range(1, 12, 2)])
SINE = make_table(((1, 1.0),))
NOISE = noise_table(seed=5647382910)
NOISE_HZ = SR / 8192.0
FALL = array.array("h", (32767, 0))

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
crush = audiofilters.Distortion(drive=0.82, mix=0.85,
                                sample_rate=SR, channel_count=2,
                                bits_per_sample=16, samples_signed=True,
                                buffer_size=2048)
echo = audiodelays.Echo(max_delay_ms=900, delay_ms=180, decay=0.45,
                        mix=0.2, sample_rate=SR, channel_count=2,
                        bits_per_sample=16, samples_signed=True,
                        buffer_size=2048, freq_shift=False)
crush.play(synth)
echo.play(crush)

tick_hp = synthio.Biquad(synthio.FilterMode.HIGH_PASS, 6000.0, Q=0.8)
zap_lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, 2400.0, Q=2.2)
burst_bp = synthio.Biquad(synthio.FilterMode.BAND_PASS, 2800.0, Q=1.0)

voices = {}
serial = 0


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

MAX_VOICES = 4


def sync_echo():
    info = vstaudio.transport()
    bpm = info[2] if info[2] and info[2] > 1.0 else 120.0
    want = 60000.0 / bpm * 0.75
    if abs(echo.delay_ms - want) > 4.0:
        echo.delay_ms = want


def handle_event(event_type, channel, note_id, data0, value0, value1,
                 sample_position):
    global serial
    k = key_of(channel, note_id, data0)
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        if len(voices) >= MAX_VOICES:
            steal_oldest()
        sync_echo()
        amp = 0.22 + 0.4 * value0
        pan = 0.4 - 0.2 * (serial % 5)
        if data0 < 40:
            env = synthio.Envelope(attack_time=0.001, decay_time=0.15,
                                   release_time=0.06, attack_level=1.0,
                                   sustain_level=0.0)
            sweep = synthio.LFO(waveform=FALL, once=True, rate=9.0,
                                scale=2.5, interpolate=True)
            note = synthio.Note(synthio.midi_to_hz(data0 + 24),
                                waveform=SQUARE, envelope=env,
                                filter=zap_lp, amplitude=amp, panning=pan,
                                ring_frequency=880.0, ring_waveform=SINE,
                                ring_bend=sweep)
        elif data0 < 60:
            env = synthio.Envelope(attack_time=0.001, decay_time=0.07,
                                   release_time=0.04, attack_level=1.0,
                                   sustain_level=0.0)
            note = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env,
                                filter=burst_bp, amplitude=amp, panning=pan)
        else:
            env = synthio.Envelope(attack_time=0.0005, decay_time=0.012,
                                   release_time=0.01, attack_level=1.0,
                                   sustain_level=0.0)
            note = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env,
                                filter=tick_hp, amplitude=amp, panning=pan)
        serial += 1
        voices[k] = ((note,), serial)
        synth.press(note)
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0:
            echo.mix = 0.45 * value0


# Patch 1 (Program Change 0) is the sound this script's module-level
# defaults describe, so a fresh instance and Patch 1 are the same thing.
# piece.py also reads it: a macro a composition does not set resolves here
# rather than to 0.5. Derived by tools/derive_patches.py - see that file
# before editing these numbers by hand.
PATCHES = {
    0: ("Init", (
        0.444444,)),
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


vstaudio.output(echo)
