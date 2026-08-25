"""Shared plumbing for the effects library.

Every effect class takes its audio source as the first argument - the
host input (``vstaudio.input()``) or another effect's ``output`` - builds
its chain immediately, and exposes the chain tail as ``.output``:

    import vstaudio
    from effects import Compressor, Reverb

    comp = Compressor(vstaudio.input(), threshold_db=-20, ratio=3)
    verb = Reverb(comp.output, preset="hall", mix=0.3)
    vstaudio.output(verb.output)

The underlying audioif/vstaudio nodes are kept as attributes so scripts
can bind macros straight to them.
"""

import math

import vstaudio

SAMPLE_RATE = vstaudio.sample_rate()


def pcm(buffer_size=2048):
    """The keyword bundle every audioif node wants."""
    return {
        "sample_rate": SAMPLE_RATE,
        "channel_count": 2,
        "bits_per_sample": 16,
        "samples_signed": True,
        "buffer_size": buffer_size,
    }


def db_to_gain(db):
    return 10.0 ** (db / 20.0)


def db_to_amplitude(db):
    """Biquad peaking/shelf A parameter."""
    return 10.0 ** (db / 40.0)


def logmap(value, lo, hi):
    """0..1 -> lo..hi, logarithmic; the natural mapping for frequencies."""
    return lo * ((hi / lo) ** value)


class Effect:
    """Base: subclasses set self.output to their chain tail."""

    output = None


# CircuitPython's audiofilters.Filter (and this engine's faithful port of
# it) runs one biquad state across the interleaved stereo stream, which
# halves every frequency the filter perceives: a biquad asked for f is
# centered at 2f. Verified against the CircuitPython oracle - mono is
# exact, stereo is shifted - so the library compensates here instead of
# diverging from upstream. Peaking EQ is unusable at this pin (upstream
# computes b2 with the wrong sign); ParametricEQ builds bells from notch
# and band-pass sections instead.
SPECTRAL_SCALE = 0.5


def filter_hz(frequency):
    """The value to hand a Biquad inside a stereo Filter so its true
    center lands at `frequency`."""
    return float(frequency) * SPECTRAL_SCALE
