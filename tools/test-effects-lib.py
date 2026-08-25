#!/usr/bin/env python3
"""Run every effects-library class through the real sidecar.

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
    "Compressor": ("effects.Compressor(src, threshold_db=-24, ratio=4)",
                   "squeeze"),
    "Compressor_fet": ("effects.Compressor(src, threshold_db=-20, ratio=8,"
                       " character='fet')", "squeeze"),
    "Limiter": ("effects.Limiter(src, ceiling_db=-12)", "squeeze"),
    "Expander": ("effects.Expander(src, threshold_db=-20, ratio=3)",
                 "mute_quiet"),
    "NoiseGate": ("effects.NoiseGate(src, threshold_db=-24)", "mute_quiet"),
    "DeEsser": ("effects.DeEsser(src, threshold_db=-40, frequency=150)",
                "squeeze"),
    "TransientShaper": ("effects.TransientShaper(src, attack_db=6,"
                        " sustain_db=-3)", "pass"),
    "MultibandCompressor": ("effects.MultibandCompressor(src)", "pass"),
    "ParametricEQ": ("effects.ParametricEQ(src, bands=[(220, -12, 2)])",
                     "squeeze"),
    "GraphicEQ": ("effects.GraphicEQ(src,"
                  " [0, 0, -9, -9, 0, 0, 0, 0, 0, 0])", "pass"),
    "DynamicEQ": ("effects.DynamicEQ(src, frequency=220,"
                  " threshold_db=-30)", "pass"),
    "LowPass": ("effects.LowPass(src, frequency=2000)", "pass"),
    "HighPass": ("effects.HighPass(src, frequency=1000)", "kill"),
    "BandPass": ("effects.BandPass(src, frequency=220, q=2)", "pass"),
    "Notch": ("effects.Notch(src, frequency=220, q=1)", "squeeze"),
    "LadderFilter": ("effects.LadderFilter(src, cutoff=3000,"
                     " resonance=0.3)", "pass"),
    "CombFilter": ("effects.CombFilter(src, frequency=440)", "pass"),
    "Reverb": ("effects.Reverb(src, preset='hall', mix=0.4)", "pass"),
    "Reverb_spring": ("effects.Reverb(src, preset='spring', mix=0.4)",
                      "pass"),
    "DigitalDelay": ("effects.DigitalDelay(src)", "pass"),
    "SlapbackDelay": ("effects.SlapbackDelay(src)", "pass"),
    "TapeDelay": ("effects.TapeDelay(src)", "pass"),
    "PingPongDelay": ("effects.PingPongDelay(src)", "pass"),
    "MultiTapDelay": ("effects.MultiTapDelay(src)", "pass"),
    "Chorus": ("effects.Chorus(src)", "pass"),
    "Flanger": ("effects.Flanger(src)", "pass"),
    "Phaser": ("effects.Phaser(src)", "pass"),
    "Tremolo": ("effects.Tremolo(src)", "pass"),
    "AutoPan": ("effects.AutoPan(src)", "pass"),
    "Vibrato": ("effects.Vibrato(src)", "pass"),
    "Rotary": ("effects.Rotary(src, speed='fast')", "pass"),
    "Overdrive": ("effects.Overdrive(src, drive=0.5)", "pass"),
    "Distortion": ("effects.Distortion(src)", "pass"),
    "Fuzz": ("effects.Fuzz(src)", "pass"),
    "Saturation": ("effects.Saturation(src)", "pass"),
    "Bitcrusher": ("effects.Bitcrusher(src, crush=0.5)", "pass"),
    "Exciter": ("effects.Exciter(src)", "pass"),
    "PitchShifter": ("effects.PitchShifter(src, semitones=7)", "pass"),
    "Harmonizer": ("effects.Harmonizer(src)", "pass"),
    "Octaver": ("effects.Octaver(src, down=0.6)", "pass"),
    "StereoWidener": ("effects.StereoWidener(src)", "pass"),
}

TEMPLATE = """import vstaudio
import effects

src = vstaudio.input()
fx = {ctor}
vstaudio.output(fx.output)
"""


def main():
    smoke, bundle = sys.argv[1], sys.argv[2]
    failures = []
    with tempfile.TemporaryDirectory() as workdir:
        for name, (ctor, check) in sorted(CASES.items()):
            script = Path(workdir) / (name + ".py")
            script.write_text(TEMPLATE.format(ctor=ctor))
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
