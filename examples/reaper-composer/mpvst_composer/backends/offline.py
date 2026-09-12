"""Render a project to a WAV here, with no DAW and no plug-in.

    from mpvst_composer.backends.offline import OfflineRenderer
    song.render("song.wav", OfflineRenderer)

The Reaper backend writes a project for a host to play. This one plays it,
through the same DSP: `audiorender` is audioif's offline renderer, and it
drives the very `audioinstruments` and `audioeffects` packages the sidecar
imports. Same notes, same components, same arithmetic, on a machine with
nothing installed on it.

It is not the quick way. This runs at about the speed of the music - sixteen
voices over two and a half minutes take two and a half minutes - where Reaper
bounces the same project in twenty-six seconds, eighteen sidecar startups and
all. What you get here is a render that needs no DAW and no plug-in, not a
render that arrives sooner.

It does not go through the vstaudio shim, because there is nothing left for
the adapter to do: `audiorender.deliver` crosses the normalized-to-MIDI seam
with the same multiply `mpvst_instrument_adapter` uses. Routing through a
script to reach the same multiply would buy a dependency on the installed
product and no fidelity. Two things the adapters do that the bare renderer
does not are guarded below, both places a component declares fewer than
sixteen macros.

The plug-in is still where the catalog comes from: `Project` reads patch
names, macro ranges and class IDs out of an installed bundle's
`catalog.json`. Without one, patches resolve to zero and this renders a
different arrangement than the bounce - the composer warns when that
happens, and `MPVST_BUNDLE` points it at the install.

What it cannot tell you is whether the plug-in works. The class IDs, the
state chunk, the item timing and the send topology are all things the
project file asserts and only a host can honour. Render here while you are
writing; render through Reaper before you believe it.

Not yet mixed here: pan automation (the pan is static, as in `apply_mix`)
and sidechain keys.

Needs `pydevices-audioif`, `pydevices-audioinstruments` and
`pydevices-audioeffects`.
"""

from __future__ import annotations

import numpy as np

import audiorender

from ..macros import macros_for_effect, macros_for_instrument
from ..models import DrumPattern, resolve_drum_note
from .base import BaseRenderer
from .reaper import TimeMap

#: Seconds of room after the last beat. Zero, because Reaper renders a
#: project to its content and stops, and a file this one cannot be compared
#: with is a file that cannot check the bounce. Raise it on the renderer when
#: you want to hear the tail ring out.
TAIL_SECONDS = 0.0

#: Constructor arguments that name a routing choice rather than a control,
#: so they are not passed to the component. The Reaper backend drops the same
#: ones out of its effect payload.
_ROUTING_KWARGS = ("sidechain", "duck", "patch", "preset")


def _interpolate(points, beat, default):
    """A value from `(beat, value)` points, held flat outside their span."""
    if not points:
        return default
    if beat <= points[0][0]:
        return points[0][1]
    for (first, low), (last, high) in zip(points, points[1:]):
        if beat <= last:
            if last == first:
                return high
            return low + (high - low) * (beat - first) / (last - first)
    return points[-1][1]


class _Composition:
    """A `Project` wearing the shape `audiorender` reads a composition in.

    audioif's renderer takes a module of module-level constants and three
    lookup methods; a Project is an object graph. This is the translation,
    and it is the only place that knows both.
    """

    def __init__(self, project, tail_seconds=TAIL_SECONDS):
        self._project = project
        self.time_map = TimeMap(project.tempo_markers)

        self.TITLE = project.name
        self.SAMPLE_RATE = project.sample_rate
        self.MASTER_GAIN_DB = 0.0
        self.TEMPO_MAP = self._tempo_rows()
        # content_end_measure() is the last bar with something in it, so the
        # song ends where the bar after it begins.
        self.TOTAL_BEATS = self.time_map.measure_beat_to_abs_beat(
            project.content_end_measure() + 1, 0.0)
        self.tempo = audiorender.TempoMap(self.TEMPO_MAP, self.TOTAL_BEATS,
                                          self.SAMPLE_RATE)
        self.SONG_SECONDS = self.tempo.beats_to_seconds(self.TOTAL_BEATS)
        self.RENDER_SECONDS = self.SONG_SECONDS + tail_seconds
        self.SECTIONS = [("song", 0.0, self.TOTAL_BEATS)]
        self.TRACKS = [self._track(t) for t in project.tracks]
        self.ACTIVE_LIMIT = None

    def _tempo_rows(self):
        rows = []
        for marker in self._project.tempo_markers:
            beat = self.time_map.measure_beat_to_abs_beat(marker.measure, 0.0)
            rows.append((beat, float(marker.bpm),
                         marker.signature[0], marker.signature[1]))
        return rows or [(0.0, 120.0, 4, 4)]

    def beats_to_seconds(self, beat):
        return self.tempo.beats_to_seconds(beat)

    # -- tracks ------------------------------------------------------------

    def _notes(self, track):
        notes = []
        for pattern in track.patterns:
            drums = isinstance(pattern, DrumPattern)
            if drums:
                pattern.resolve_chokes()
            origin = self.time_map.measure_beat_to_abs_beat(
                pattern.start_measure, 0.0)
            span = self._span_beats(pattern)
            for repeat in range(max(1, pattern.repeat)):
                start_of_loop = origin + repeat * span
                for event in pattern.events:
                    if drums:
                        pitch = resolve_drum_note(event.hit_type,
                                                  track.instrument,
                                                  self._project.patch_manifest)
                    else:
                        pitch = self._project.theory.get_midi_note(
                            event.degree, event.octave, event.accidental)
                    notes.append((start_of_loop + event.start_beat,
                                  event.length_beats, pitch,
                                  event.velocity / 127.0))
        notes.sort()
        return notes

    def _span_beats(self, pattern):
        """How far one repeat advances - the same arithmetic reaper.py uses.

        These two have to agree exactly. A pattern whose longest note crosses
        the barline spans two bars, and a backend that counts it as one lays
        every repeat after the first on the wrong beat.
        """
        default_bar = self.time_map._segment_at_measure(
            pattern.start_measure)["signature"][0]
        bar = max(1, int(getattr(pattern, "beats_per_bar", default_bar)
                         or default_bar))
        span = max(bar * max(1, pattern.length_measures),
                   getattr(pattern, "max_beat", 0.0), bar)
        return max(bar, -(-(span - 1e-9) // bar) * bar)

    def _points(self, automation):
        if automation is None:
            return []
        return sorted(
            (self.time_map.measure_beat_to_abs_beat(p.measure, p.beat), p.value)
            for p in automation.points)

    def _track(self, track):
        return {
            # audiorender names a stem after the script, so give it something
            # with the extension it expects to strip.
            "name": track.name,
            "script": "%s.py" % track.name.replace("/", "_"),
            "pan": float(track.pan),
            "notes": self._notes(track),
            "macros": macros_for_instrument(track.instrument, track.patch,
                                            self._project.patch_manifest,
                                            track.options),
            "macro_env": {a.macro_index: self._points(a)
                          for a in track.automation},
            "gain": float(track.volume),
            "gain_env": self._points(track.volume_automation),
        }

    # -- what audiorender asks of a composition ----------------------------

    def macro_value(self, track, index, beat):
        envelope = track["macro_env"].get(index)
        if envelope:
            return _interpolate(envelope, beat, 0.5)
        return track["macros"].get(index, 0.5)

    def track_gain(self, track, beat):
        return _interpolate(track["gain_env"], beat, track["gain"])

    def active_track_count(self, beat):
        return sum(1 for track in self.TRACKS
                   if any(start <= beat < start + length
                          for start, length, _pitch, _velocity
                          in track["notes"]))


class _Voice(audiorender.Voice):
    """A voice that ignores macros its instrument does not declare.

    The renderer sends all sixteen, because the format carries sixteen and a
    host always has a value for every parameter. An instrument with eight
    raises on the ninth. `mpvst_instrument_adapter` drops those on the floor,
    so this has to as well - the alternative is a backend that cannot render
    the two thirds of the library declaring fewer than sixteen.
    """

    def __init__(self, instrument):
        audiorender.Voice.__init__(self, instrument)
        labels = getattr(instrument, "MACRO_LABELS", None)
        if labels is None:
            labels = getattr(instrument, "macro_labels", ())
        self._macro_count = len(labels)

    def deliver(self, event, sample_position):
        if event[1] == audiorender.MACRO and event[2] >= self._macro_count:
            return
        audiorender.Voice.deliver(self, event, sample_position)


class OfflineRenderer(BaseRenderer):
    """Mix a project to a stereo WAV through the CPython audio packages."""

    #: Per-track progress lines, as `audiorender.render` prints them.
    verbose = True

    #: Seconds past the last beat to keep rendering (see `TAIL_SECONDS`).
    tail_seconds = TAIL_SECONDS

    def render(self, filepath: str):
        import audioinstruments

        project = self.project
        song = _Composition(project, self.tail_seconds)
        rate = song.SAMPLE_RATE
        frames = int(song.RENDER_SECONDS * rate)
        self._say("%s: %.1f s song, %.1f s render, %d tracks, %d aux"
                  % (song.TITLE, song.SONG_SECONDS, song.RENDER_SECONDS,
                     len(song.TRACKS), len(project.aux_tracks)))

        master = np.zeros((frames, 2), dtype=np.float32)
        buses = {aux.guid: np.zeros((frames, 2), dtype=np.float32)
                 for aux in project.aux_tracks}

        for track, entry in zip(project.tracks, song.TRACKS):
            patch = project.resolve_instrument_patch(track.instrument,
                                                     track.patch)

            instrument = audioinstruments.create(track.instrument, rate)
            # What the generated script does at load, before the host replays
            # the macro array over the top of it.
            if patch:
                instrument.program_change(patch)

            data = audiorender.render_track(
                entry, song, song.tempo, _Voice(instrument), frames,
                effects=[self._stage(spec, rate) for spec in track.inserts])
            data = audiorender.apply_mix(entry, data, song, song.tempo)
            self._say("  %-16s peak=%.3f" % (track.name,
                                             float(np.abs(data).max())))
            self._send(data, track.sends, buses)
            if track.mainsend:
                master += data

        # Aux tracks in declaration order, so one that feeds another - a mix
        # bus, say - is filled before it is read.
        for aux in project.aux_tracks:
            spec = {"effect": aux.effect, "preset": aux.preset,
                    "kwargs": aux.kwargs}
            data = self._through(self._stage(spec, rate), buses[aux.guid])
            data *= float(aux.volume)
            if aux.pan:
                data[:, 0] *= min(1.0, 1.0 - aux.pan)
                data[:, 1] *= min(1.0, 1.0 + aux.pan)
            self._say("  %-16s peak=%.3f (aux %s)"
                      % (aux.name, float(np.abs(data).max()), aux.effect))
            self._send(data, aux.sends, buses)
            if aux.mainsend:
                master += data

        for spec in project.master_inserts:
            master = self._through(self._stage(spec, rate), master)

        audiorender.write_wav(filepath, master, rate)
        self._say("wrote %s (peak %.3f)" % (filepath,
                                            float(np.abs(master).max())))
        return master

    # -- plumbing ----------------------------------------------------------

    def _say(self, line):
        if self.verbose:
            print(line)

    @staticmethod
    def _send(data, sends, buses):
        for send in sends:
            bus = buses.get(send["target"])
            if bus is not None:
                bus += data * float(send["level"])

    def _stage(self, spec, rate):
        """One insert, as the callable `audiorender.render_track` wants."""
        import audioeffects

        options = {key: value for key, value in (spec["kwargs"] or {}).items()
                   if key not in _ROUTING_KWARGS}
        macros = macros_for_effect(spec["effect"], spec.get("preset"),
                                   spec["kwargs"], self.project.patch_manifest)

        def build(pcm):
            source = audiorender.PcmSource(pcm, rate)
            effect = audioeffects.create(spec["effect"], source, rate,
                                         **options)
            # Every macro the component declares, not just the ones this
            # insert names: a VST parameter always has a value, and the
            # project file carries all sixteen. Sending only the named ones
            # would leave this render disagreeing with the bounce. Capped at
            # what the component declares, because `mpvst_effect_adapter`
            # caps it there and the seventeenth would raise.
            declared = len(getattr(effect, "MACRO_LABELS", ()))
            for index in range(min(audiorender.MACRO_COUNT, declared)):
                effect.set_macro(index, macros.get(index, 0.5) * 127.0)
            return audiorender.Puller(getattr(effect, "output", effect))

        return build

    @staticmethod
    def _through(stage, data, block=audiorender.BLOCK):
        """Push a rendered buffer through one effect stage, in blocks."""
        frames = len(data)
        pcm = (np.clip(data, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
        puller = stage(pcm)
        out = np.zeros((frames, 2), dtype=np.float32)
        cursor = 0
        while cursor < frames:
            count = min(block, frames - cursor)
            values = np.frombuffer(puller.pull_frames(count), dtype=np.int16)
            out[cursor:cursor + count] = (
                values.astype(np.float32).reshape(-1, 2) / 32768.0)
            cursor += count
        return out
