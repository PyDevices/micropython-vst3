import math
import os
import uuid
from typing import List, Optional

from .base import BaseRenderer
from ..macros import macros_for_effect, macros_for_instrument
from ..models import (
    AuxTrack,
    DrumPattern,
    Project,
    Track,
    resolve_drum_note,
)
from ..vst_state import encode_chunk_lines


class TimeMap:
    def __init__(self, markers):
        self.segments = []
        current_beat = 0.0
        current_time = 0.0

        for i, m in enumerate(markers):
            if i > 0:
                prev_m = markers[i - 1]
                measures_diff = m.measure - prev_m.measure
                beats_diff = measures_diff * prev_m.signature[0]

                if prev_m.transition == "linear" and prev_m.bpm != m.bpm and beats_diff:
                    bpm1 = prev_m.bpm
                    bpm2 = m.bpm
                    k = (bpm2 - bpm1) / beats_diff
                    if abs(k) < 1e-12:
                        time_diff = beats_diff * (60.0 / bpm1)
                    else:
                        time_diff = (60.0 / k) * math.log((bpm1 + k * beats_diff) / bpm1)
                else:
                    time_diff = beats_diff * (60.0 / prev_m.bpm)

                current_beat += beats_diff
                current_time += time_diff
                self.segments[-1]["next_bpm"] = m.bpm
                self.segments[-1]["total_beats"] = beats_diff

            self.segments.append({
                "measure": m.measure,
                "bpm": m.bpm,
                "signature": m.signature,
                "transition": m.transition,
                "start_beat": current_beat,
                "start_time": current_time,
                "next_bpm": None,
                "total_beats": 0,
            })

    def _segment_at_measure(self, measure: int):
        target = self.segments[0]
        for seg in self.segments:
            if measure >= seg["measure"]:
                target = seg
            else:
                break
        return target

    def _segment_at_abs_beat(self, abs_beat: float):
        target = self.segments[0]
        for i, seg in enumerate(self.segments):
            if abs_beat + 1e-9 >= seg["start_beat"]:
                target = seg
            else:
                break
        return target

    def measure_beat_to_abs_beat(self, measure: int, beat: float) -> float:
        seg = self._segment_at_measure(measure)
        return seg["start_beat"] + (measure - seg["measure"]) * seg["signature"][0] + beat

    def abs_beat_to_time(self, abs_beat: float) -> float:
        seg = self._segment_at_abs_beat(abs_beat)
        beats_into = abs_beat - seg["start_beat"]
        if seg["transition"] == "linear" and seg["next_bpm"] is not None:
            bpm1 = seg["bpm"]
            bpm2 = seg["next_bpm"]
            D = seg["total_beats"]
            if D > 0 and abs(bpm1 - bpm2) > 1e-12:
                k = (bpm2 - bpm1) / D
                local = min(max(beats_into, 0.0), D) if D else beats_into
                if local <= 0:
                    time_diff = 0.0
                else:
                    time_diff = (60.0 / k) * math.log((bpm1 + k * local) / bpm1)
                if beats_into > D:
                    time_diff += (beats_into - D) * (60.0 / bpm2)
                return seg["start_time"] + time_diff
        return seg["start_time"] + beats_into * (60.0 / seg["bpm"])

    def measure_beat_to_absolute(self, measure: int, beat: float) -> float:
        return self.abs_beat_to_time(self.measure_beat_to_abs_beat(measure, beat))

    def beats_to_seconds(self, beats: float, measure: int, start_beat: float = 0.0) -> float:
        """Convert a beat length starting at measure/start_beat into seconds, integrating tempo ramps."""
        t0 = self.measure_beat_to_absolute(measure, start_beat)
        t1 = self.abs_beat_to_time(self.measure_beat_to_abs_beat(measure, start_beat) + beats)
        return max(0.0, t1 - t0)


def _kw_repr(kwargs: dict) -> str:
    parts = []
    for k, v in kwargs.items():
        if k in ("sidechain", "duck_from"):
            continue
        parts.append(f"{k}={repr(v)}")
    return ", ".join(parts)


def _effect_call_args(preset, kwargs: dict) -> str:
    bits = []
    if preset:
        bits.append(f"preset={repr(preset)}")
    extra = _kw_repr(kwargs)
    if extra:
        bits.append(extra)
    return ", ".join(bits)


# 24-bit PCM WAV render config (little-endian 'wave' + 24 + flag)
_RENDER_CFG_24 = "ZXZhdxgAAQ=="


class ReaperRenderer(BaseRenderer):

    def _encode_vst_chunk(
        self,
        script_payload: str,
        is_instrument: bool = True,
        cid: str = None,
        display_name: str = None,
        numeric_id: int = 0,
        inner_lines: Optional[List[str]] = None,
        indent: str = "    ",
        macros: Optional[dict] = None,
    ) -> list:
        if not cid:
            kind = "instrument" if is_instrument else "effect"
            raise ValueError(
                f"Missing MPVST CID for {kind} {display_name!r}. "
                "Script Host CIDs load default_instrument.py / default_effect.py."
            )
        cid = cid.replace("{", "").replace("}", "").upper()
        numeric = int(numeric_id) if numeric_id else 0
        if not numeric and hasattr(self, "project") and getattr(self.project, "vst_numeric", None):
            numeric = int(self.project.vst_numeric.get(cid, 0))
        label = display_name or cid
        if is_instrument:
            header = f'<VST "VST3i: {label} (PyDevices)" MPVST.vst3 0 "" {numeric}{{{cid}}} ""'
        else:
            header = f'<VST "VST3: {label} (PyDevices)" MPVST.vst3 0 "" {numeric}{{{cid}}} ""'

        chunk = encode_chunk_lines(script_payload, numeric, is_instrument, macros or {})
        pad = indent + "  "
        lines = [f"{indent}{header}"]
        lines.extend([f"{pad}{line}" for line in chunk])
        if inner_lines:
            lines.extend(inner_lines)
        lines.append(f"{indent}>")
        return lines

    def _parmenv_lines(self, automation, time_map: TimeMap, indent: str) -> list:
        lines = []
        if not automation or not time_map:
            return lines
        for auto in automation:
            lines.append(f"{indent}<PARMENV {auto.macro_index} 0.5 0")
            lines.append(f"{indent}  ACT 1 -1")
            lines.append(f"{indent}  VIS 1 1 1")
            lines.append(f"{indent}  LANEHEIGHT 0 0")
            lines.append(f"{indent}  ARM 1")
            lines.append(f"{indent}  DEFSHAPE 0 -1 -1")
            sorted_points = sorted(auto.points, key=lambda p: (p.measure, p.beat))
            for pt in sorted_points:
                t = time_map.measure_beat_to_absolute(pt.measure, pt.beat)
                lines.append(f"{indent}  PT {t:.5f} {pt.value:.5f} 0")
            lines.append(f"{indent}>")
        return lines

    def _instrument_payload(self, tr: Track, proj: Project) -> str:
        patch_idx = proj.resolve_instrument_patch(tr.instrument, tr.patch)
        lines = [
            f"# mpvst-module: audioinstruments.{tr.instrument}",
            "import mpvst_instrument_adapter",
            f"inst = mpvst_instrument_adapter.run('audioinstruments.{tr.instrument}')",
        ]
        if patch_idx:
            lines.append(f"inst.program_change({patch_idx})")
        return "\n".join(lines) + "\n"

    def _effect_payload(self, effect: str, preset, kwargs: dict, sidechain: bool = False) -> str:
        kwargs = dict(kwargs or {})
        sidechain = sidechain or bool(kwargs.pop("sidechain", False))
        duck = bool(kwargs.pop("duck", False))
        args = _effect_call_args(preset, kwargs)
        # Compressor has no key=. NoiseGate(duck=True) and Expander(key=) are the
        # processors that can actually hear an external key. When the track is
        # 4-channel (kick AUXRECV onto dest chan 2), pass the host input as key
        # so the detector sees channels 3/4 if the host presents them.
        if sidechain and effect in ("NoiseGate", "Expander", "noisegate", "expander"):
            class_name = "NoiseGate" if effect.lower() == "noisegate" else (
                "Expander" if effect.lower() == "expander" else effect
            )
            extra = args
            duck_arg = ""
            if class_name == "NoiseGate" and duck:
                duck_arg = "duck=True, "
            if extra:
                extra = duck_arg + extra
            else:
                extra = duck_arg.rstrip(", ")
            call = f"audioeffects.create({repr(class_name)}, host, rate, key=host, {extra})" if extra else (
                f"audioeffects.create({repr(class_name)}, host, rate, key=host)"
            )
            return (
                f"# mpvst-module: audioeffects.{class_name}\n"
                "import vstaudio\n"
                "import audioeffects\n"
                "host = vstaudio.input()\n"
                "rate = vstaudio.sample_rate()\n"
                f"fx = {call}\n"
                "vstaudio.output(fx.output)\n"
            )
        if args:
            body = f"fx = mpvst_effect_adapter.run({repr(effect)}, {args})"
        else:
            body = f"fx = mpvst_effect_adapter.run({repr(effect)})"
        return (
            f"# mpvst-module: audioeffects.{effect}\n"
            "import mpvst_effect_adapter\n"
            f"{body}\n"
        )

    def _fxchain(
        self,
        vst_blocks: List[list],
        indent: str = "    ",
    ) -> list:
        lines = [f"{indent}<FXCHAIN"]
        lines.append(f"{indent}  SHOW 0")
        lines.append(f"{indent}  LASTSEL 0")
        lines.append(f"{indent}  DOCKED 0")
        for block in vst_blocks:
            lines.append(f"{indent}  BYPASS 0 0 0")
            lines.extend(block)
        lines.append(f"{indent}>")
        return lines

    def _vst_for_effect(self, proj: Project, effect: str, preset, kwargs, sidechain=False, indent="      "):
        payload = self._effect_payload(effect, preset, kwargs, sidechain=sidechain)
        cid, display_name, numeric = proj.resolve_vst(effect)
        macros = macros_for_effect(effect, preset, kwargs, proj.patch_manifest)
        return self._encode_vst_chunk(
            payload, is_instrument=False, cid=cid, display_name=display_name,
            numeric_id=numeric, indent=indent, macros=macros,
        )

    def _generate_midi_item(self, pattern, track, time_map: TimeMap, theory, proj: Project, patch_idx: int = 0):
        lines = []
        start_sec = time_map.measure_beat_to_absolute(pattern.start_measure, 0.0)
        beats_per_bar = time_map._segment_at_measure(pattern.start_measure)["signature"][0]
        bar = max(1, int(getattr(pattern, "beats_per_bar", beats_per_bar) or beats_per_bar))
        span_beats = max(bar * max(1, pattern.length_measures), getattr(pattern, "max_beat", 0.0), bar)
        # Snap up to a whole number of bars so LOOP does not cut the last note.
        span_beats = max(bar, math.ceil((span_beats - 1e-9) / bar) * bar)
        one_iter_sec = time_map.beats_to_seconds(span_beats, pattern.start_measure, 0.0)
        length_sec = one_iter_sec * max(1, pattern.repeat)

        item_guid = "{" + str(uuid.uuid4()).upper() + "}"

        lines.append("    <ITEM")
        lines.append(f"      POSITION {start_sec:.8f}")
        lines.append("      SNAPOFFS 0")
        lines.append(f"      LENGTH {length_sec:.8f}")
        lines.append("      LOOP 1")
        lines.append("      ALLTAKES 0")
        lines.append("      FADEIN 1 0 0 1 0 0 0")
        lines.append("      FADEOUT 1 0 0 1 0 0 0")
        lines.append("      MUTE 0 0")
        lines.append("      SEL 0")
        lines.append(f"      NAME \"{track.name}\"")
        lines.append("      VOLPAN 1 0 1 -1")
        lines.append("      SOFFS 0 0")
        lines.append("      PLAYRATE 1 1 0 -1 0 0.0025")
        lines.append("      CHANMODE 0")
        lines.append(f"      GUID {item_guid}")
        lines.append("      <SOURCE MIDI")
        lines.append("        HASDATA 1 960 QN")
        lines.append("        CCINTERP 32")

        current_tick = 0
        wrote_pc = False
        for r in range(max(1, pattern.repeat)):
            events = sorted(pattern.events, key=lambda e: e.start_beat)
            midi_actions = []
            if isinstance(pattern, DrumPattern):
                pattern.resolve_chokes()
                for ev in events:
                    note_num = resolve_drum_note(ev.hit_type, track.instrument, proj.patch_manifest)
                    start_tick = current_tick + int(ev.start_beat * 960)
                    end_tick = start_tick + max(1, int(ev.length_beats * 960))
                    midi_actions.append({"tick": start_tick, "type": "on", "note": note_num, "vel": ev.velocity})
                    midi_actions.append({"tick": end_tick, "type": "off", "note": note_num, "vel": 0})
            else:
                for ev in events:
                    note_num = theory.get_midi_note(ev.degree, ev.octave, ev.accidental)
                    start_tick = current_tick + int(ev.start_beat * 960)
                    end_tick = start_tick + max(1, int(ev.length_beats * 960))
                    midi_actions.append({"tick": start_tick, "type": "on", "note": note_num, "vel": ev.velocity})
                    midi_actions.append({"tick": end_tick, "type": "off", "note": note_num, "vel": 0})

            for cev in pattern.control_events:
                tick = current_tick + int(cev.start_beat * 960)
                if cev.cc_num is not None:
                    midi_actions.append({"tick": tick, "type": "cc", "cc": cev.cc_num, "val": cev.value})
                elif cev.pitch_bend is not None:
                    midi_actions.append({"tick": tick, "type": "pb", "val": cev.pitch_bend})

            if patch_idx and not wrote_pc:
                midi_actions.append({"tick": current_tick, "type": "pc", "val": patch_idx})
                wrote_pc = True

            midi_actions.sort(key=lambda x: (x["tick"], 0 if x["type"] in ("off", "pc") else 1))

            action_current_tick = current_tick
            for action in midi_actions:
                delta = max(0, action["tick"] - action_current_tick)
                if action["type"] == "on":
                    lines.append(f"        E {delta} 90 {action['note']:02x} {action['vel']:02x}")
                elif action["type"] == "off":
                    lines.append(f"        E {delta} 80 {action['note']:02x} 00")
                elif action["type"] == "cc":
                    lines.append(f"        E {delta} b0 {action['cc']:02x} {action['val']:02x}")
                elif action["type"] == "pc":
                    lines.append(f"        E {delta} c0 {action['val']:02x}")
                elif action["type"] == "pb":
                    val = action["val"]
                    lsb = val & 0x7F
                    msb = (val >> 7) & 0x7F
                    lines.append(f"        E {delta} e0 {lsb:02x} {msb:02x}")
                action_current_tick = action["tick"]

            current_tick += int(span_beats * 960)

        lines.append("      >")
        lines.append("    >")
        return lines

    def _generate_track_automation(self, track, time_map):
        out = []
        if getattr(track, "volume_automation", None):
            out.append("    <VOLENV2")
            out.append("      ACT 1 -1")
            out.append("      VIS 1 1 1")
            out.append("      LANEHEIGHT 0 0")
            out.append("      ARM 1")
            out.append("      DEFSHAPE 0 -1 -1")
            for pt in track.volume_automation.points:
                t = time_map.measure_beat_to_absolute(pt.measure, pt.beat)
                out.append(f"      PT {t:.5f} {pt.value:.5f} 0")
            out.append("    >")

        if getattr(track, "pan_automation", None):
            out.append("    <PANENV2")
            out.append("      ACT 1 -1")
            out.append("      VIS 1 1 1")
            out.append("      LANEHEIGHT 0 0")
            out.append("      ARM 1")
            out.append("      DEFSHAPE 0 -1 -1")
            for pt in track.pan_automation.points:
                t = time_map.measure_beat_to_absolute(pt.measure, pt.beat)
                out.append(f"      PT {t:.5f} {pt.value:.5f} 0")
            out.append("    >")
        return out

    def _ordered_nodes(self, proj: Project):
        """Aux tracks first, then instrument tracks. Indices are 0-based RPP order."""
        nodes = []
        for aux in proj.aux_tracks:
            nodes.append(("aux", aux))
        for tr in proj.tracks:
            nodes.append(("track", tr))
        return nodes

    def render(self, filepath: str):
        return self.render_project(self.project, filepath)

    def render_project(self, proj: Project, filepath: str):
        proj = self.project
        time_map = TimeMap(proj.tempo_markers)
        nodes = self._ordered_nodes(proj)
        guid_to_index = {obj.guid: i for i, (_, obj) in enumerate(nodes)}

        receives = {obj.guid: [] for _, obj in nodes}
        sidechain_targets = set()
        for _, src_obj in nodes:
            for send in getattr(src_obj, "sends", []) or []:
                dest = send["target"]
                src_idx = guid_to_index.get(src_obj.guid)
                if src_idx is None:
                    continue
                receives.setdefault(dest, []).append({
                    "src_idx": src_idx,
                    "level": send.get("level", 1.0),
                    "src_chan": send.get("src_chan", 0),
                    "dst_chan": send.get("dst_chan", 0),
                    "mode": send.get("mode", 0),
                })
                if send.get("dst_chan", 0) > 0:
                    sidechain_targets.add(dest)

        start_bpm = proj.tempo_markers[0].bpm if proj.tempo_markers else 120
        start_sig = proj.tempo_markers[0].signature if proj.tempo_markers else (4, 4)
        wav_path = proj.render_file or (os.path.splitext(os.path.abspath(filepath))[0] + ".wav")
        wav_path = wav_path.replace("\\", "/")
        tail_ms = int(getattr(proj, "render_tail_ms", 1000) or 1000)
        sr = int(getattr(proj, "sample_rate", 48000) or 48000)

        out = []
        out.append('<REAPER_PROJECT 0.1 "7.79/win64" 0')
        out.append("  RIPPLE 0 0")
        out.append("  GROUPOVERRIDE 0 0 0 0")
        out.append("  AUTOXFADE 129")
        out.append(f"  TEMPO {start_bpm:.6f} {start_sig[0]} {start_sig[1]} 0")
        out.append(f"  SAMPLERATE {sr} 1 0")
        out.append("  LOCK 1")
        out.append(f"  RENDER_FILE \"{wav_path}\"")
        out.append("  RENDER_PATTERN \"\"")
        out.append(f"  RENDER_FMT 0 2 {sr}")
        out.append("  RENDER_1X 0")
        out.append(f"  RENDER_RANGE 1 0 0 0 {tail_ms}")
        out.append("  RENDER_RESAMPLE 3 0 1")
        out.append("  RENDER_ADDTOPROJ 0")
        out.append("  RENDER_STEMS 0")
        out.append("  RENDER_DITHER 0")
        out.append("  RENDER_TRIM 0.000001 0.000001 0 0")
        out.append("  <RENDER_CFG")
        out.append(f"    {_RENDER_CFG_24}")
        out.append("  >")
        out.append("  MASTER_NCH 2 2")
        out.append("  MASTER_VOLUME 1 0 -1 -1 1")
        out.append("  MASTER_FX 1")
        out.append("  MASTERHWOUT 0 0 1 0 0 0 0 -1")
        out.append("  <NOTES")
        out.append(f"    |{proj.name} — generated by MPVST Composer")
        out.append("  >")

        out.append("  <TEMPOENVEX")
        out.append("    ACT 1 -1")
        out.append("    VIS 1 0 1")
        out.append("    LANEHEIGHT 0 0")
        out.append("    ARM 0")
        out.append("    DEFSHAPE 1 -1 -1")
        for m in proj.tempo_markers:
            t = time_map.measure_beat_to_absolute(m.measure, 0.0)
            sig_encoded = m.signature[0] | (m.signature[1] << 16)
            shape = 1 if m.transition == "linear" else 0
            out.append(f"    PT {t:.8f} {m.bpm:.6f} {sig_encoded} 0 0 {shape}")
        out.append("  >")

        if proj.master_inserts:
            out.append("  <MASTERFXLIST")
            out.append("    SHOW 0")
            out.append("    LASTSEL 0")
            out.append("    DOCKED 0")
            for ins in proj.master_inserts:
                out.append("    BYPASS 0 0 0")
                payload = self._effect_payload(ins["effect"], ins["preset"], ins["kwargs"])
                cid, display_name, numeric = proj.resolve_vst(ins["effect"])
                macros = macros_for_effect(
                    ins["effect"], ins["preset"], ins["kwargs"], proj.patch_manifest,
                )
                out.extend(self._encode_vst_chunk(
                    payload, is_instrument=False, cid=cid, display_name=display_name,
                    numeric_id=numeric, indent="    ", macros=macros,
                ))
            out.append("  >")

        for kind, obj in nodes:
            nchan = 4 if obj.guid in sidechain_targets else 2
            vol = getattr(obj, "volume", 1.0)
            pan = getattr(obj, "pan", 0.0)
            out.append(f"  <TRACK {obj.guid}")
            out.append(f"    NAME \"{obj.name}\"")
            out.append(f"    VOLPAN {vol} {pan} 1 -1 1")
            out.append("    MUTESOLO 0 0 0")
            out.append("    ISBUS 0 0")
            out.append(f"    NCHAN {nchan}")
            out.append("    FX 1")
            out.append("    PERF 0")
            out.append("    MIDIOUT -1 -1")
            mainsend = 1 if getattr(obj, "mainsend", 1) else 0
            out.append(f"    MAINSEND {mainsend} 0")
            out.append(f"    TRACKID {obj.guid}")

            for recv in receives.get(obj.guid, []):
                # AUXRECV lives on the DESTINATION. First field = source track index.
                # destchan/srcchan: 0 = 1/2, 2 = 3/4.
                out.append(
                    f"    AUXRECV {recv['src_idx']} {recv['mode']} {recv['level']:.8f} 0 0 0 0 "
                    f"{recv['dst_chan']} {recv['src_chan']} -1:0 -1"
                )

            if kind == "aux":
                vst = self._vst_for_effect(proj, obj.effect, obj.preset, obj.kwargs, indent="      ")
                out.extend(self._fxchain([vst]))
                out.extend(self._generate_track_automation(obj, time_map))
            else:
                tr: Track = obj
                patch_idx = proj.resolve_instrument_patch(tr.instrument, tr.patch)
                inst_payload = self._instrument_payload(tr, proj)
                cid, display_name, numeric = proj.resolve_vst(tr.instrument)
                parmenv = self._parmenv_lines(tr.automation, time_map, indent="        ")
                inst_macros = macros_for_instrument(
                    tr.instrument, tr.patch, proj.patch_manifest,
                )
                inst_vst = self._encode_vst_chunk(
                    inst_payload,
                    is_instrument=True,
                    cid=cid,
                    display_name=display_name,
                    numeric_id=numeric,
                    inner_lines=parmenv,
                    indent="      ",
                    macros=inst_macros,
                )
                vst_blocks = [inst_vst]
                wants_key = tr.guid in sidechain_targets
                for ins in tr.inserts:
                    sc = bool(ins["kwargs"].get("sidechain")) or (
                        wants_key and ins["effect"] in ("NoiseGate", "Expander", "noisegate", "expander")
                    )
                    vst_blocks.append(
                        self._vst_for_effect(
                            proj, ins["effect"], ins["preset"], ins["kwargs"],
                            sidechain=sc, indent="      ",
                        )
                    )
                out.extend(self._fxchain(vst_blocks))
                for pat in tr.patterns:
                    out.extend(self._generate_midi_item(pat, tr, time_map, proj.theory, proj, patch_idx=patch_idx))
                out.extend(self._generate_track_automation(tr, time_map))

            out.append("  >")

        out.append(">")

        os.makedirs(os.path.dirname(os.path.abspath(filepath)) or ".", exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")
