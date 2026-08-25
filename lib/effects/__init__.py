"""Shared effect library for the MicroPython Effect plug-in.

Every class wires itself from an audio source (vstaudio.input() or a
previous effect's .output) and exposes its chain tail as .output.
See README.md for the catalogue.
"""

from .dynamics import (Compressor, Limiter, Expander, NoiseGate, DeEsser,
                       TransientShaper, MultibandCompressor)
from .eq import (ParametricEQ, GraphicEQ, LowPass, HighPass, BandPass,
                 Notch, LadderFilter, CombFilter, DynamicEQ)
from .reverb import Reverb
from .delay import (DigitalDelay, SlapbackDelay, TapeDelay, PingPongDelay,
                    MultiTapDelay)
from .modulation import (Chorus, Flanger, Phaser, Tremolo, AutoPan,
                         Vibrato, Rotary)
from .drive import (Overdrive, Distortion, Fuzz, Saturation, Bitcrusher,
                    Exciter)
from .pitch import PitchShifter, Harmonizer, Octaver, StereoWidener
