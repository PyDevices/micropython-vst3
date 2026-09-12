"""Turn a `Project` back into the document `from_yaml.py` reads.

    from mpvst_composer import to_yaml
    to_yaml.write(song, "song.yaml")

`from_yaml.build` goes document to Project. This goes the other way, so a
composition written against the Python API can be handed to someone who
would rather read notes than functions - and so the two halves can be
checked against each other, which is what `source/converge.py` does.

The round trip is not textual and does not try to be. It preserves what a
project *is* - the notes, where they fall, the instruments, the routing -
not how the Python that built it was organised. Two things change on the
way through by design:

Patterns get named. A Project holds pattern objects; the document holds a
dictionary of named cells that tracks refer to. Identical cells are found
by comparing their rows, so a piece that reuses one figure across eight
voices exports one cell played eight times, the way someone would write it
by hand. A cell nothing else matches gets a name from the track that plays
it.

Offsets get baked. A placement may shift a cell by a fraction of a beat;
on the way out the shift is already in the rows, and `offset` is gone. The
notes land in the same places either way.
"""

from __future__ import annotations

import math
from typing import Dict, List

from .models import AuxTrack, DrumPattern, Project

#: Kwargs `Project.add_mix_bus` supplies for its Limiter unless told
#: otherwise. Emitted only where the project differs from them, so a
#: `mix_bus:` block stays as short as the one someone would write.
_MIX_BUS_DEFAULTS = {"ceiling_db": -1.0, "gain_db": 0.0, "lookahead_ms": 1.5,
                     "release_ms": 160.0, "true_peak": True, "knee_db": 1.0}


def _round(value, places=6):
    """A float that reads like the number someone typed, not like binary."""
    value = round(float(value), places)
    return int(value) if value == int(value) else value


def _rows(pattern) -> List[list]:
    """One pattern as the document's rows: hits name a drum, notes give a
    length. `from_yaml.is_drum` tells them apart by the second column."""
    rows = []
    if isinstance(pattern, DrumPattern):
        for event in sorted(pattern.events, key=lambda e: e.start_beat):
            row = [_round(event.start_beat), event.hit_type]
            if event.velocity != 100:
                row.append(event.velocity)
            rows.append(row)
        return rows
    for event in sorted(pattern.events,
                        key=lambda e: (e.start_beat, e.degree, e.octave)):
        row = [_round(event.start_beat), _round(event.length_beats),
               event.degree, event.octave]
        if event.velocity != 100:
            row.append(event.velocity)
        rows.append(row)
    return rows


class _Cells:
    """The document's `patterns:` dictionary, built as tracks are walked.

    Cells are matched by content, so the same figure placed by six voices
    is stored once. Names come from the track that first plays a cell,
    which is the name a reader would have chosen anyway.
    """

    def __init__(self):
        self.by_rows: Dict[str, str] = {}
        self.patterns: Dict[str, List[list]] = {}

    def name_for(self, rows, hint) -> str:
        key = repr(rows)
        if key in self.by_rows:
            return self.by_rows[key]
        name = _slug(hint)
        if name in self.patterns:
            n = 2
            while "%s_%d" % (name, n) in self.patterns:
                n += 1
            name = "%s_%d" % (name, n)
        self.by_rows[key] = name
        self.patterns[name] = rows
        return name


def _slug(text) -> str:
    out = "".join(c.lower() if c.isalnum() else "_" for c in str(text))
    return "_".join(part for part in out.split("_") if part) or "cell"


def _effect_spec(effect: str, preset, kwargs) -> dict:
    spec = {"effect": effect}
    if preset:
        spec["preset"] = preset
    spec.update(kwargs or {})
    return spec


def _mix_bus_of(project: Project):
    """The aux track `add_mix_bus` made, if the project has one.

    It is not flagged, so it is recognised the way it was built: a Limiter
    aux that every other track sends into and nothing sends out of. Getting
    this wrong would export it twice - once as an aux track and again as
    the `mix_bus:` block - and the rebuilt project would sum through two
    limiters.
    """
    for aux in project.aux_tracks:
        if aux.effect != "Limiter" or aux.mainsend != 1:
            continue
        others = [t for t in list(project.tracks) + list(project.aux_tracks)
                  if t is not aux]
        if others and all(t.mainsend == 0 and
                          any(s["target"] == aux.guid for s in t.sends)
                          for t in others):
            return aux
    return None


def _tempo_markers(project: Project):
    """One marker per measure, last one wins.

    `Project()` starts with 120 bpm at bar 1, so a composition that sets its
    own tempo there leaves two markers on the same measure. The renderer
    takes the later one; exporting both would write a song at 120 with an
    immediate change to the real tempo, which is not what anyone wrote.
    """
    latest = {}
    for marker in project.tempo_markers:
        latest[marker.measure] = marker
    return [latest[measure] for measure in sorted(latest)]


def document(project: Project) -> dict:
    """The project as the dictionary `from_yaml.build` takes."""
    markers = _tempo_markers(project)
    first = markers[0] if markers else None
    beats_per_bar = first.signature[0] if first else 4
    bus = _mix_bus_of(project)
    cells = _Cells()

    doc = {
        "title": project.name,
        "tempo": _round(first.bpm) if first else 120,
        "key": project.theory.key.name,
        "scale": project.theory.scale.name.lower(),
    }
    if beats_per_bar != 4:
        doc["beats_per_bar"] = beats_per_bar

    changes = [{"bar": m.measure, "tempo": _round(m.bpm)}
               for m in markers[1:]]
    if changes:
        doc["tempo_changes"] = changes

    auxes = [aux for aux in project.aux_tracks if aux is not bus]
    if auxes:
        doc["aux_tracks"] = [_aux_spec(aux) for aux in auxes]

    by_guid = {aux.guid: aux.name for aux in project.aux_tracks}
    doc["patterns"] = cells.patterns          # filled by _track_spec below
    doc["tracks"] = [_track_spec(t, cells, by_guid, bus) for t in project.tracks]

    if project.master_inserts:
        doc["master_effects"] = [
            _effect_spec(fx["effect"], fx.get("preset"), fx.get("kwargs"))
            for fx in project.master_inserts]

    if bus is not None:
        block = {k: v for k, v in bus.kwargs.items()
                 if _MIX_BUS_DEFAULTS.get(k) != v}
        if bus.name != "Mix Bus":
            block["name"] = bus.name
        doc["mix_bus"] = block
    return doc


def _aux_spec(aux: AuxTrack) -> dict:
    spec = {"name": aux.name, "effect": aux.effect}
    if aux.preset:
        spec["preset"] = aux.preset
    spec.update(aux.kwargs or {})
    return spec


def _track_spec(track, cells: _Cells, by_guid, bus) -> dict:
    spec = {"name": track.name, "instrument": track.instrument}
    if track.patch and track.patch != "Default":
        spec["patch"] = track.patch
    if abs(track.volume - 1.0) > 1e-9:
        spec["gain_db"] = _round(20.0 * math.log10(track.volume), 2)
    if track.pan:
        spec["pan"] = _round(track.pan)
    spec.update(track.options or {})

    if track.inserts:
        spec["inserts"] = [
            _effect_spec(fx["effect"], fx.get("preset"), fx.get("kwargs"))
            for fx in track.inserts]

    # The sends into the mix bus are not the composition's; route_to_mix_bus
    # adds one per track and build() will add them again on the way back in.
    sends = [s for s in track.sends
             if bus is None or s["target"] != bus.guid]
    if sends:
        spec["sends"] = [{"to": by_guid[s["target"]],
                          "level": _round(s["level"])} for s in sends]

    play = []
    for pattern in track.patterns:
        rows = _rows(pattern)
        placement = {"bar": pattern.start_measure,
                     "pattern": cells.name_for(rows, track.name)}
        if pattern.repeat != 1:
            placement["repeat"] = pattern.repeat
        play.append(placement)
    if play:
        spec["play"] = play
    return spec


def write(project: Project, path, header=None):
    """Write the project's document to `path` as YAML.

    PyYAML is imported here rather than at the top so that `document()` -
    which is the part that does the work - stays on the standard library,
    like the rest of the composer.
    """
    import yaml

    doc = document(project)
    with open(path, "w", encoding="utf-8") as handle:
        if header:
            for line in header.strip().splitlines():
                handle.write("# %s\n" % line.strip())
        yaml.safe_dump(doc, handle, sort_keys=False,
                       default_flow_style=None, width=100)
    return path
