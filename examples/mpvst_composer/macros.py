"""Map constructor kwargs / named patches onto MPVST's 16 normalized macros.

The plug-in restores the float array from project state and replays it after
the script runs. Constructor arguments are not round-tripped; they only
survive if they are also in this array (or arrive later as PARMENV).
"""

from __future__ import annotations

import ast
import math
import os
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

_SKIP_KW = {
    "sidechain", "duck", "key", "character", "stereo", "impulse",
    "impulse_channels", "seed", "patch", "preset",
}

_VST_FX_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~/AppData/Local")),
    "Programs", "Common", "VST3", "MPVST.vst3",
    "Contents", "x86_64-win", "audioeffects",
)

_TABLES: Optional[Dict[str, dict]] = None


def _norm_key(name: str) -> str:
    s = re.sub(r"(_db|_ms|_hz|_pct)$", "", str(name).lower())
    return re.sub(r"[^a-z0-9]", "", s)


def macro_position(span: Sequence, value: float) -> float:
    """Inverse of audioeffects._component.macro_value, clamped to 0..1."""
    low, high = float(span[0]), float(span[1])
    value = float(value)
    if len(span) > 2:
        if value <= 0.0 or low <= 0.0 or high <= 0.0 or high == low:
            if high == low:
                return 0.0
            return min(1.0, max(0.0, (value - low) / (high - low)))
        position = math.log(value / low) / math.log(high / low)
    else:
        if high == low:
            return 0.0
        position = (value - low) / (high - low)
    return min(1.0, max(0.0, position))


def _eval_node(node, ns: dict):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in ns:
            return ns[node.id]
        raise ValueError(node.id)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval_node(node.operand, ns)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd):
        return _eval_node(node.operand, ns)
    if isinstance(node, ast.Tuple):
        return tuple(_eval_node(elt, ns) for elt in node.elts)
    if isinstance(node, ast.List):
        return [_eval_node(elt, ns) for elt in node.elts]
    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left, ns)
        right = _eval_node(node.right, ns)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.FloorDiv):
            return left // right
        if isinstance(node.op, ast.Pow):
            return left ** right
        raise ValueError(type(node.op))
    if isinstance(node, ast.Attribute):
        obj = _eval_node(node.value, ns)
        return getattr(obj, node.attr)
    if isinstance(node, ast.Call):
        func = _eval_node(node.func, ns)
        args = [_eval_node(a, ns) for a in node.args]
        return func(*args)
    raise ValueError(type(node).__name__)


def _scan_effect_tables(fx_dir: str) -> Dict[str, dict]:
    tables: Dict[str, dict] = {}
    if not os.path.isdir(fx_dir):
        return tables
    for fname in os.listdir(fx_dir):
        if not fname.endswith(".py"):
            continue
        path = os.path.join(fx_dir, fname)
        try:
            src = open(path, encoding="utf-8").read()
            tree = ast.parse(src)
        except (OSError, SyntaxError):
            continue
        module_ns: dict = {"math": math}
        for stmt in tree.body:
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
                try:
                    module_ns[stmt.targets[0].id] = _eval_node(stmt.value, module_ns)
                except Exception:
                    pass
            if not isinstance(stmt, ast.ClassDef):
                continue
            class_ns = dict(module_ns)
            name = None
            ranges = None
            labels = None
            for body in stmt.body:
                if not isinstance(body, ast.Assign):
                    continue
                for target in body.targets:
                    if not isinstance(target, ast.Name):
                        continue
                    try:
                        val = _eval_node(body.value, class_ns)
                    except Exception:
                        continue
                    class_ns[target.id] = val
                    if target.id == "NAME":
                        name = val
                    elif target.id == "_MACRO_RANGES":
                        ranges = val
                    elif target.id == "MACRO_LABELS":
                        labels = val
            if isinstance(name, str) and name:
                tables[name] = {
                    "ranges": tuple(ranges) if ranges else (),
                    "labels": tuple(labels) if labels else (),
                }
    return tables


def effect_tables() -> Dict[str, dict]:
    global _TABLES
    if _TABLES is None:
        _TABLES = _scan_effect_tables(_VST_FX_DIR)
    return _TABLES


def _midi_macros(midi: Sequence) -> Dict[int, float]:
    out = {}
    for i, v in enumerate(midi or ()):
        try:
            out[i] = max(0.0, min(1.0, float(v) / 127.0))
        except (TypeError, ValueError):
            continue
    return out


def _lookup_entry(manifest: Mapping, kind: str, name: str) -> dict:
    bucket = (manifest or {}).get(kind) or {}
    if name in bucket and isinstance(bucket[name], dict):
        return bucket[name]
    lower = str(name).lower()
    for key, val in bucket.items():
        if str(key).lower() == lower and isinstance(val, dict):
            return val
    return {}


def patch_midi(entry: Mapping, preset) -> Tuple[int, List]:
    patches = entry.get("patches") or {}
    if not patches:
        return 0, []

    def _vals(data) -> List:
        if isinstance(data, list) and len(data) > 1 and isinstance(data[1], (list, tuple)):
            return list(data[1])
        return []

    if preset is None or preset == "":
        data = patches.get("0") or patches.get(0)
        if data:
            return 0, _vals(data)
        return 0, []
    if isinstance(preset, bool):
        return 0, []
    if isinstance(preset, int) or (isinstance(preset, str) and preset.isdigit()):
        idx = str(int(preset))
        data = patches.get(idx)
        if data:
            return int(idx), _vals(data)
        return int(idx), []
    needle = str(preset).lower()
    for idx_str, data in patches.items():
        pname = data[0] if isinstance(data, list) and data else data
        if str(pname).lower() == needle or needle in str(pname).lower():
            try:
                return int(idx_str), _vals(data)
            except (TypeError, ValueError):
                return 0, _vals(data)
    return 0, []


def _labels_and_ranges(effect: str, entry: Mapping) -> Tuple[List[str], Tuple]:
    labels = list(entry.get("macros") or [])
    tables = effect_tables().get(effect) or {}
    if not labels:
        labels = list(tables.get("labels") or ())
    ranges = tables.get("ranges") or ()
    return labels, tuple(ranges)


def _kw_to_position(label: str, span, value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    key = _norm_key(label)
    if key == "slope":
        try:
            n = float(value)
        except (TypeError, ValueError):
            return None
        if n in (12.0, 12):
            return 0.0
        if n in (24.0, 24):
            return 1.0
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if span:
        return macro_position(span, n)
    if 0.0 <= n <= 1.0:
        return n
    if 0.0 <= n <= 127.0:
        return n / 127.0
    return None


def macros_for_effect(
    effect: str,
    preset,
    kwargs: Optional[Mapping[str, Any]],
    manifest: Mapping,
) -> Dict[int, float]:
    kwargs = dict(kwargs or {})
    entry = _lookup_entry(manifest, "effects", effect)
    patch_key = kwargs.get("patch", preset)
    _idx, midi = patch_midi(entry, patch_key)
    macros = _midi_macros(midi)
    labels, ranges = _labels_and_ranges(effect, entry)
    by_key = {_norm_key(lab): i for i, lab in enumerate(labels)}
    for key, value in kwargs.items():
        if key in _SKIP_KW:
            continue
        idx = by_key.get(_norm_key(key))
        if idx is None:
            continue
        span = ranges[idx] if idx < len(ranges) else None
        pos = _kw_to_position(labels[idx] if idx < len(labels) else key, span, value)
        if pos is not None:
            macros[idx] = pos
    return macros


def macros_for_instrument(
    instrument: str,
    patch_name: str,
    manifest: Mapping,
) -> Dict[int, float]:
    entry = _lookup_entry(manifest, "instruments", instrument)
    _idx, midi = patch_midi(entry, patch_name)
    return _midi_macros(midi)
