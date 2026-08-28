#!/usr/bin/env python3
"""Run every audioeffects class through the real sidecar.

For each public class this writes a tiny script that builds the effect
from vstaudio.input() with default-ish arguments, runs it through the
VST3 effect class via the smoke host's --effect-script probe (quiet sine
then loud sine), and asserts the behaviour the effect promises:
dynamics squeeze or mute the right half, everything else passes signal.

Usage: test-effects-lib.py <smoke_host> <bundle.vst3>
"""

import re
import subprocess
import sys
import tempfile
from pathlib import Path

QUIET_IN = 0.014142
LOUD_IN = 0.353553

# name -> (constructor line, check)
# checks: "pass" output present both halves; "squeeze" loud reduced >=3 dB;
# "mute_quiet" quiet half near-silent while loud passes; "wet" loud present.
CASES = {
    "Compressor": ("audioeffects.Compressor(src, threshold_db=-24, ratio=4)",
                   "squeeze"),
    "Compressor_fet": ("audioeffects.Compressor(src, threshold_db=-20, ratio=8,"
                       " character='fet')", "squeeze"),
    "Limiter": ("audioeffects.Limiter(src, ceiling_db=-12)", "squeeze"),
    # The two options audiodynamics gained in phase 11. Both allocate and
    # both change the detector, so a host run is where a mistake in either
    # would show up as a stall rather than as a number.
    "Limiter-lookahead": ("audioeffects.Limiter(src, ceiling_db=-12,"
                          " lookahead_ms=5, true_peak=True)", "squeeze"),
    # "pass", not "squeeze": every Limiter patch sets its ceiling within a
    # decibel or two of full scale, which is what a limiter is for, and this
    # harness's loud half peaks around -9 dBFS. Nothing to catch is the
    # correct answer here.
    "Limiter-patch": ("audioeffects.Limiter(src, patch=2)", "pass"),
    "Compressor-patch": ("audioeffects.Compressor(src, patch=5)", "squeeze"),
    "Expander": ("audioeffects.Expander(src, threshold_db=-20, ratio=3)",
                 "mute_quiet"),
    "NoiseGate": ("audioeffects.NoiseGate(src, threshold_db=-24)", "mute_quiet"),
    "DeEsser": ("audioeffects.DeEsser(src, threshold_db=-40, frequency=150)",
                "squeeze"),
    "TransientShaper": ("audioeffects.TransientShaper(src, attack_db=6,"
                        " sustain_db=-3)", "pass"),
    "MultibandCompressor": ("audioeffects.MultibandCompressor(src)", "pass"),
    "ParametricEQ": ("audioeffects.ParametricEQ(src, bands=[(220, -12, 2)])",
                     "squeeze"),
    "GraphicEQ": ("audioeffects.GraphicEQ(src,"
                  " gains_db=[0, 0, -9, -9, 0, 0, 0, 0, 0, 0])", "pass"),
    "DynamicEQ": ("audioeffects.DynamicEQ(src, frequency=220,"
                  " threshold_db=-30)", "pass"),
    "LowPass": ("audioeffects.LowPass(src, frequency=2000)", "pass"),
    # Below a few hundred hertz the engine's biquad coefficients used to
    # quantize into nonsense, and this one returned silence in the host -
    # so the case is here as much for the "does it render at all" check as
    # for the corner. audioif's biquads are wider now; see its
    # docs/upstream-diff.md, "The biquads are Q15, so they cannot go low".
    "LowPass-100Hz": ("audioeffects.LowPass(src, frequency=100)", "pass"),
    "GraphicEQ-low": ("audioeffects.GraphicEQ(src,"
                      " gains_db=[9, 9, 9, 0, 0, 0, 0, 0, 0, 0])", "pass"),
    "HighPass": ("audioeffects.HighPass(src, frequency=1000)", "kill"),
    "BandPass": ("audioeffects.BandPass(src, frequency=220, q=2)", "pass"),
    # Tuned to the probe's own 220 Hz tone, so it annihilates it (-45 dB)
    # rather than merely denting it. This was "squeeze" back when a stereo
    # Filter shared one biquad state between the channels and every filter
    # sat an octave above where it was asked to sit: the notch landed on
    # 440 Hz and the tone lost 2 dB in the skirt.
    "Notch": ("audioeffects.Notch(src, frequency=220, q=1)", "kill"),
    "LadderFilter": ("audioeffects.LadderFilter(src, cutoff=3000,"
                     " resonance=0.3)", "pass"),
    "CombFilter": ("audioeffects.CombFilter(src, frequency=440)", "pass"),
    "Reverb": ("audioeffects.Reverb(src, preset='hall', mix=0.4)", "pass"),
    # Convolution, in the host rather than offline. The sidecar is where a
    # mistake in the allocation shows up as a stall or a dead instance
    # instead of as a number, and a quarter second of stereo impulse is
    # ~390 KB carved out of the engine's heap in one go.
    "ConvolutionReverb": ("audioeffects.ConvolutionReverb(src, seconds=0.25,"
                          " mix=0.5)", "pass"),
    "ConvolutionReverb-patch": ("audioeffects.ConvolutionReverb(src,"
                                " seconds=0.25, patch=2)", "pass"),
    "Reverb_spring": ("audioeffects.Reverb(src, preset='spring', mix=0.4)",
                      "pass"),
    "DigitalDelay": ("audioeffects.DigitalDelay(src)", "pass"),
    "SlapbackDelay": ("audioeffects.SlapbackDelay(src)", "pass"),
    "TapeDelay": ("audioeffects.TapeDelay(src)", "pass"),
    "PingPongDelay": ("audioeffects.PingPongDelay(src)", "pass"),
    "MultiTapDelay": ("audioeffects.MultiTapDelay(src)", "pass"),
    "Chorus": ("audioeffects.Chorus(src)", "pass"),
    "Flanger": ("audioeffects.Flanger(src)", "pass"),
    "Phaser": ("audioeffects.Phaser(src)", "pass"),
    "Tremolo": ("audioeffects.Tremolo(src)", "pass"),
    "AutoPan": ("audioeffects.AutoPan(src)", "pass"),
    "Vibrato": ("audioeffects.Vibrato(src)", "pass"),
    "Rotary": ("audioeffects.Rotary(src, speed='fast')", "pass"),
    # audioif's audiomath module, which the engine did not have before -
    # this case is as much "does the new native module reach the sidecar at
    # all" as it is a check on the effect.
    "RingMod": ("audioeffects.RingMod(src, frequency=220)", "pass"),
    # Driven by patch rather than by argument, so the patch surface itself
    # is exercised in a real host and not only in audioif's own tests.
    "RingMod-patch": ("audioeffects.RingMod(src, patch=1)", "pass"),
    "Overdrive": ("audioeffects.Overdrive(src, drive=0.5)", "pass"),
    "Distortion": ("audioeffects.Distortion(src)", "pass"),
    "Fuzz": ("audioeffects.Fuzz(src)", "pass"),
    "Saturation": ("audioeffects.Saturation(src)", "pass"),
    # The three characters are different curves, not one curve with
    # presets, so each gets its own trip through the host.
    "Saturation-tape": (
        "audioeffects.Saturation(src, amount=0.6, character='tape')",
        "pass"),
    "Saturation-console": (
        "audioeffects.Saturation(src, amount=0.6, character='console')",
        "pass"),
    "Bitcrusher": ("audioeffects.Bitcrusher(src, crush=0.5)", "pass"),
    "Bitcrusher-bits": ("audioeffects.Bitcrusher(src, bits=6)", "pass"),
    "Exciter": ("audioeffects.Exciter(src)", "pass"),
    # The microcontroller-scale use of the convolver: four partitions, and an
    # impulse built in Python at construction rather than loaded. The second
    # case is patch 5 rather than an adjacent one because the probe has only
    # the 220 Hz tone to work with, and most of the cabinets are within
    # 0.03 dB of each other there - "Broken Radio" is the one whose response
    # at that frequency actually differs.
    "CabinetSim": ("audioeffects.CabinetSim(src, patch=1)", "pass"),
    "CabinetSim-patch": ("audioeffects.CabinetSim(src, patch=5)", "pass"),
    # The audioecho module, and the three classes rebuilt on it. The
    # ping-pong case is the one that could not exist before: its repeats
    # alternate sides, which needs each channel fed into the other's line.
    "TapeDelay-loop": ("audioeffects.TapeDelay(src, time_ms=180)", "pass"),
    "TapeDelay-patch": ("audioeffects.TapeDelay(src, patch=2)", "pass"),
    "AnalogDelay": ("audioeffects.AnalogDelay(src, time_ms=200)", "pass"),
    "AnalogDelay-patch": ("audioeffects.AnalogDelay(src, patch=4)", "pass"),
    "PingPongDelay-cross": (
        "audioeffects.PingPongDelay(src, time_ms=160)", "pass"),
    "PitchShifter": ("audioeffects.PitchShifter(src, semitones=7)", "pass"),
    "Harmonizer": ("audioeffects.Harmonizer(src)", "pass"),
    "Octaver": ("audioeffects.Octaver(src, down=0.6)", "pass"),
    "Octaver-two-octaves": (
        "audioeffects.Octaver(src, down=0.4, down2=0.3, up=0.2)", "pass"),
    "StereoWidener": ("audioeffects.StereoWidener(src)", "pass"),
}

TEMPLATE = """import vstaudio
import audioeffects

src = vstaudio.input()
fx = {ctor}
vstaudio.output(fx.output)
"""


def factory_constructor(expression):
    """Turn a legacy constructor expression into the public factory call."""
    match = re.match(r"audioeffects\.([A-Za-z]+)\(src(.*)\)$", expression)
    if match is None:
        raise ValueError("not an audioeffects constructor: %s" % expression)
    name, options = match.groups()
    return ('audioeffects.create("%s", src, vstaudio.sample_rate()%s)'
            % (name, options))


def main():
    smoke, bundle = sys.argv[1], sys.argv[2]
    failures = []
    with tempfile.TemporaryDirectory() as workdir:
        for name, (ctor, check) in sorted(CASES.items()):
            script = Path(workdir) / (name + ".py")
            script.write_text(TEMPLATE.format(
                ctor=factory_constructor(ctor)))
            result = subprocess.run(
                [smoke, bundle, "--effect-script", str(script)],
                capture_output=True, text=True, timeout=300)
            match = re.search(
                r"EFFECT_RMS \S+ \S+ quiet_out=(\S+) loud_out=(\S+)",
                result.stdout)
            if result.returncode != 0 or match is None:
                failures.append(name)
                print("%-22s FAIL (probe: rc=%d)" % (name, result.returncode))
                continue
            quiet = float(match.group(1))
            loud = float(match.group(2))
            ok = loud > 0.005
            detail = "quiet=%.4f loud=%.4f" % (quiet, loud)
            if check == "kill":
                ok = loud < LOUD_IN * 0.1
                detail += " (band killed %.1f dB)" % (
                    -20 * __import__("math").log10(max(loud, 1e-9) / LOUD_IN))
            elif check == "squeeze":
                ok = ok and loud < LOUD_IN * 0.7
                detail += " (loud reduced %.1f dB)" % (
                    -20 * __import__("math").log10(max(loud, 1e-9) / LOUD_IN))
            elif check == "mute_quiet":
                ok = ok and quiet < QUIET_IN * 0.25
            if ok:
                print("%-22s PASS %s" % (name, detail))
            else:
                failures.append(name)
                print("%-22s FAIL %s" % (name, detail))
    print()
    if failures:
        print("EFFECTS LIB FAIL: %d of %d (%s)"
              % (len(failures), len(CASES), ", ".join(failures)))
        return 1
    print("EFFECTS LIB PASS: all %d cases" % len(CASES))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
