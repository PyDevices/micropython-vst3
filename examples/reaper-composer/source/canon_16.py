"""Canon in D for sixteen voices - the same piece, two ways out.

    python source/canon_16.py                 write canon_16.rpp
    python source/canon_16.py --yaml          write canon_16.yaml as well

Pachelbel's Canon is one melody, played by three voices four bars apart, over
a bass that never changes. The harmony does not move for the whole piece, so
the only thing that can build is *density* - which is what the modern
arrangements do: the same line in half notes, then quarters, then eighths,
then sixteenths, stacking up.

That is an algorithm, not a transcription, so this file is functions. The
ground is eight scale degrees. Every other cell is derived from it: triads
built on each degree, a root-and-fifth ostinato, a descending sixteenth-note
cascade. Change GROUND and everything downstream follows.

It builds a *document* - the same dictionary `from_yaml.py` reads - and then
either hands it to the composer or writes it out as YAML. So one source makes
an example for both: read this if you like functions, read the YAML it emits
if you would rather see the notes.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import from_yaml                                              # noqa: E402
from mpvst_composer.backends.reaper import ReaperRenderer      # noqa: E402

#: D A B F# G D G A, as scale degrees in D major. One chord every two beats,
#: four bars round, and the source of every other cell in the piece.
GROUND = [1, 5, 6, 3, 4, 1, 4, 5]

#: The diatonic triad on each degree of the ground.
TRIAD = {1: (1, 3, 5), 5: (5, 7, 2), 6: (6, 1, 3), 3: (3, 5, 7), 4: (4, 6, 1)}

#: Pachelbel's treble: one half note per chord.
TREBLE = [(3, 5), (2, 5), (1, 5), (7, 4), (6, 4), (5, 4), (6, 4), (7, 4)]

BEATS_PER_CHORD = 2.0


def step(degree, octave, n):
    """`n` scale steps from (degree, octave); negative goes down."""
    index = (degree - 1) + n
    return (index % 7) + 1, octave + (index // 7)


def fifth(degree):
    """The diatonic fifth above a degree - four steps up."""
    return step(degree, 4, 4)[0]


def held(degree, octave, bars=4, velocity=64):
    """One note held for the whole cycle: a pedal point."""
    return [[0.0, bars * 4 - 0.1, degree, octave, velocity]]


def bassline(octave=2, velocity=80):
    """The ground itself, one half note per chord."""
    return [[i * BEATS_PER_CHORD, 1.9, d, octave, velocity]
            for i, d in enumerate(GROUND)]


def melody(subdivision, octave_shift=0):
    """The treble at a given subdivision.

    A half note per chord is Pachelbel. Halve it and the line fills in with
    passing tones; halve it again and again and you get the cascade the modern
    arrangements are known for. One function, four variations.
    """
    rows = []
    for chord, (degree, octave) in enumerate(TREBLE):
        octave += octave_shift
        start = chord * BEATS_PER_CHORD
        count = int(BEATS_PER_CHORD / subdivision)
        for i in range(count):
            if subdivision >= 2.0:
                deg, octv = degree, octave
            elif subdivision >= 1.0:
                deg, octv = step(degree, octave, 2 * i)
            elif subdivision >= 0.5:
                deg, octv = step(degree, octave, (1, 2, 1, 0)[i % 4])
            else:
                deg, octv = step(degree, octave, -i)
            rows.append([start + i * subdivision, subdivision * 0.9, deg, octv,
                         86 if i % 2 == 0 else 72])
    return rows


def chords(subdivision, octave=4, velocity=64):
    """The triad on each chord, struck every `subdivision` beats."""
    rows = []
    for chord, root in enumerate(GROUND):
        start = chord * BEATS_PER_CHORD
        for i in range(int(BEATS_PER_CHORD / subdivision)):
            for voice in TRIAD[root]:
                rows.append([start + i * subdivision, subdivision * 0.9,
                             voice, octave, velocity])
    return rows


def arpeggio(subdivision, octave=5, velocity=76):
    """Up and back down the triad, once per chord."""
    rows = []
    for chord, root in enumerate(GROUND):
        a, b, c = TRIAD[root]
        shape = (a, b, c, b)
        start = chord * BEATS_PER_CHORD
        for i in range(int(BEATS_PER_CHORD / subdivision)):
            rows.append([start + i * subdivision, subdivision * 0.9,
                         shape[i % 4], octave, velocity])
    return rows


def root_fifth(subdivision, octave=3, velocity=74):
    """Root, fifth, root, fifth - the oldest bass figure there is.

    A pedal in the organ sense: the bass alternates the root and its fifth
    while everything above it moves. At an eighth or a sixteenth it stops
    being a bass line and becomes the engine underneath one.
    """
    rows = []
    for chord, root in enumerate(GROUND):
        pair = (root, fifth(root))
        start = chord * BEATS_PER_CHORD
        for i in range(int(BEATS_PER_CHORD / subdivision)):
            rows.append([start + i * subdivision, subdivision * 0.9,
                         pair[i % 2], octave, velocity])
    return rows


def accents(velocity=70):
    """One note where each chord turns over - a bell on the change."""
    return [[i * BEATS_PER_CHORD, 0.6, TRIAD[d][0], 5, velocity]
            for i, d in enumerate(GROUND)]


PATTERNS = {
    "pedal":        held(1, 2),
    "ground":       bassline(),
    "half":         melody(2.0),
    "quarter":      melody(1.0),
    "eighth":       melody(0.5),
    "sixteenth":    melody(0.25),
    "half_high":    melody(2.0, octave_shift=1),
    "pad":          chords(2.0),
    "chords_q":     chords(1.0),
    "arp_e":        arpeggio(0.5),
    "rf_quarter":   root_fifth(1.0),
    "rf_sixteenth": root_fifth(0.25, octave=2),
    "accents":      accents(),
}

#: name, instrument, gain, pan, [(bar, pattern) ...]. Four-bar cycles.
#:
#: The ground plays from the first bar rather than under a bare drone: two
#: cycles of pedal before anything recognisable happened was half a minute of
#: nothing. The tune arrives at bar 5, and from there each cycle adds a layer
#: or subdivides one, until bar 33 begins taking them away again.
VOICES = [
    ("Pedal",      "prophet5",    -10.0,  0.0,  [(b, "pedal") for b in range(1, 41, 4)]),
    ("Cello",      "mellotron",    -3.0, -0.1,  [(b, "ground") for b in range(1, 41, 4)]),
    ("Continuo",   "cp70",         -9.0,  0.1,  [(b, "rf_quarter") for b in range(5, 37, 4)]),
    ("Violin I",   "solina",       -8.0, -0.35, [(5, "half"), (9, "quarter"), (13, "eighth"),
                                                 (17, "sixteenth"), (21, "eighth"), (25, "quarter"),
                                                 (29, "half"), (33, "half"), (37, "half")]),
    ("Violin II",  "solina",       -9.0,  0.0,  [(9, "half"), (13, "quarter"), (17, "eighth"),
                                                 (21, "sixteenth"), (25, "eighth"), (29, "quarter"),
                                                 (33, "half")]),
    ("Violin III", "solina",       -9.0,  0.35, [(13, "half"), (17, "quarter"), (21, "eighth"),
                                                 (25, "sixteenth"), (29, "eighth")]),
    ("Pad",        "jupiter8",    -14.0, -0.2,  [(b, "pad") for b in range(13, 37, 4)]),
    ("Chords",     "juno106",     -13.0,  0.2,  [(b, "chords_q") for b in range(9, 33, 4)]),
    ("Pluck",      "karplus",     -11.0, -0.45, [(b, "arp_e") for b in range(13, 33, 4)]),
    ("Bells",      "music_easel", -13.0,  0.45, [(b, "accents") for b in range(21, 37, 4)]),
    ("Counter",    "rhodes",      -13.0,  0.15, [(b, "chords_q") for b in range(17, 33, 4)]),
    ("Choir",      "vp330",       -15.0,  0.0,  [(b, "pad") for b in range(21, 37, 4)]),
    ("Ostinato",   "clavinet",    -14.0, -0.25, [(b, "rf_sixteenth") for b in range(17, 33, 4)]),
    ("Accent",     "dx7",         -15.0,  0.3,  [(b, "accents") for b in range(25, 33, 4)]),
    ("Pad 2",      "polysix",     -15.0, -0.3,  [(b, "pad") for b in range(25, 37, 4)]),
    ("Lead",       "cs80",        -11.0,  0.0,  [(21, "half_high"), (25, "half_high"),
                                                 (29, "half_high"), (33, "half_high")]),
]


def document():
    """The whole piece as the dictionary `from_yaml` reads."""
    return {
        "title": "Canon in D (sixteen voices)",
        "tempo": 64,
        "key": "D",
        "scale": "major",
        "patterns": {name: [list(r) for r in rows]
                     for name, rows in PATTERNS.items()},
        "aux_tracks": [{"name": "Chapel", "effect": "Reverb",
                        "preset": "hall", "mix": 1.0}],
        "tracks": [
            {"name": name, "instrument": instrument, "gain_db": gain,
             "pan": pan, "sends": [{"to": "Chapel", "level": 0.35}],
             "play": [{"bar": bar, "pattern": pattern} for bar, pattern in plays]}
            for name, instrument, gain, pan, plays in VOICES
        ],
        "mix_bus": {"ceiling_db": -2.0, "gain_db": 6.0},
    }


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    doc = document()
    if "--yaml" in sys.argv:
        import yaml
        path = os.path.join(here, "canon_16.yaml")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("# Generated by canon_16.py - edit that, or edit this\n"
                         "# and stop generating it. Either is a real song.\n")
            yaml.safe_dump(doc, handle, sort_keys=False, default_flow_style=None,
                           width=100)
        print("wrote %s" % path)
    song = from_yaml.build(doc)
    out = os.path.join(here, "canon_16.rpp")
    song.render(out, ReaperRenderer)
    print("wrote %s (%d voices)" % (out, len(VOICES)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
