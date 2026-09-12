# MPVST: AI & Automation Integration Guide

Welcome to the programmatic integration guide for **MPVST**. If you are an AI agent, automation engineer, or generative music developer looking to programmatically generate Reaper (`.RPP`) projects complete with functioning synthesizers and effects, you are in the right place.

---

## 🤖 The "Code as State" Philosophy

Generating DAW project files (like Reaper's `.RPP`) programmatically is notoriously difficult because standard VST plugins serialize their state (presets, parameters, logic) as proprietary, opaque binary blobs. To change a standard VST's preset, you would have to reverse-engineer undocumented C++ structs.

**MPVST completely solves this by using "Code as State".**
MPVST embeds a MicroPython interpreter directly into the VST3 plugin. When the plugin saves its state to the `.RPP` file, it saves the literal Python script that defines its DSP graph. This means you do not have to reverse-engineer anything. You can generate entirely new synthesizer patches, build custom effect racks, and define exact macro parameters on the fly by simply writing a short Python script, encoding it in the VST3 state chunk, and injecting it into the `.RPP` XML-like structure.

This architecture makes MPVST the ultimate target for AI-driven music generation.

---

## 🛠️ Everything You Need Is in `catalog.json`

Before you generate a project, you need to know what exists: which instruments and effects are installed, what their class IDs are, what macros they have and in what units, and what patches they offer. All of it is one file inside the installed bundle:

```
%LOCALAPPDATA%\Programs\Common\VST3\MPVST.vst3\Contents\Resources\catalog.json
```

```python
import json
catalog = json.load(open(bundle + "/Contents/Resources/catalog.json"))
by_name = {c["name"]: c for c in catalog["classes"]}

limiter = by_name["Limiter"]
limiter["cid"]           # 0700D6A78BFA9A03BA678484750C4B21
limiter["macro_labels"]  # ['Ceiling', 'Gain', 'Lookahead', ...]
limiter["macro_ranges"]  # [[-24.0, 0.0], [0.0, 24.0], ...]
limiter["patches"]       # [{'index': 2, 'name': 'Loud', 'macros': [125, 64, ...]}, ...]
by_name["tr808"]["note_map"]   # [[36, 'Bass Drum'], [38, 'Snare'], ...]
```

Do **not** parse the `.py` files in the VST directory, and do not hardcode an ID out of a document - including this one. The catalog is written by the installer and is the only copy that cannot drift.

Two things it does not carry. Reaper's own 32-bit numeric id for each class lives in `reaper-vstplugins64.ini`, next to the CID. And `moduleinfo.json` beside the catalog is Steinberg's file, for hosts - same IDs, no patches, no ranges.

Put **that class's** numeric id and CID on the `<VST>` line (for example Limiter `1086681545{0700D6A78BFA9A03BA678484750C4B21}`). The display name is only a label; the TUID in braces selects the class. Use one of the two generic **Script Host** IDs only when the script itself is the point - use it for an instrument and every track loads the same empty slot, which by design makes no sound.

---

## 📜 The Adapter Contract (CRITICAL)

When generating the Python payload for an MPVST instance, **do not** instantiate the effect or instrument classes directly (e.g., `effect = audioeffects.Reverb()`). Doing so will cause the DSP graph to break and fail silently (outputting `-inf` silence) when macros change, because you bypass the framework's rebinding logic.

Instead, you **must** use the built-in adapter modules.

### For Instruments:
```python
# mpvst-module: audioinstruments.minimoog
import mpvst_instrument_adapter
inst = mpvst_instrument_adapter.run('audioinstruments.minimoog')
inst.program_change(1)
```

`run()` takes only the module name. Select a patch with `program_change(N)` (and/or a MIDI Program Change on the item). Pack that patch's MIDI 0–127 values from the catalog into the chunk's 16-float macro array as `value / 127.0`.

### For Effects:
```python
# mpvst-module: audioeffects.Limiter
import mpvst_effect_adapter
fx = mpvst_effect_adapter.run('Limiter')
```

**Put knob values in the chunk's macros array, not only in `run()` kwargs.** The sixteen normalized floats are what the plug-in restores and replays. `run()` kwargs still belong in the script for constructor-only options that are not macros (Reverb `preset=`, Saturation `character=`).

Limiter ranges: Ceiling (−24…0 dB), Gain (0…24 dB), Lookahead (0…10 ms), Release (5…2000 ms, log), True Peak (0/1), Knee (0…12 dB). Gain 8 dB → macro 1 = `8 / 24 = 0.3333`. Ceiling −1 dB → macro 0 = `(-1 - (-24)) / 24 = 0.9583`.

Start declared macros from patch 0 (or a named preset) as MIDI/127, then overlay kwargs converted through each `macro_ranges` span. Unused slots among the 16 stay `0.5`.

---

## 🧬 Injecting the Payload into Reaper (`.RPP`)

The script and its macros travel in the plug-in's **v2 component state**. Copy this layout from `reaper/matrix/build_effect_project.py`, or from `examples/reaper-composer/mpvst_composer/vst_state.py`, which does the same job in the composer.

Little-endian component state:

| Field | Type | Notes |
|---|---|---|
| version | `int32` | `2` |
| bypass | `int32` | 0 or 1 |
| macros | `float32` × 16 | normalized 0.0–1.0 |
| pipeline blocks | `int32` | `4` |
| script length | `int32` | bytes, not characters |
| script | bytes | UTF-8, no terminator |

REAPER wraps that in a header of `uint32` words (first word = the class's Reaper numeric id; the `None` slot is the data size), then `uint32 length`, `uint32 1`, the component, and eight zero bytes. Base64 the header as the first line, the data in 128-character lines, and a footer of six zero bytes.

```python
import base64
import struct

INSTRUMENT_TAIL = [0xFEED5EEE, 0x0, 0x2, 0x1, 0x0, 0x2, 0x0, None, 0x1, 0xFFFF]
EFFECT_TAIL = [
    0xFEED5EEE,
    0x2, 0x1, 0x0, 0x2, 0x0,
    0x2, 0x1, 0x0, 0x2, 0x0,
    None, 0x1, 0xFFFF,
]

def component_state(script: bytes, macros: dict) -> bytes:
    comp = struct.pack("<ii", 2, 0)
    for index in range(16):
        comp += struct.pack("<f", float(macros.get(index, 0.5)))
    comp += struct.pack("<ii", 4, len(script))
    return comp + script

def chunk_lines(numeric_id: int, script_payload: str, macros: dict, is_instrument: bool):
    script = script_payload.encode("utf-8")
    tail = INSTRUMENT_TAIL if is_instrument else EFFECT_TAIL
    header_words = [int(numeric_id) & 0xFFFFFFFF] + list(tail)
    comp = component_state(script, macros)
    data = struct.pack("<II", len(comp), 1) + comp + b"\0" * 8
    words = [len(data) if w is None else int(w) for w in header_words]
    header = struct.pack("<%dI" % len(words), *words)
    lines = [base64.b64encode(header).decode("ascii")]
    encoded = base64.b64encode(data).decode("ascii")
    lines += [encoded[i:i + 128] for i in range(0, len(encoded), 128)]
    lines.append(base64.b64encode(b"\0" * 6).decode("ascii"))
    return lines

def fx_block(script_payload: str, numeric_id: int, cid: str, display_name: str,
             is_instrument: bool = False, macros: dict = None):
    cid = cid.replace("{", "").replace("}", "").upper()
    if is_instrument:
        vst = f'<VST "VST3i: {display_name} (PyDevices)" MPVST.vst3 0 "" {numeric_id}{{{cid}}} ""'
    else:
        vst = f'<VST "VST3: {display_name} (PyDevices)" MPVST.vst3 0 "" {numeric_id}{{{cid}}} ""'
    lines = [f"      {vst}"]
    for line in chunk_lines(numeric_id, script_payload, macros or {}, is_instrument):
        lines.append(f"        {line}")
    lines.append("      >")
    return lines
```

`PARMENV` on a macro is a real parameter change (plug-in macro IDs are 100–115). A one-point envelope at the normalized value is another way to set a knob.

### Placing the Chunk
- **Track instruments and inserts**: `<VST>` blocks inside `<FXCHAIN>` on the track (`BYPASS 0 0 0` before each).
- **Project limiter**: a summing aux with a Limiter insert. Set every other track's `MAINSEND 0 0`, send into the bus, and write `AUXRECV` on the **bus** (first field = source track index). Drive loudness with Limiter `gain_db` in the macros array; leave the bus `VOLPAN` at `1.0` so the fader does not boost past the ceiling. If true peak still overshoots, set `ceiling_db` a few tenths below −1.

---

## 🚦 Reaper Routing Gotchas (Avoid Silent Projects!)

When programmatically generating `.RPP` files, Reaper's routing engine is unforgiving. If you omit specific properties, Reaper will silently drop the audio, and the Master meter will remain flat.

Ensure every `<TRACK>` you generate includes the following properties:

1. **`TRACKID {guid}`**: You **must** generate and assign a unique GUID to the track. If `TRACKID` is missing, Reaper will refuse to process `AUXRECV` (Sends) for that track.
2. **`MAINSEND 1 0`**: You **must** explicitly include this property. Without it, the track will not send its audio to the Master buss. Use `MAINSEND 0 0` on tracks that feed a mix bus instead.
3. **`MUTESOLO 0 0 0`**: Explicitly declare the mute/solo state to ensure the track defaults to active.
4. **`AUXRECV` lives on the destination.** First field is the **source track index** (0-based). `dst_chan=0` → channels 1/2; `dst_chan=2` → channels 3/4 (sidechain key).
5. **Render block**: `SAMPLERATE 48000 1 0`, `RENDER_FMT 0 2 48000`, `RENDER_CFG ZXZhdxgAAQ==` (24-bit WAV). The second `SAMPLERATE` field enables the project-rate checkbox; the third `RENDER_FMT` field is the render rate.

**Example Track Definition:**
```text
  <TRACK {F6A3B9...}
    NAME "Bass Synth"
    VOLPAN 1.0 0.0 1 -1 1
    MUTESOLO 0 0 0
    NCHAN 2
    FX 1
    PERF 0
    MIDIOUT -1 -1
    MAINSEND 1 0
    TRACKID {F6A3B9...}
    <FXCHAIN
      ... (VST CHUNK GOES HERE) ...
    >
  >
```

By following this guide, you can successfully harness MPVST to build fully automated, AI-driven music generation pipelines inside Reaper!
