# mpvst-macro-labels: Tune | Space | Focus | Rise
"""Tuned air: the same band-passed noise the Perihelion shimmer is made of,
but with the band placed *on the note* instead of at a fixed frequency.

The original picks one center for every note and sweeps it upward, so it is
a reverse-cymbal - a sound effect that arrives on a downbeat. Tracking the
pitch instead turns the same engine into an instrument: the noise takes on
the note's pitch, sits in the chord, and the sweep becomes a slow bloom from
the fundamental up to the octave rather than a whistle sliding past it.

Macro 1 places the band on a harmonic (unison, octave, twelfth, or two
octaves and a fifth), macro 2 the room, macro 3 how tightly the band is
focused - low is breath, high is a sung tone - and macro 4 where the bloom
climbs to: nowhere, a fifth, an octave, or a twelfth above where it began.
Both of the frequency knobs are stepped rather than continuous, for the same
reason: a band between two partials is in tune with nothing.
"""

MACRO_LABELS = (
    "Tune", "Space", "Focus", "Rise",
)

# Patch 0 is the sound this instrument's defaults describe, so a fresh
# instance and patch 0 are the same thing - create() applies it. A macro
# a caller does not set resolves here rather than to the middle of its
# range.
PATCHES = {
    0: ('Init', (64, 95, 70, 64)),
    1: ('Breath', (46, 108, 24, 46)),
    2: ('Sung Octave', (64, 89, 102, 76)),
    3: ('Glass Twelfth', (89, 102, 89, 51)),
}

import array
import audiofreeverb
import synthio

from audioinstruments._support import (
    EVENT_NOTE_ON, EVENT_NOTE_OFF, EVENT_PARAMETER, key_of, logmap,
    noise_table,
)
from audioinstruments._support import Instrument
from audioinstruments import _support

NOISE = noise_table(seed=555444333)
RISE = array.array("h", (0, 32767))

# Whole harmonics rather than a continuous sweep: a band sitting on a partial
# of the note is in tune with it, and one sitting between two partials is
# not, however pretty the number in the middle looks.
HARMONICS = (1.0, 2.0, 3.0, 6.0)

# Where the bloom ends up, as a multiple of where it started - so the same
# rule applies to the sweep as to its starting point. A continuous Rise knob
# spent most of its travel landing between two partials, which measured as a
# band at 2.26x the note: in the right octave and in tune with nothing.
RISES = (1.0, 1.5, 2.0, 3.0)


def create(sample_rate, transport=None):
    SR = sample_rate
    NOISE_HZ = SR / 8192.0
    synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
    verb = audiofreeverb.Freeverb(roomsize=0.94, damp=0.2, mix=0.5,
                                  sample_rate=SR, channel_count=2,
                                  bits_per_sample=16, samples_signed=True,
                                  buffer_size=2048)
    # Slow either side. The attack is what makes it a swell rather than a
    # hit, and the release is what lets it hand over to the reverb instead
    # of stopping.
    env = synthio.Envelope(attack_time=3.0, decay_time=0.5, release_time=3.5,
                           attack_level=1.0, sustain_level=1.0)

    verb.play(synth)

    voices = {}
    MAX_VOICES = 6
    serial = 0
    harmonic = 2.0
    focus = 7.0
    # Stored as the multiple the climb adds, which is the destination minus
    # the start: an LFO scaled by `base * rise` on top of `base` arrives at
    # `base * (1 + rise)`.
    rise = 1.0

    def release_voice(k):
        voice = voices.pop(k, None)
        if voice is not None:
            synth.release(voice[0])

    def steal_oldest():
        _support.steal_oldest(voices, release_voice)

    def handle_event(event_type, channel, note_id, data0, value0, value1,
                     sample_position):
        nonlocal serial, harmonic, focus, rise
        k = key_of(channel, note_id, data0)
        if event_type == EVENT_NOTE_ON and value0 > 0.0:
            release_voice(k)
            if len(voices) >= MAX_VOICES:
                steal_oldest()
            # The note's own frequency, times whichever harmonic Tune picked.
            base = 440.0 * (2.0 ** ((data0 - 69) / 12.0)) * harmonic
            # The bloom lands on another partial of the same note - an
            # octave, a twelfth, or nowhere - so it stays inside the chord
            # rather than gliding out of it.
            climb = synthio.LFO(waveform=RISE, once=True, rate=1.0 / 7.0,
                                scale=base * rise, interpolate=True)
            freq = synthio.Math(synthio.MathOperation.SUM, base, climb, 0.0)
            bp = synthio.Biquad(synthio.FilterMode.BAND_PASS, freq, Q=focus)
            # A narrow band passes a small slice of the noise, so the
            # amplitude has to climb with the focus or the tuned settings
            # arrive far quieter than the breathy ones.
            amp = (0.10 + 0.22 * value0) * (1.0 + 0.22 * focus)
            note = synthio.Note(NOISE_HZ, waveform=NOISE, envelope=env,
                                filter=bp, amplitude=amp,
                                panning=0.3 - 0.6 * (serial % 2))
            serial += 1
            voices[k] = (note, serial)
            synth.press(note)
        elif event_type in (EVENT_NOTE_OFF, EVENT_NOTE_ON):
            release_voice(k)
        elif event_type == EVENT_PARAMETER:
            if data0 == 0:
                harmonic = HARMONICS[min(3, int(value0 * 4.0))]
            elif data0 == 1:
                verb.mix = 0.2 + 0.4 * value0
            elif data0 == 2:
                focus = logmap(value0, 0.9, 24.0)
            elif data0 == 3:
                rise = RISES[min(3, int(value0 * 4.0))] - 1.0

    instrument = Instrument(synth, handle_event, PATCHES, MACRO_LABELS,
                            transport=transport, output=verb)
    instrument.program_change(0)
    return instrument


if __name__ == "__main__":
    import mpvst_adapter

    mpvst_adapter.attach(create)
