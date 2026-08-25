# mpvst-macro-labels: Space | Echo | Tone
"""A scripted send-style effect: the host audio runs through a low-pass,
a tempo-synced echo, and a hall reverb, all built from audioif modules.
Macro 1 is the reverb mix, macro 2 the echo send, macro 3 the tone."""

import audiodelays
import audiofilters
import audiofreeverb
import synthio
import vstaudio

SR = vstaudio.sample_rate()

tone = synthio.Math(synthio.MathOperation.SUM, 4200.0, 0.0, 0.0)
lp = audiofilters.Filter(
    filter=synthio.Biquad(synthio.FilterMode.LOW_PASS, tone, Q=0.8),
    sample_rate=SR, channel_count=2, bits_per_sample=16,
    samples_signed=True, buffer_size=2048)
echo = audiodelays.Echo(max_delay_ms=1200, delay_ms=375, decay=0.4, mix=0.25,
                        sample_rate=SR, channel_count=2, bits_per_sample=16,
                        samples_signed=True, buffer_size=2048,
                        freq_shift=False)
verb = audiofreeverb.Freeverb(roomsize=0.88, damp=0.4, mix=0.3,
                              sample_rate=SR, channel_count=2,
                              bits_per_sample=16, samples_signed=True,
                              buffer_size=2048)

lp.play(vstaudio.input())
echo.play(lp)
verb.play(echo)


def logmap(v, lo, hi):
    return lo * ((hi / lo) ** v)


def handle_event(event_type, channel, note_id, data0, value0, value1,
                 sample_position):
    if event_type != vstaudio.EVENT_PARAMETER:
        return
    if data0 == 0:
        verb.mix = 0.6 * value0
    elif data0 == 1:
        echo.mix = 0.6 * value0
    elif data0 == 2:
        tone.a = logmap(value0, 500.0, 12000.0)


def sync_echo():
    info = vstaudio.transport()
    bpm = info[2] if info[2] and info[2] > 1.0 else 120.0
    want = 60000.0 / bpm * 0.75
    if abs(echo.delay_ms - want) > 4.0:
        echo.delay_ms = want


sync_echo()
vstaudio.on_event(handle_event)
vstaudio.output(verb)
