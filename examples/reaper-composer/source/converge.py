"""Converge - one line, taken apart and put back together.

    python source/converge.py              build, export, rebuild, render both
    python source/converge.py --rpp        write converge.rpp as well
    python source/converge.py --keep       keep both WAVs instead of one

This is the round trip. The piece is written against the `mpvst_composer`
API - `Project`, `add_track`, `MidiPattern` - rather than as a document. It
is then exported to `converge.yaml`, read back by `from_yaml.py`, and the
rebuilt project is rendered alongside the original. The two WAVs should be
byte-identical, and the script says so.

That is the whole point of the file: the Python API and the YAML are two
front doors to one composer, and this proves they arrive at the same place.
`canon_16.py` goes the other way round - it builds a document and hands it
straight to `from_yaml.build` - so between them the loop is closed.

The music is built to match. Every voice plays SEED, the same eight scale
degrees. They begin together in half notes, fan out as each voice takes the
line at its own note value, pile up in the middle, and collapse back into
unison at the end. One line, several routes, converging.
"""

from __future__ import annotations

import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import from_yaml                                              # noqa: E402
from mpvst_composer import MidiEvent, MidiPattern, Note, Project, Scale  # noqa: E402
from mpvst_composer import to_yaml                            # noqa: E402
from mpvst_composer.backends.offline import OfflineRenderer    # noqa: E402

BEATS_PER_BAR = 4
TEMPO = 96

#: The line. Eight degrees of D dorian; everything below is this, re-timed.
SEED = [1, 5, 4, 3, 2, 6, 5, 1]

#: The degree under each bar of the seed - one root per two seed notes.
ROOTS = SEED[0::2]


def line(note_value, octave, velocity=100):
    """SEED at one note value. Eight notes of `note_value` beats each."""
    return [(i * note_value, note_value, degree, octave, velocity)
            for i, degree in enumerate(SEED)]


def pedal(note_value, octave, velocity=92):
    """Root and fifth alternating under each bar of the seed.

    A pedal is the part that does not move while everything else does, so it
    is written from ROOTS rather than SEED: one bar per root, root on the
    downbeat and its fifth halfway through.
    """
    rows = []
    per_bar = int(BEATS_PER_BAR / note_value)
    for bar, root in enumerate(ROOTS):
        for step in range(per_bar):
            degree = root if step % 2 == 0 else root + 4
            rows.append((bar * BEATS_PER_BAR + step * note_value,
                         note_value, degree, octave, velocity))
    return rows


def chords(octave, velocity=76):
    """A triad per bar, held. The harmony the fanned-out voices move over."""
    rows = []
    for bar, root in enumerate(ROOTS):
        for degree in (root, root + 2, root + 4):
            rows.append((bar * BEATS_PER_BAR, float(BEATS_PER_BAR),
                         degree, octave, velocity))
    return rows


def cascade(octave, velocity=84):
    """The seed descending in sixteenths - the busiest the piece gets."""
    rows = []
    for i, degree in enumerate(SEED):
        for step in range(4):
            rows.append((i * 2.0 + step * 0.5, 0.5,
                         degree + (3 - step), octave, velocity))
    return rows


#: One section of the piece, in bars and in beats.
SECTION_BARS = 4
SECTION_BEATS = SECTION_BARS * BEATS_PER_BAR


def pattern_of(rows, bar):
    """Rows into a cell placed at `bar`, looped to fill one section.

    SEED is eight notes, so a voice playing it in half notes fills the whole
    section and one playing it in eighths fills a quarter of it. Rather than
    write the fast lines out four times, the cell repeats - which is the
    thing `repeat` is for, and which only lands on the right beats because
    a four-bar cell is now counted as four bars.
    """
    content = max(start + length for start, length, _d, _o, _v in rows)
    cell = MidiPattern(start_measure=bar,
                       repeat=max(1, int(round(SECTION_BEATS / content))),
                       beats_per_bar=BEATS_PER_BAR)
    for start, length, degree, octave, velocity in rows:
        cell.add_event(MidiEvent(start_beat=start, length_beats=length,
                                 degree=degree, octave=octave,
                                 velocity=velocity))
    return cell


#: name, instrument, gain dB, pan, and the cell each section gets.
#:
#: Seven sections of four bars: together, fanning out, everything at once,
#: then collapsing back. A voice with None in a section sits that one out,
#: and the shape of this table is the shape of the piece - read down a
#: column to see what is playing, across a row to see what one voice does.
VOICES = [
    # name        instrument   gain   pan   bars 1-4        5-8              9-12             13-16            17-20            21-24            25-28
    ("Pedal",     "taurus",    -7.0,  0.0, [pedal(2.0, 2), pedal(2.0, 2),   pedal(1.0, 2),   pedal(1.0, 2),   pedal(1.0, 2),   pedal(2.0, 2),   pedal(2.0, 2)]),
    ("Bass",      "minimoog",  -9.0, -0.2, [line(2.0, 3),  line(2.0, 3),    line(2.0, 3),    line(2.0, 3),    line(2.0, 3),    line(2.0, 3),    line(2.0, 3)]),
    ("Strings",   "solina",   -12.0, -0.5, [line(2.0, 4),  line(2.0, 4),    chords(4),       chords(4),       chords(4),       line(2.0, 4),    line(2.0, 4)]),
    ("Rhodes",    "rhodes",   -13.0,  0.4, [line(2.0, 4),  line(1.0, 4),    line(1.0, 4),    line(1.0, 4),    line(1.0, 4),    line(2.0, 4),    line(2.0, 4)]),
    ("Juno",      "juno106",  -14.0,  0.6, [None,          line(0.5, 5),    line(0.5, 5),    line(0.5, 5),    line(0.5, 5),    None,            None]),
    ("Pluck",     "karplus",  -15.0, -0.7, [None,          None,            cascade(5),      cascade(5),      cascade(5),      None,            None]),
    ("Pad",       "jupiter8", -15.0,  0.0, [None,          chords(3),       chords(3),       chords(3),       chords(3),       chords(3),       None]),
    ("Bells",     "polysix",  -17.0,  0.7, [None,          None,            line(1.0, 6),    line(0.5, 6),    line(1.0, 6),    None,            None]),
    ("Lead",      "prophet5", -13.0,  0.0, [None,          None,            None,            line(1.0, 5),    line(1.0, 5),    line(2.0, 5),    line(2.0, 5)]),
]


def build() -> Project:
    """The piece, written against the composer API."""
    song = Project(name="Converge")
    song.set_key(Note.D, Scale.DORIAN)
    song.add_tempo_marker(measure=1, bpm=TEMPO,
                          signature=(BEATS_PER_BAR, 4))

    hall = song.add_aux_track("Hall", effect="Reverb", mix=1.0)

    for name, instrument, gain_db, pan, sections in VOICES:
        track = song.add_track(name, instrument=instrument)
        track.volume = 10.0 ** (gain_db / 20.0)
        track.pan = pan
        track.add_send(hall, 0.30)
        for index, rows in enumerate(sections):
            if rows:
                track.add_pattern(pattern_of(rows, 1 + index * SECTION_BARS))

    # +6 dB lands the piece at -13.5 LUFS, inside the band audio_qc.py
    # checks. Its loudness range is narrow - 3.0 LU, where Canon gets 12.7 -
    # and that is the writing, not the limiter: this starts with four voices
    # and grows to eight, where Canon starts with one and grows to sixteen.
    # Backing the bus off to +2 was tried and moved the range not at all.
    song.route_to_mix_bus(song.add_mix_bus(ceiling_db=-2.0, gain_db=6.0))
    return song


def digest(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    written = build()

    yaml_path = to_yaml.write(
        written, os.path.join(here, "converge.yaml"),
        header="Exported from converge.py. Edit either one - they are the\n"
               "same song, and the script checks that they still are.")
    print("wrote %s" % yaml_path)

    rebuilt = from_yaml.load(yaml_path)

    if "--rpp" in sys.argv:
        out = os.path.join(here, "converge.rpp")
        rebuilt.render(out, from_yaml.renderer_for(out))
        print("wrote %s" % out)

    direct = os.path.join(here, "converge.wav")
    through_yaml = os.path.join(here, "converge_from_yaml.wav")
    written.render(direct, OfflineRenderer)
    rebuilt.render(through_yaml, OfflineRenderer)

    same = digest(direct) == digest(through_yaml)
    print("\n%s\n  %s\n  %s\n  %s"
          % ("The two routes converge." if same
             else "THE TWO ROUTES DISAGREE.",
             digest(direct)[:16] + "  written directly",
             digest(through_yaml)[:16] + "  round-tripped through YAML",
             "identical" if same else "different audio - the export lost something"))

    if same and "--keep" not in sys.argv:
        os.remove(through_yaml)
    return 0 if same else 1


if __name__ == "__main__":
    raise SystemExit(main())
