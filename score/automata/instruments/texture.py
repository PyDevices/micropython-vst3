# mpvst-macro-labels: Air | Space
#
# Air texture: band-passed noise breathing very slowly under everything,
# felt more than heard. Macro 1 places the band, macro 2 the room.

import array
import math

import audiofreeverb
import synthio
import vstaudio

SR = vstaudio.sample_rate()
TAU = 2.0 * math.pi


def noise_table(length=8192, seed=31415926):
    out = array.array("h", bytearray(length * 2))
    state = seed
    for i in range(length):
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        out[i] = ((state >> 15) & 0xFFFF) - 32768
    return out


def logmap(v, lo, hi):
    return lo * ((hi / lo) ** v)


NOISE = noise_table()
NOISE_HZ = SR / 8192.0

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
air = synthio.Math(synthio.MathOperation.SUM, 2300.0, 0.0, 0.0)
bp = synthio.Biquad(synthio.FilterMode.BAND_PASS, air, Q=0.6)
env = synthio.Envelope(attack_time=3.0, decay_time=0.5, release_time=4.0,
                       attack_level=1.0, sustain_level=1.0)

verb = audiofreeverb.Freeverb(roomsize=0.92, damp=0.3, mix=0.5,
                              sample_rate=SR, channel_count=2,
                              bits_per_sample=16, samples_signed=True,
                              buffer_size=2048)
verb.play(synth)

voices = {}


def key_of(channel, note_id, pitch):
    return (channel, note_id if note_id >= 0 else pitch)


def handle_event(event_type, channel, note_id, data0, value0, value1,
                 sample_position):
    k = key_of(channel, note_id, data0)
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        old = voices.pop(k, None)
        if old is not None:
            synth.release(old)
        breathe = synthio.LFO(rate=0.11, scale=0.35 * (0.1 + 0.2 * value0),
                              offset=0.1 + 0.2 * value0)
        note = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env,
                            filter=bp, amplitude=breathe)
        voices[k] = note
        synth.press(note)
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        old = voices.pop(k, None)
        if old is not None:
            synth.release(old)
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0:
            air.a = logmap(value0, 900.0, 5200.0)
        elif data0 == 1:
            verb.mix = 0.2 + 0.4 * value0


vstaudio.on_event(handle_event)
vstaudio.output(verb)
