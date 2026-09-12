"""MPVST VST3 component state and REAPER chunk wrapping.

Layout is the one in docs/writing-scripts.md, copied from
reaper/matrix/build_effect_project.py. A rejected chunk is silent: the host
discards it and the instance falls back to the catalog two-liner
(`run("Limiter")`, no arguments).
"""

from __future__ import annotations

import base64
import struct
from typing import Dict, List, Mapping, Optional, Tuple

# Byte-exact tails captured from projects REAPER itself saved for Script Host.
# The first word is the per-class Reaper numeric id, not the Script Host id.
_INSTRUMENT_TAIL = [0xFEED5EEE, 0x0, 0x2, 0x1, 0x0, 0x2, 0x0, None, 0x1, 0xFFFF]
_EFFECT_TAIL = [
    0xFEED5EEE,
    0x2, 0x1, 0x0, 0x2, 0x0,
    0x2, 0x1, 0x0, 0x2, 0x0,
    None, 0x1, 0xFFFF,
]


def component_state(script: bytes, macros: Mapping[int, float]) -> bytes:
    """Little-endian v2 state: version, bypass, 16 macros, pipeline, script."""
    comp = struct.pack("<ii", 2, 0)
    for index in range(16):
        comp += struct.pack("<f", float(macros.get(index, 0.5)))
    comp += struct.pack("<ii", 4, len(script))
    return comp + script


def chunk_lines(header_words: List, script: bytes, macros: Mapping[int, float]) -> List[str]:
    """REAPER wrapper: header line, component data, 6-zero footer."""
    comp = component_state(script, macros)
    data = struct.pack("<II", len(comp), 1) + comp + b"\0" * 8
    words = [len(data) if w is None else int(w) for w in header_words]
    header = struct.pack("<%dI" % len(words), *words)
    lines = [base64.b64encode(header).decode("ascii")]
    encoded = base64.b64encode(data).decode("ascii")
    lines += [encoded[i:i + 128] for i in range(0, len(encoded), 128)]
    lines.append(base64.b64encode(b"\0" * 6).decode("ascii"))
    return lines


def header_words(numeric_id: int, is_instrument: bool) -> List:
    first = int(numeric_id) & 0xFFFFFFFF
    tail = _INSTRUMENT_TAIL if is_instrument else _EFFECT_TAIL
    return [first] + list(tail)


def encode_chunk_lines(
    script_payload: str,
    numeric_id: int,
    is_instrument: bool,
    macros: Optional[Mapping[int, float]] = None,
) -> List[str]:
    script = script_payload.encode("utf-8")
    return chunk_lines(header_words(numeric_id, is_instrument), script, macros or {})


def decode_chunk_lines(lines: List[str]) -> dict:
    """Decode a REAPER-wrapped MPVST chunk (for tests / debugging)."""
    if len(lines) < 3:
        raise ValueError("chunk too short")
    header = base64.b64decode(lines[0])
    data = base64.b64decode("".join(lines[1:-1]))
    header_words_out = list(struct.unpack("<%dI" % (len(header) // 4), header))
    if len(data) < 8:
        raise ValueError("missing data header")
    comp_len, flag = struct.unpack_from("<II", data, 0)
    comp = data[8:8 + comp_len]
    if len(comp) < 8 + 64 + 8:
        # Legacy length-prefixed script: first uint32 is script length, not version.
        version = struct.unpack_from("<I", comp, 0)[0] if comp else None
        return {
            "legacy": True,
            "version": version,
            "header_words": header_words_out,
            "flag": flag,
            "script": b"",
            "macros": (),
        }
    version, bypass = struct.unpack_from("<ii", comp, 0)
    macros = struct.unpack_from("<16f", comp, 8)
    blocks, script_len = struct.unpack_from("<ii", comp, 8 + 64)
    script = comp[8 + 64 + 8:8 + 64 + 8 + script_len]
    return {
        "legacy": False,
        "version": version,
        "bypass": bypass,
        "macros": macros,
        "pipeline_blocks": blocks,
        "script": script,
        "header_words": header_words_out,
        "flag": flag,
        "comp_len": comp_len,
    }


def extract_vst_chunks(rpp_text: str) -> List[Tuple[str, List[str]]]:
    """Return (vst_header_line, base64_lines) for each <VST ...> block."""
    chunks = []
    lines = rpp_text.splitlines()
    i = 0
    while i < len(lines):
        stripped = lines[i].lstrip()
        if stripped.startswith("<VST "):
            header = stripped
            b64 = []
            i += 1
            while i < len(lines):
                s = lines[i].strip()
                if s == ">" or s.startswith("<"):
                    break
                if s:
                    b64.append(s)
                i += 1
            chunks.append((header, b64))
        i += 1
    return chunks
