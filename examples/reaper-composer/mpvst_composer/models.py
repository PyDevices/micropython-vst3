import json
import os
import random
import uuid
from typing import Dict, List, Mapping, Optional, Tuple

from .theory import Note, Scale, TheoryEngine


class TempoMarker:
    def __init__(self, measure: int, bpm: float, signature: Tuple[int, int] = (4, 4), transition: str = "square"):
        self.measure = measure
        self.bpm = bpm
        self.signature = signature
        self.transition = transition


class AutomationPoint:
    def __init__(self, measure: int, beat: float, value: float):
        self.measure = measure
        self.beat = beat
        self.value = value


class MacroAutomation:
    def __init__(self, macro_index: int):
        self.macro_index = macro_index
        self.points: List[AutomationPoint] = []

    def add_point(self, measure: int, beat: float, value: float):
        self.points.append(AutomationPoint(measure, beat, value))


class VolumeAutomation:
    def __init__(self):
        self.points: List[AutomationPoint] = []

    def add_point(self, measure: int, beat: float, value: float):
        self.points.append(AutomationPoint(measure, beat, value))


class PanAutomation:
    def __init__(self):
        self.points: List[AutomationPoint] = []

    def add_point(self, measure: int, beat: float, value: float):
        self.points.append(AutomationPoint(measure, beat, value))


class MidiEvent:
    def __init__(self, start_beat: float, length_beats: float, degree: int, octave: int = 4, velocity: int = 100, accidental: int = 0):
        self.start_beat = start_beat
        self.length_beats = length_beats
        self.degree = degree
        self.octave = octave
        self.velocity = velocity
        self.accidental = accidental


class MidiControlEvent:
    def __init__(self, start_beat: float, cc_num: Optional[int] = None, pitch_bend: Optional[int] = None, value: int = 0):
        self.start_beat = start_beat
        self.cc_num = cc_num
        self.pitch_bend = pitch_bend
        self.value = value


def _update_pattern_span(pattern, start_beat: float, length_beats: float):
    max_beat = start_beat + length_beats
    pattern.max_beat = max(getattr(pattern, "max_beat", 0.0), max_beat)
    bar = max(1, int(getattr(pattern, "beats_per_bar", 4)))
    # The epsilon is what keeps a cell that ends exactly on the barline from
    # claiming the next bar as well. Sixteen beats of content in 4/4 is four
    # measures, not five, and without this a `repeat` laid every loop one bar
    # further out than the last - a silent bar between them. `content_end_measure`
    # has always subtracted it; this did not.
    pattern.length_measures = max(pattern.length_measures,
                                  int((max_beat - 1e-9) // bar) + 1)


class MidiPattern:
    def __init__(self, start_measure: int, repeat: int = 1, beats_per_bar: int = 4):
        self.start_measure = start_measure
        self.repeat = repeat
        self.beats_per_bar = beats_per_bar
        self.events: List[MidiEvent] = []
        self.control_events: List[MidiControlEvent] = []
        self.length_measures = 1
        self.max_beat = 0.0

    def add_event(self, event: MidiEvent):
        self.events.append(event)
        _update_pattern_span(self, event.start_beat, event.length_beats)

    def add_chord(self, start_beat: float, length_beats: float, root_degree: int, chord_degrees: List[int], octave: int = 4, velocity: int = 100):
        """
        Helper to add a chord (multiple MidiEvents) at once based on absolute scale degrees.
        Get chord_degrees using theory.get_chord_degrees(root_degree, Chord.TRIAD)
        """
        for deg in chord_degrees:
            self.add_event(MidiEvent(start_beat, length_beats, deg, octave, velocity))

    @classmethod
    def create_arp(cls, start_measure: int, root_degree: int, chord_degrees: List[int],
                   repeat: int = 1, note_length: float = 0.25, direction: str = "up",
                   octave: int = 4, velocity: int = 100, bars: int = 1, beats_per_bar: int = 4):
        """
        Generates a MidiPattern consisting of an arpeggiated chord.
        direction: "up", "down", or "updown"
        Fills `bars` bars (default 1) rather than stopping after one chord pass.
        """
        pat = cls(start_measure, repeat, beats_per_bar=beats_per_bar)
        degrees = sorted(chord_degrees)
        if direction == "down":
            degrees = list(reversed(degrees))
        elif direction == "updown":
            if len(degrees) > 1:
                degrees = degrees + list(reversed(degrees))[1:-1]
        if not degrees:
            return pat

        current_beat = 0.0
        total_beats = max(1, bars) * beats_per_bar
        i = 0
        while current_beat < total_beats - 1e-9:
            deg = degrees[i % len(degrees)]
            remaining = total_beats - current_beat
            length = min(note_length, remaining)
            pat.add_event(MidiEvent(current_beat, length, deg, octave, velocity))
            current_beat += note_length
            i += 1
        return pat

    def add_control_event(self, event: MidiControlEvent):
        self.control_events.append(event)

    def humanize(self, velocity_jitter: int = 10, timing_jitter_beats: float = 0.02):
        for ev in self.events:
            v_offset = random.randint(-velocity_jitter, velocity_jitter)
            ev.velocity = max(1, min(127, ev.velocity + v_offset))
            t_offset = random.uniform(-timing_jitter_beats, timing_jitter_beats)
            ev.start_beat = max(0.0, ev.start_beat + t_offset)

    def apply_swing(self, amount: float = 0.60, subdivision: float = 0.25):
        """
        Pushes off-beat events late by a percentage amount.
        amount=0.5 is straight timing, amount=0.66 is perfect triplet swing.
        subdivision=0.25 means it swings every 16th note.
        """
        for ev in self.events:
            pos = ev.start_beat % (subdivision * 2)
            if pos >= subdivision - 0.01 and pos <= subdivision + 0.01:
                delay = (amount - 0.5) * (subdivision * 2)
                ev.start_beat += delay


class AuxTrack:
    def __init__(self, name: str, effect: str, preset: Optional[str] = None, **kwargs):
        self.name = name
        self.guid = "{" + str(uuid.uuid4()).upper() + "}"
        self.effect = effect
        self.preset = preset
        self.kwargs = kwargs
        self.volume = 1.0
        self.pan = 0.0
        self.mainsend = 1
        self.sends: List[Dict] = []
        self.volume_automation: Optional[VolumeAutomation] = None
        self.pan_automation: Optional[PanAutomation] = None

    def add_send(self, aux, send_level: float = 1.0, src_chan: int = 0, dst_chan: int = 0, mode: int = 0):
        self.sends.append({
            "target": aux.guid,
            "level": send_level,
            "src_chan": src_chan,
            "dst_chan": dst_chan,
            "mode": mode,
        })


class Track:
    def __init__(self, name: str, instrument: str, patch: str = "Default",
                 **options):
        self.name = name
        self.guid = "{" + str(uuid.uuid4()).upper() + "}"
        self.instrument = instrument
        self.patch = patch
        #: Anything named after one of the instrument's macros, applied over
        #: the patch. Same rule as an insert's keywords.
        self.options = options

        self.patterns: List = []
        self.sends: List[Dict] = []
        self.inserts: List[Dict] = []
        self.automation: List[MacroAutomation] = []
        self.volume_automation: Optional[VolumeAutomation] = None
        self.pan_automation: Optional[PanAutomation] = None

        self.volume = 1.0
        self.pan = 0.0
        self.mainsend = 1

    def add_pattern(self, pattern):
        self.patterns.append(pattern)

    def add_automation(self, automation: MacroAutomation):
        self.automation.append(automation)

    def add_volume_automation(self, auto: VolumeAutomation):
        self.volume_automation = auto

    def add_pan_automation(self, auto: PanAutomation):
        self.pan_automation = auto

    def add_send(self, aux, send_level: float = 1.0, src_chan: int = 0, dst_chan: int = 0, mode: int = 0):
        """
        Route this track into `aux` (an AuxTrack or Track).
        dst_chan=0 -> destination channels 1/2; dst_chan=2 -> channels 3/4 (sidechain key).
        mode: 0=Post-Fader, 1=Pre-FX, 3=Post-FX. Reaper AUXRECV is written on the destination.
        """
        self.sends.append({
            "target": aux.guid,
            "level": send_level,
            "src_chan": src_chan,
            "dst_chan": dst_chan,
            "mode": mode,
        })

    def add_insert(self, effect: str, preset: Optional[str] = None, **kwargs):
        self.inserts.append({
            "effect": effect,
            "preset": preset,
            "kwargs": kwargs,
        })


def _new_guid() -> str:
    return "{" + str(uuid.uuid4()).upper() + "}"


class Project:
    def __init__(self, name: str = "MPVST Project"):
        self.name = name
        self.theory = TheoryEngine()

        self.tempo_markers: List[TempoMarker] = []
        self.tracks: List[Track] = []
        self.aux_tracks: List[AuxTrack] = []
        self.master_inserts: List[Dict] = []

        self.sample_rate = 48000
        self.render_bit_depth = 24
        self.render_tail_ms = 1000
        self.render_file: Optional[str] = None

        self.add_tempo_marker(measure=1, bpm=120, signature=(4, 4))
        self.vst_registry = {}
        self._load_catalog()

    def _load_catalog(self):
        """Learn every component, and every class ID, from wherever each lives.

        Two sources, because the question has two halves. What a component
        *is* - its macro labels and ranges, its patches, which key plays which
        drum - belongs to audiocomponents, and the packages answer for
        themselves when they are installed. What MPVST *calls* it - the VST3
        class ID a project file has to name - is the plug-in's own assignment,
        and only the installed bundle's catalog.json has it.

        So the packages are asked first and the catalog fills in behind them:
        every class ID, plus the components pip does not have. That is what
        lets a project be written, and rendered by OfflineRenderer, on a
        machine where MPVST was never installed.

        This replaces two older readers - a regex over moduleinfo.json's JSON5
        comments, and a patches_dump.json produced by running the plug-in's
        engine as a subprocess. Both are gone.
        """
        self.patch_manifest = {"instruments": {}, "effects": {}}
        self._patches = self.patch_manifest
        self.catalog = {}
        # Reaper's own 32-bit id per CID, filled in by _load_reaper_numeric_ids
        # below. Initialised here so every path out of this method leaves it set.
        self.vst_numeric = {}

        from_packages = self._load_components()

        path = self._catalog_path()
        if path is None:
            if from_packages:
                print("Note: catalog.json not found, so class IDs are "
                      "unavailable and only OfflineRenderer can run. Install "
                      "MPVST or set MPVST_BUNDLE to write a Reaper project.")
            else:
                print("Warning: no catalog.json in any VST3 folder and no "
                      "audiocomponents packages installed. Named patches and "
                      "class IDs are unavailable; install MPVST, set "
                      "MPVST_BUNDLE, or pip install pydevices-audioinstruments "
                      "and pydevices-audioeffects.")
            self._load_reaper_numeric_ids()
            return

        with open(path, "r", encoding="utf-8") as handle:
            document = json.load(handle)

        stale = []
        for item in document.get("classes", []):
            name = item["name"]
            record = (item["cid"].upper(), item.get("display_name", name))
            self.catalog[name] = item
            self.vst_registry[name] = record
            self.vst_registry[record[1]] = record
            bucket = "effects" if item["kind"] == "effect" else "instruments"
            entry = {
                # index -> [name, midi values]. Both halves are load-bearing:
                # resolve_instrument_patch matches on the name, and patch_midi
                # reads the values to seed the macro array. Keeping only the
                # name left every instrument rendering at defaults instead of
                # the patch it was designed with.
                "patches": {str(p["index"]): [p["name"], list(p.get("macros", ()))]
                            for p in item.get("patches", ())},
                "macros": item.get("macro_labels", []),
                "ranges": item.get("macro_ranges", []),
                "note_map": item.get("note_map"),
            }
            installed = self.patch_manifest[bucket].get(name)
            if installed is None:
                self.patch_manifest[bucket][name] = entry
            elif _describes_differently(installed, entry):
                stale.append(name)

        if stale:
            # The bundle stages its own copy of the library, so it can be a
            # different version than pip has. That is invisible until two
            # renders of the same project disagree, which is exactly the
            # comparison OfflineRenderer exists to make - so say it out loud.
            print("Note: %d component(s) differ between the installed bundle "
                  "and the audiocomponents packages (%s%s). Renders here "
                  "follow the packages; a Reaper bounce follows the bundle. "
                  "Reinstall MPVST to bring them back together."
                  % (len(stale), ", ".join(sorted(stale)[:4]),
                     ", ..." if len(stale) > 4 else ""))
        self._load_reaper_numeric_ids()

    def _load_components(self):
        """Component metadata from the audiocomponents packages, if installed.

        Reads the same declared attributes `lib/mpvst_catalog.py` reads when
        it builds catalog.json, because they are the source that file is
        scraped from. Returns whether anything was found.
        """
        found = False
        for package, bucket in (("audioinstruments", "instruments"),
                                ("audioeffects", "effects")):
            try:
                module = __import__(package)
            except ImportError:
                continue
            for name in getattr(module, "ALL", ()):
                try:
                    # Instruments are modules behind a lazy loader; effects are
                    # classes on the package.
                    component = (module.load(name) if hasattr(module, "load")
                                 else getattr(module, name))
                except Exception:                     # noqa: BLE001
                    continue                          # one bad module is not fatal
                self.patch_manifest[bucket][name] = _component_entry(component)
                found = True
        return found

    def _catalog_path(self):
        """The installed bundle's catalog, wherever this machine keeps VST3s."""
        override = os.environ.get("MPVST_BUNDLE")
        roots = [override] if override else []
        local = os.environ.get("LOCALAPPDATA", os.path.expanduser("~/AppData/Local"))
        common = os.environ.get("COMMONPROGRAMFILES", r"C:\Program Files\Common Files")
        roots += [
            os.path.join(local, "Programs", "Common", "VST3", "MPVST.vst3"),
            os.path.join(common, "VST3", "MPVST.vst3"),
            os.path.expanduser("~/.vst3/MPVST.vst3"),
            "/usr/lib/vst3/MPVST.vst3",
        ]
        for root in roots:
            candidate = os.path.join(root, "Contents", "Resources", "catalog.json")
            if os.path.isfile(candidate):
                return candidate
        return None

    def _load_reaper_numeric_ids(self):
        """Reaper's 32-bit VST3 id lives in reaper-vstplugins64.ini next to the CID."""
        import re
        local = os.environ.get("LOCALAPPDATA", os.path.expanduser("~/AppData/Local"))
        appdata = os.environ.get("APPDATA", os.path.expanduser("~/AppData/Roaming"))
        candidates = [
            os.path.join(os.path.dirname(r"C:\Users\bradb\REAPER\reaper.exe"), "reaper-vstplugins64.ini"),
            os.path.join(appdata, "REAPER", "reaper-vstplugins64.ini"),
            os.path.join(local, "REAPER", "reaper-vstplugins64.ini"),
        ]
        pat = re.compile(
            r"MPVST\.vst3<\d+=[^,\n]+,(\d+)\{([0-9A-Fa-f]{32})",
            re.IGNORECASE,
        )
        for path in candidates:
            if not os.path.isfile(path):
                continue
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
            except OSError:
                continue
            for m in pat.finditer(text):
                self.vst_numeric[m.group(2).upper()] = int(m.group(1))
            if self.vst_numeric:
                return

    def resolve_vst(self, key: str) -> Tuple[str, str, int]:
        """Return (cid, display_name, reaper_numeric_id) for an instrument module or effect class.

        Script Host CIDs load default_instrument.py / default_effect.py, so
        every track would be the same sound. Callers must use the per-class
        CID, which is what catalog.json carries.
        """
        rec = self.vst_registry.get(key)
        if rec is None:
            rec = self.vst_registry.get(key.replace(" ", ""))
        if rec is None:
            raise KeyError(
                f"No MPVST CID for {key!r}. Check catalog.json in the "
                f"installed bundle."
            )
        cid, display_name = rec
        numeric = self.vst_numeric.get(cid.upper(), 0)
        return cid, display_name, numeric

    def set_key(self, key: Note, scale: Scale):
        self.theory = TheoryEngine(key=key, scale=scale)

    def add_tempo_marker(self, measure: int, bpm: float, signature: Tuple[int, int] = None, transition: str = "square"):
        if not signature:
            signature = self.tempo_markers[-1].signature if self.tempo_markers else (4, 4)
        self.tempo_markers.append(TempoMarker(measure, bpm, signature, transition))
        self.tempo_markers.sort(key=lambda x: x.measure)

    def signature_at(self, measure: int) -> Tuple[int, int]:
        sig = (4, 4)
        for m in self.tempo_markers:
            if measure >= m.measure:
                sig = m.signature
            else:
                break
        return sig

    def add_track(self, name: str, instrument: str, patch: str = "Default",
                  **options) -> Track:
        t = Track(name, instrument, patch, **options)
        self.tracks.append(t)
        return t

    def add_aux_track(self, name: str, effect: str, preset: Optional[str] = None, **kwargs) -> AuxTrack:
        aux = AuxTrack(name, effect, preset, **kwargs)
        self.aux_tracks.append(aux)
        return aux

    def add_master_effect(self, effect: str, preset: Optional[str] = None, **kwargs):
        self.master_inserts.append({
            "effect": effect,
            "preset": preset,
            "kwargs": kwargs,
        })

    def add_mix_bus(self, name: str = "Mix Bus", **limiter_kwargs) -> AuxTrack:
        """A summing track with a Limiter insert. Call route_to_mix_bus() after all tracks exist."""
        kwargs = {"ceiling_db": -1.0, "gain_db": 0.0, "lookahead_ms": 1.5,
                  "release_ms": 160.0, "true_peak": True, "knee_db": 1.0}
        kwargs.update(limiter_kwargs)
        return self.add_aux_track(name, effect="Limiter", **kwargs)

    def route_to_mix_bus(self, bus: AuxTrack):
        """Send every instrument and return aux into `bus`; mute their hardware master sends."""
        for t in self.tracks:
            t.mainsend = 0
            # Avoid a second send if the composition already routed this track.
            if not any(s.get("target") == bus.guid for s in t.sends):
                t.add_send(bus, send_level=1.0)
        for a in self.aux_tracks:
            if a is bus:
                continue
            a.mainsend = 0
            if not any(s.get("target") == bus.guid for s in getattr(a, "sends", [])):
                a.add_send(bus, send_level=1.0)

    def _instrument_entry(self, instrument: str) -> Dict:
        entry = self.patch_manifest.get("instruments", {}).get(instrument, {})
        if not isinstance(entry, dict):
            return {}
        return entry

    def _instrument_patches(self, instrument: str) -> Dict:
        entry = self._instrument_entry(instrument)
        if "patches" in entry and isinstance(entry["patches"], dict):
            return entry["patches"]
        # Legacy dump: { "0": ["Default", [...]] }
        return {k: v for k, v in entry.items() if str(k).isdigit()}

    def resolve_instrument_patch(self, instrument: str, patch_name: str) -> int:
        patches = self._instrument_patches(instrument)
        for idx_str, patch_data in patches.items():
            if isinstance(patch_data, list) and patch_data and patch_data[0] == patch_name:
                return int(idx_str)
            if isinstance(patch_data, str) and patch_data == patch_name:
                return int(idx_str)
        print(f"Warning: Patch '{patch_name}' not found for instrument '{instrument}'. Defaulting to 0.")
        return 0

    def instrument_note_map(self, instrument: str) -> Optional[List]:
        entry = self._instrument_entry(instrument)
        return entry.get("note_map")

    def content_end_measure(self) -> int:
        end = 1
        for tr in self.tracks:
            for pat in tr.patterns:
                bar = max(1, int(getattr(pat, "beats_per_bar", self.signature_at(pat.start_measure)[0])))
                span = max(getattr(pat, "length_measures", 1), 1)
                if getattr(pat, "max_beat", 0) > 0:
                    span = max(span, int((pat.max_beat - 1e-9) // bar) + 1)
                end = max(end, pat.start_measure + span * max(1, pat.repeat) - 1)
        return end

    def apply_sidechain_duck(
        self,
        source_track: Track,
        dest_track: Track,
        hit_type: str = "kick",
        depth: float = 0.45,
        attack_beats: float = 0.03,
        hold_beats: float = 0.08,
        release_beats: float = 0.22,
        floor: float = None,
    ):
        """
        Audible ducking that does not depend on MPVST Compressor (which has no key=).

        Writes a volume envelope on `dest_track` that dips at every matching hit on
        `source_track`. Also used alongside a NoiseGate(duck=True) insert + AUXRECV
        key send when the host presents 4-channel input.
        """
        ducked = floor if floor is not None else max(0.05, 1.0 - depth)
        auto = dest_track.volume_automation or VolumeAutomation()
        auto.add_point(1, 0.0, dest_track.volume)
        hits = []
        for pat in source_track.patterns:
            bar = max(1, int(getattr(pat, "beats_per_bar", 4)))
            events = getattr(pat, "events", [])
            for r in range(max(1, pat.repeat)):
                measure0 = pat.start_measure + r * max(1, pat.length_measures)
                for ev in events:
                    if getattr(ev, "hit_type", "").lower() != hit_type.lower() and getattr(ev, "degree", None) is None:
                        continue
                    if hasattr(ev, "hit_type") and ev.hit_type.lower() != hit_type.lower():
                        continue
                    if not hasattr(ev, "hit_type"):
                        continue
                    abs_beats = (measure0 - 1) * bar + ev.start_beat
                    hits.append(abs_beats)
        hits.sort()
        for abs_beats in hits:
            bar = self.signature_at(1)[0]
            measure = int(abs_beats // bar) + 1
            beat = abs_beats % bar
            pre_beat = beat - 0.005
            pre_measure = measure
            if pre_beat < 0:
                pre_measure = max(1, measure - 1)
                pre_beat += bar
            auto.add_point(pre_measure, max(0.0, pre_beat), dest_track.volume)
            atk_beats = abs_beats + attack_beats
            hold_end = abs_beats + attack_beats + hold_beats
            rel_end = hold_end + release_beats
            auto.add_point(int(atk_beats // bar) + 1, atk_beats % bar, ducked)
            auto.add_point(int(hold_end // bar) + 1, hold_end % bar, ducked)
            auto.add_point(int(rel_end // bar) + 1, rel_end % bar, dest_track.volume)
        dest_track.add_volume_automation(auto)

    def render(self, filepath: str, backend_cls):
        """
        Render the project using the specified backend.
        Example: proj.render("song.rpp", ReaperRenderer)
        """
        if self.render_file is None:
            root, _ = os.path.splitext(os.path.abspath(filepath))
            self.render_file = root + ".wav"
        renderer = backend_cls(self)
        renderer.render(filepath)


# GM aliases used when an instrument has no NOTE_MAP, or as name fallbacks.
DRUM_MAP = {
    "kick": 36,
    "bass_drum": 36,
    "bd": 36,
    "snare": 38,
    "sd": 38,
    "rim": 37,
    "rimshot": 37,
    "clap": 39,
    "low_tom": 41,
    "lt": 41,
    "closed_hihat": 42,
    "closed_hat": 42,
    "hat": 42,
    "ch": 42,
    "pedal_hihat": 44,
    "mid_tom": 45,
    "mt": 45,
    "open_hihat": 46,
    "open_hat": 46,
    "oh": 46,
    "hi_tom": 48,
    "ht": 48,
    "crash": 49,
    "ride": 51,
    "tambourine": 54,
    "cowbell": 56,
    "conga_hi": 62,
    "conga_mid": 63,
    "conga_lo": 64,
    "cabasa": 69,
    "maracas": 70,
    "claves": 75,
}

_DRUM_CANONICAL = {
    "kick": ["kick", "bass drum", "bassdrum", "bd"],
    "snare": ["snare", "sd"],
    "rim": ["rim", "rimshot"],
    "clap": ["clap"],
    "low_tom": ["low tom", "lt", "tom"],
    "mid_tom": ["mid tom", "mt"],
    "hi_tom": ["hi tom", "high tom", "ht"],
    "closed_hihat": ["closed hihat", "closed hat", "closed hat", "ch", "hat"],
    "open_hihat": ["open hihat", "open hat", "oh"],
    "pedal_hihat": ["pedal hihat", "pedal hat"],
    "crash": ["crash", "cymbal"],
    "ride": ["ride"],
    "cowbell": ["cowbell"],
    "claves": ["claves"],
    "tambourine": ["tambourine"],
    "cabasa": ["cabasa"],
    "maracas": ["maracas"],
    "conga_hi": ["conga hi", "conga high"],
    "conga_mid": ["conga mid"],
    "conga_lo": ["conga lo", "conga low"],
}


def _norm_hit(name: str) -> str:
    return name.lower().replace("-", " ").replace("_", " ").strip()


def _declared(component, name, default):
    value = getattr(component, name, default)
    return default if value is None else value


def _component_entry(component) -> Dict:
    """One component's own description, in the shape the manifest carries.

    The four attributes read here are what a component publishes about
    itself, and `lib/mpvst_catalog.py` reads the same four to write
    catalog.json. Keep them in step: a component that starts describing
    something new has to be picked up in both places or the two paths drift.
    """
    patches = {}
    for index in sorted(_declared(component, "PATCHES", {})):
        entry = component.PATCHES[index]
        label, values = ((entry[0], entry[1]) if isinstance(entry, tuple)
                         else (str(entry), ()))
        patches[str(index)] = [label, list(values)]

    ranges = [list(span[:2]) if len(span) >= 2 else None
              for span in _declared(component, "_MACRO_RANGES", ())]

    note_map = [[int(note), str(label)]
                for note, label in _declared(component, "NOTE_MAP", ())]

    return {
        "patches": patches,
        "macros": list(_declared(component, "MACRO_LABELS", ())),
        "ranges": ranges,
        "note_map": note_map or None,
    }


def _describes_differently(installed: Mapping, catalogued: Mapping) -> bool:
    """Whether two descriptions of one component disagree about anything."""
    if list(installed.get("macros") or ()) != list(catalogued.get("macros") or ()):
        return True
    if (installed.get("note_map") or []) != (catalogued.get("note_map") or []):
        return True
    return (installed.get("patches") or {}) != (catalogued.get("patches") or {})


def resolve_drum_note(hit_type: str, instrument: str = None, manifest: Dict = None) -> int:
    """Map a hit name to a MIDI note, preferring the instrument NOTE_MAP."""
    raw = _norm_hit(hit_type)
    canonical = raw.replace(" ", "_")
    for canon, names in _DRUM_CANONICAL.items():
        if raw == canon.replace("_", " ") or raw in names or canonical == canon:
            canonical = canon
            raw_aliases = set(names + [canon.replace("_", " "), canon])
            break
    else:
        raw_aliases = {raw, canonical, canonical.replace("_", " ")}

    note_map = None
    if instrument and manifest:
        entry = manifest.get("instruments", {}).get(instrument, {})
        if isinstance(entry, dict):
            note_map = entry.get("note_map")
    if note_map:
        wanted = set()
        for a in raw_aliases:
            wanted.add(_norm_hit(a))
            wanted.add(_norm_hit(a).replace(" ", ""))
        for item in note_map:
            if not item:
                continue
            note, label = int(item[0]), str(item[1])
            lab = _norm_hit(label)
            compact = lab.replace(" ", "")
            if lab in wanted or compact in wanted:
                return note
            for w in list(wanted):
                if w and (w in lab or lab in w or w.replace(" ", "") in compact):
                    return note
    if canonical in DRUM_MAP:
        return DRUM_MAP[canonical]
    if hit_type.lower() in DRUM_MAP:
        return DRUM_MAP[hit_type.lower()]
    return DRUM_MAP.get("kick", 36)


class DrumEvent:
    def __init__(self, start_beat: float, hit_type: str, velocity: int = 100):
        self.start_beat = start_beat
        self.hit_type = hit_type.lower()
        self.velocity = velocity
        self.length_beats = 0.125


class DrumPattern:
    def __init__(self, start_measure: int, repeat: int = 1, beats_per_bar: int = 4):
        self.start_measure = start_measure
        self.repeat = repeat
        self.beats_per_bar = beats_per_bar
        self.events: List[DrumEvent] = []
        self.control_events: List[MidiControlEvent] = []
        self.length_measures = 1
        self.max_beat = 0.0

    def add_hit(self, start_beat: float, hit_type: str, velocity: int = 100):
        ev = DrumEvent(start_beat, hit_type, velocity)
        self.events.append(ev)
        _update_pattern_span(self, ev.start_beat, ev.length_beats)

    def add_control_event(self, event: MidiControlEvent):
        self.control_events.append(event)

    def resolve_chokes(self):
        """
        Calculates exact note lengths for open hi-hats so they are perfectly choked
        by the next closed or pedal hi-hat.
        """
        for i, ev in enumerate(self.events):
            if ev.hit_type in ("open_hihat", "open_hat", "oh"):
                next_choke_beat = float("inf")
                for future_ev in self.events:
                    if future_ev.start_beat > ev.start_beat and future_ev.hit_type in (
                        "closed_hihat", "closed_hat", "ch", "hat", "pedal_hihat",
                    ):
                        next_choke_beat = min(next_choke_beat, future_ev.start_beat)
                if next_choke_beat != float("inf"):
                    ev.length_beats = next_choke_beat - ev.start_beat
                else:
                    ev.length_beats = max(ev.length_beats, 1.0)

    def humanize(self, velocity_jitter: int = 10, timing_jitter_beats: float = 0.02):
        for ev in self.events:
            v_offset = random.randint(-velocity_jitter, velocity_jitter)
            ev.velocity = max(1, min(127, ev.velocity + v_offset))
            t_offset = random.uniform(-timing_jitter_beats, timing_jitter_beats)
            ev.start_beat = max(0.0, ev.start_beat + t_offset)

    def apply_swing(self, amount: float = 0.60, subdivision: float = 0.25):
        for ev in self.events:
            pos = ev.start_beat % (subdivision * 2)
            if pos >= subdivision - 0.01 and pos <= subdivision + 0.01:
                delay = (amount - 0.5) * (subdivision * 2)
                ev.start_beat += delay
