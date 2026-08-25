# mpvst-macro-labels: Center | Space
#
# Air swell: band-passed noise whose center climbs while the note swells -
# the reverse-cymbal rise into a downbeat. Macro 1 places the band, macro 2
# the room.

import array
import math

import audiofreeverb
import synthio
import vstaudio

SR = vstaudio.sample_rate()
TAU = 2.0 * math.pi


def noise_table(length=8192, seed=555444333):
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
RISE = array.array("h", (0, 32767))

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
center = synthio.Math(synthio.MathOperation.SUM, 2400.0, 0.0, 0.0)
env = synthio.Envelope(attack_time=2.2, decay_time=0.5, release_time=1.8,
                       attack_level=1.0, sustain_level=1.0)

verb = audiofreeverb.Freeverb(roomsize=0.93, damp=0.25, mix=0.5,
                              sample_rate=SR, channel_count=2,
                              bits_per_sample=16, samples_signed=True,
                              buffer_size=2048)
verb.play(synth)

voices = {}
MAX_VOICES = 3
serial = 0


def key_of(channel, note_id, pitch):
    return (channel, note_id if note_id >= 0 else pitch)


def release_voice(k):
    voice = voices.pop(k, None)
    if voice is not None:
        synth.release(voice[0])


def steal_oldest():
    oldest = None
    for k in voices:
        if oldest is None or voices[k][1] < voices[oldest][1]:
            oldest = k
    if oldest is not None:
        release_voice(oldest)


def handle_event(event_type, channel, note_id, data0, value0, value1,
                 sample_position):
    global serial
    k = key_of(channel, note_id, data0)
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_voice(k)
        if len(voices) >= MAX_VOICES:
            steal_oldest()
        amp = 0.15 + 0.3 * value0
        climb = synthio.LFO(waveform=RISE, once=True, rate=1.0 / 3.0,
                            scale=3400.0, interpolate=True)
        freq = synthio.Math(synthio.MathOperation.SUM, center, climb, 0.0)
        bp = synthio.Biquad(synthio.FilterMode.BAND_PASS, freq, Q=2.4)
        note = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env,
                            filter=bp, amplitude=amp,
                            panning=0.25 - 0.5 * (serial % 2))
        serial += 1
        voices[k] = (note, serial)
        synth.press(note)
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        release_voice(k)
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0:
            center.a = logmap(value0, 900.0, 7800.0)
        elif data0 == 1:
            verb.mix = 0.2 + 0.4 * value0


vstaudio.on_event(handle_event)
vstaudio.output(verb)
