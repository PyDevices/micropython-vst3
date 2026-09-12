"""Write a song in YAML instead of Python.

    python from_yaml.py source/interlock.yaml

The other way in to `mpvst_composer`, for when you would rather describe a
song than program one. A YAML file names some patterns and says where they
play; this reads it and drives the same composer the Python examples use, so
anything you can express here is a real project with real routing.

It is deliberately smaller than the Python API. Patterns, tracks, sends, an
aux or two, a mix bus - the things a first song needs. When you outgrow it,
`mpvst_composer_guide.md` is the same library from the inside.

Needs PyYAML: `pip install pyyaml`.


THE FILE
--------

    title: Interlock
    tempo: 104
    key: D
    scale: dorian

    patterns:
      figure:                       # [beat, length, degree, octave]
        - [0.0, 0.5, 1, 4]
      pulse:                        # [beat, drum]
        - [0.0, kick]

    tracks:
      - name: Pluck
        instrument: karplus
        gain_db: -6
        play:
          - {bar: 1, pattern: figure, repeat: 8}
          - {bar: 9, pattern: figure, repeat: 8, offset: 0.5}

`degree` is a step of the scale, so 1 is the tonic and 8 is the octave above -
no MIDI numbers to look up, and a change of `key` moves the whole song. A
drum pattern uses names (`kick`, `snare`, `closed_hihat`) and the instrument's
own note map decides which key that is.

`offset` shifts every beat in that placement. Two tracks playing one pattern
half a beat apart interlock into a line neither of them is playing, and
walking the offset over successive placements is how a part drifts against
itself. That is the thing this format makes easy and a piano roll makes
tedious.
"""

from __future__ import annotations

import sys

import yaml

from mpvst_composer import DrumPattern, MidiEvent, MidiPattern, Note, Project, Scale
from mpvst_composer.backends.reaper import ReaperRenderer

def scale_of(name):
    key = str(name).replace("-", "_").upper()
    try:
        return getattr(Scale, key)
    except AttributeError:
        raise SystemExit("unknown scale %r - try %s"
                         % (name, ", ".join(s.name.lower() for s in Scale)))


def note_of(name):
    key = str(name).replace("#", "s").replace("b", "b").capitalize()
    try:
        return getattr(Note, key)
    except AttributeError:
        raise SystemExit("unknown key %r" % name)


def is_drum(rows):
    """A hit names its drum; a note gives a length. Told apart by the second
    column's type, so both may carry an optional trailing velocity."""
    return bool(rows) and isinstance(rows[0][1], str)


def build_pattern(rows, bar, repeat, offset, beats_per_bar):
    """One placement of a named pattern, shifted by `offset` beats."""
    if is_drum(rows):
        pattern = DrumPattern(start_measure=bar, repeat=repeat,
                              beats_per_bar=beats_per_bar)
        for row in rows:
            beat, hit = row[0], row[1]
            pattern.add_hit(float(beat) + offset, str(hit),
                            int(row[2]) if len(row) > 2 else 100)
        return pattern
    pattern = MidiPattern(start_measure=bar, repeat=repeat,
                          beats_per_bar=beats_per_bar)
    for row in rows:
        beat, length, degree, octave = row[0], row[1], row[2], row[3]
        pattern.add_event(MidiEvent(
            start_beat=float(beat) + offset, length_beats=float(length),
            degree=int(degree), octave=int(octave),
            velocity=int(row[4]) if len(row) > 4 else 100))
    return pattern


def load(path):
    with open(path, "r", encoding="utf-8") as handle:
        document = yaml.safe_load(handle)

    song = Project(name=document.get("title", "Untitled"))
    song.set_key(note_of(document.get("key", "C")),
                 scale_of(document.get("scale", "major")))
    beats_per_bar = int(document.get("beats_per_bar", 4))
    song.add_tempo_marker(measure=1, bpm=float(document.get("tempo", 120)),
                          signature=(beats_per_bar, 4))
    for marker in document.get("tempo_changes", []):
        song.add_tempo_marker(measure=int(marker["bar"]),
                              bpm=float(marker["tempo"]))

    patterns = document.get("patterns", {})
    auxes = {}
    for spec in document.get("aux_tracks", []):
        options = {k: v for k, v in spec.items()
                   if k not in ("name", "effect", "preset")}
        auxes[spec["name"]] = song.add_aux_track(
            spec["name"], effect=spec["effect"], preset=spec.get("preset"),
            **options)

    tracks = []
    for spec in document.get("tracks", []):
        track = song.add_track(spec["name"], instrument=spec["instrument"],
                               patch=spec.get("patch", "Default"))
        if "gain_db" in spec:
            track.volume = 10.0 ** (float(spec["gain_db"]) / 20.0)
        if "pan" in spec:
            track.pan = float(spec["pan"])
        for insert in spec.get("inserts", []):
            options = {k: v for k, v in insert.items()
                       if k not in ("effect", "preset")}
            track.add_insert(insert["effect"], preset=insert.get("preset"),
                             **options)
        for send in spec.get("sends", []):
            target = auxes.get(send["to"])
            if target is None:
                raise SystemExit("%s sends to %r, which is not an aux track"
                                 % (spec["name"], send["to"]))
            track.add_send(target, float(send.get("level", 1.0)))
        for placement in spec.get("play", []):
            name = placement["pattern"]
            if name not in patterns:
                raise SystemExit("%s plays %r, which is not in patterns"
                                 % (spec["name"], name))
            track.add_pattern(build_pattern(
                patterns[name], int(placement["bar"]),
                int(placement.get("repeat", 1)),
                float(placement.get("offset", 0.0)), beats_per_bar))
        tracks.append(track)

    for effect in document.get("master_effects", []):
        options = {k: v for k, v in effect.items()
                   if k not in ("effect", "preset")}
        song.add_master_effect(effect["effect"], preset=effect.get("preset"),
                               **options)

    mix = document.get("mix_bus")
    if mix:
        bus = song.add_mix_bus(**{k: v for k, v in mix.items()
                                  if k != "name"})
        song.route_to_mix_bus(bus)
    return song


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: from_yaml.py <song.yaml> [out.rpp]")
    source = sys.argv[1]
    song = load(source)
    out = sys.argv[2] if len(sys.argv) > 2 else source.rsplit(".", 1)[0] + ".rpp"
    song.render(out, ReaperRenderer)
    print("wrote %s" % out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
