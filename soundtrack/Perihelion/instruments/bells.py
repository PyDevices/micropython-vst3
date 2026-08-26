# mpvst-macro-labels: Color | Echo | Space
#
# Aurora bells: a struck sine ring-modulated at a bell partial ratio, with
# a quieter upper partial, echo, and a long hall. Carries the signal motif.
# Macro 1 tunes the ring ratio (mellow to metallic), macro 2 the echo,
# macro 3 the room.

import array
import math

import audiodelays
import audiofreeverb
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


SINE = make_table(((1, 1.0),))

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
ratio = 3.36
strike_env = synthio.Envelope(attack_time=0.003, decay_time=1.4,
                              release_time=3.0, attack_level=1.0,
                              sustain_level=0.2)
partial_env = synthio.Envelope(attack_time=0.002, decay_time=0.7,
                               release_time=1.6, attack_level=1.0,
                               sustain_level=0.1)

echo = audiodelays.Echo(max_delay_ms=900, delay_ms=428, decay=0.45,
                        mix=0.25, sample_rate=SR, channel_count=2,
                        bits_per_sample=16, samples_signed=True,
                        buffer_size=2048)
verb = audiofreeverb.Freeverb(roomsize=0.9, damp=0.3, mix=0.35,
                              sample_rate=SR, channel_count=2,
                              bits_per_sample=16, samples_signed=True,
                              buffer_size=2048)
echo.play(synth)
verb.play(echo)

voices = {}
MAX_VOICES = 5
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


def handle_event(event_type, channel, note_id, data0, value0, value1,
                 sample_position):
    global serial, ratio
    k = key_of(channel, note_id, data0)
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        if len(voices) >= MAX_VOICES:
            steal_oldest()
        hz = synthio.midi_to_hz(data0 + value1)
        amp = 0.15 + 0.25 * value0
        pan = 0.3 - 0.2 * (serial % 3)
        strike = synthio.Note(hz, waveform=SINE, envelope=strike_env,
                              amplitude=amp, panning=pan,
                              ring_frequency=hz * ratio, ring_waveform=SINE,
                              ring_bend=0.0001)
        upper = synthio.Note(hz * 2.67, waveform=SINE, envelope=partial_env,
                             amplitude=amp * 0.3, panning=-pan)
        serial += 1
        voices[k] = ((strike, upper), serial)
        synth.press(strike)
        synth.press(upper)
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0:
            ratio = 2.9 + 1.3 * value0
        elif data0 == 1:
            echo.mix = 0.5 * value0
        elif data0 == 2:
            verb.mix = 0.15 + 0.4 * value0


# Patch 1 (Program Change 0) is the sound this script's module-level
# defaults describe, so a fresh instance and Patch 1 are the same thing.
# piece.py also reads it: a macro a composition does not set resolves here
# rather than to 0.5. Derived by tools/derive_patches.py - see that file
# before editing these numbers by hand.
PATCHES = {
    0: ("Init", (
        0.353846, 0.5, 0.5)),
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

vstaudio.output(verb)
