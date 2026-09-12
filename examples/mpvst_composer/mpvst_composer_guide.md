# MPVST Composer Framework Guide

The `mpvst_composer` framework is a Python-based Domain Specific Language (DSL) for programmatically generating DAW project files (currently supporting Reaper `.RPP`). 

By writing your compositions in Python rather than static file formats, you unlock the ability to use variables, loops, mathematical patterns, and music theory logic to rapidly generate complex arrangements.

---

## 🚀 Getting Started

To use the framework, you need:
1. The `mpvst_composer` Python package in your workspace.
2. A generated `patches_dump.json` file in your working directory. (This file maps human-readable patch strings to their integer indices. You can generate it using the `dump_patches.py` utility).

**Basic Skeleton:**
```python
from mpvst_composer import Project, Note, Scale, MidiPattern, MidiEvent
from mpvst_composer.backends.reaper import ReaperRenderer

# Create a new project in D Minor
song = Project(name="My First Song")
song.set_key(Note.D, Scale.MINOR)

# ... define tracks and patterns ...

# Render the project to a file
song.render("MySong.RPP", ReaperRenderer)
```

---

## 🎼 The Music Theory Engine

One of the most powerful features of `mpvst_composer` is its scale-degree abstraction. Instead of hardcoding absolute MIDI note numbers (e.g., C4 = 60), you write melodies and chords using **Scale Degrees**.

- `degree=1`: The Root note of the scale.
- `degree=3`: The Third of the scale (automatically major or minor depending on your `Project` key).
- `degree=5`: The Fifth.
- `accidental=1`: Sharp the note by one semitone. `accidental=-1`: Flat the note.

**Why do this?** Because if you decide your song sounds better in G# Dorian instead of D Minor, you simply change `song.set_key(Note.Gs, Scale.DORIAN)` at the top of your script, and the *entire composition* will instantly regenerate in the new key!

---

## 🎹 Tracks & Instruments

You can add standard instrument tracks to your project. The framework will automatically resolve the string `patch` name using your `patches_dump.json` manifest.

```python
bass_track = song.add_track("Synth Bass", instrument="minimoog", patch="Classic Lead")
```

---

## 🎛️ Effects & Routing

You can add Master effects (applied to the whole song), or Aux Tracks (send-returns) for things like shared Reverb.

**Master Effects:**
```python
song.add_master_effect("TapeDelay", mix=0.2, feedback=0.4)
```

**Aux Tracks (Sends):**
```python
# 1. Create an Aux track hosting a Reverb
verb_aux = song.add_aux_track("Big Verb", effect="Reverb", preset="hall")

# 2. Route an instrument track into the Aux track
bass_track.add_send(verb_aux, send_level=0.5)
```

**Sidechain Compression (Advanced Routing):**
You can sidechain one track to another (e.g., ducking the bass when the kick hits) by routing the send to the auxiliary channels (channels 3/4, which is `dst_chan=2`).
```python
# Send kick drum to bass sidechain
drums_track.add_send(bass_track, send_level=1.0, src_chan=0, dst_chan=2)

# Insert a compressor on the bass track that listens to the sidechain input
bass_track.add_insert("compressor", threshold=0.1, ratio=10.0, attack=0.001, release=0.1)
```

---

## 🕒 Tempo & Time Mapping

The framework handles complex tempo changes automatically. Reaper requires MIDI items to be placed using absolute seconds, but humans write music in beats and measures. 

Simply define your tempo markers, and the `ReaperRenderer` will mathematically integrate the tempo map to place everything perfectly on the grid.

```python
# Start the song at 120 BPM
song.add_tempo_marker(measure=1, bpm=120)

# Jump to 140 BPM at measure 17
song.add_tempo_marker(measure=17, bpm=140)
```
*(Note: Measures are 1-indexed. Measure 1 is the start of the song).*

---

## 📝 Writing Musical Patterns

Music is arranged using `MidiPattern` blocks, which contain `MidiEvent`s. 

- `start_beat`: Relative to the start of the pattern (0.0 is the first beat).
- `length_beats`: How long the note is held.
- `degree`, `octave`, `velocity`: Musical properties.

**Creating a Pattern:**
```python
# Create a pattern that starts at measure 5 and repeats 4 times
lead_pattern = MidiPattern(start_measure=5, repeat=4)

# Add events to the pattern
lead_pattern.add_event(MidiEvent(start_beat=0.0, length_beats=1.5, degree=1, octave=4))
lead_pattern.add_event(MidiEvent(start_beat=1.5, length_beats=0.5, degree=5, octave=4))

# Attach the pattern to a track
lead_track.add_pattern(lead_pattern)
```

---

## 🥁 Drum Patterns & Chokes

You can create realistic drum sequences using `DrumPattern`. Drum hits are mapped via simple strings (`"kick"`, `"snare"`, `"open_hihat"`, etc.) which are automatically mapped to General MIDI standards.

Even better, `DrumPattern` includes realistic Open/Closed hi-hat choke logic. It scans your pattern and truncates the length of Open Hi-Hat hits so they are perfectly "choked" exactly when the next Closed Hi-Hat hits.

```python
drums = DrumPattern(start_measure=1, repeat=4)
drums.add_hit(0.0, "kick")
drums.add_hit(1.0, "snare")

# The open hi-hat will ring until the closed hi-hat on beat 3!
drums.add_hit(2.5, "open_hihat")
drums.add_hit(3.0, "closed_hihat")
```

---

## 🎛️ MIDI Expressiveness (CC & Pitch Bend)

You can add continuous control data to any `MidiPattern` or `DrumPattern` using `MidiControlEvent`.

```python
# Mod Wheel (CC 1) swell
pat.add_control_event(MidiControlEvent(start_beat=0.0, cc_num=1, value=0))
pat.add_control_event(MidiControlEvent(start_beat=2.0, cc_num=1, value=127))

# Pitch Bend drop (center is 8192)
pat.add_control_event(MidiControlEvent(start_beat=3.5, pitch_bend=0))
pat.add_control_event(MidiControlEvent(start_beat=4.0, pitch_bend=8192))
```

---

## 🎸 Chords & Arpeggiators

Use the `TheoryEngine` and `Chord` enum to effortlessly fetch chords and inject them into patterns.

```python
from mpvst_composer import Chord
# Get absolute degrees for a minor Triad
triad_degrees = song.theory.get_chord_degrees(root_degree=1, chord_type=Chord.TRIAD)

# Get a First Inversion minor Triad (moves the root note up an octave)
inv_triad_degrees = song.theory.get_chord_degrees(root_degree=1, chord_type=Chord.TRIAD, inversion=1)

# Generate an arpeggio using the inverted chord
arp = MidiPattern.create_arp(start_measure=1, root_degree=1, chord_degrees=inv_triad_degrees, direction="updown")
```

---

## 🦾 Humanization Engine

You can instantly breathe life into mechanical sequenced patterns using the `.humanize()` method. It adds realistic, randomized jitter to note velocities and timing.

```python
drums.humanize(velocity_jitter=15, timing_jitter_beats=0.03)
```

## 🕺 Swing & Groove Templates

If humanization provides random jitter, **Swing** provides structured, algorithmic groove (like a classic Akai MPC drum machine). 

By calling `.apply_swing()`, you can shift all off-beat subdivisions late by a percentage amount.
```python
# Apply classic 90s hip-hop 62% swing to 16th notes
drums.apply_swing(amount=0.62, subdivision=0.25) 
```

---

## 📈 Macro Automation & Tempo Curves

**Linear Tempo Ramps:** Create smooth accelerandos/decelerandos by setting `transition="linear"`. The engine handles the mathematical tempo integration for absolute MIDI placements.

```python
song.add_tempo_marker(measure=1, bpm=120)
# Linearly ramp from 120 to 140 bpm over 8 measures
song.add_tempo_marker(measure=9, bpm=140, transition="linear")
```

**VST Macro Automation:** Automate the 8 Macros on your VSTs using `MacroAutomation`. Note: The `macro_index` (0-7) maps to the VST's exposed parameter index.

```python
from mpvst_composer import MacroAutomation

sweep = MacroAutomation(macro_index=0)
sweep.add_point(measure=1, beat=0.0, value=0.0) # Start closed
sweep.add_point(measure=5, beat=0.0, value=1.0) # Open filter over 4 measures

lead_track.add_automation(sweep)
```

**Mix Automation (Native Track Volume and Pan):** Automate the DAW's actual track faders and pan dials using `VolumeAutomation` and `PanAutomation`.

```python
from mpvst_composer.models import VolumeAutomation, PanAutomation

# Fade out the track
vol_auto = VolumeAutomation()
vol_auto.add_point(1, 0.0, 1.0) # 0 dB
vol_auto.add_point(4, 0.0, 0.0) # -inf dB
lead_track.add_volume_automation(vol_auto)
```

---

## 🔌 Backends & Extending

The framework is strictly decoupled from the DAW rendering logic. The `Project` class is just an abstract representation of a song. 

To turn it into a Reaper project, you pass the `ReaperRenderer` class into the `render()` function. If you want to support a new DAW (e.g., Logic Pro, ProTools, or Ableton), you simply create a new Backend class that implements the `BaseRenderer` interface!

---

## Discoveries from Afterimage (Signal Room)

These notes come from bouncing the 8-bar test cue and the seven-track EP. They override older examples in this guide where the two disagree. The VST tree was not edited; every workaround lives in `mpvst_composer` or workspace scripts.

### Test cue

`source/00_test_cue.py` is the smallest project that should make sound: D minor, 118 BPM, 8 bars, TR-808 + Minimoog (Deep Bass) + Juno-106/Chorus + SH-101/Saturation, hall send, kick→bass duck, mix-bus limiter. Headless bounce:

```
C:\Users\bradb\REAPER\reaper.exe -nosplash -newinst -renderproject bounce\<stem>.rpp
```

`-renderproject` honors the RPP render block and exits. `bounce_qc.py` writes the RPP, calls that command, then measures the WAV. Lua (`render_and_quit.lua`) is only a fallback.

### Inserts, patches, CIDs

- Track inserts are extra `<VST>` blocks in the same `<FXCHAIN>` as the instrument (`BYPASS 0 0 0` before each).
- Instruments: `inst = mpvst_instrument_adapter.run('audioinstruments.X'); inst.program_change(N)`. Never `run(..., patch_index=N)` — the adapter is `run(name)` only.
- **Use each plug-in's own CID** from `moduleinfo.json` (and Reaper's numeric id from `reaper-vstplugins64.ini`). The Script Host CIDs (`896536053{60A40168…}` / `1503031402{910677E2…}`) load `default_instrument.py` and `default_effect.py`, so every track is the same sound. Display names are not enough — the TUID in braces selects the class.

### Routing

- `AUXRECV` is written on the **destination**. First field is the **source track index** (0-based; auxes first, then instruments):
  `AUXRECV {src_idx} {mode} {level} 0 0 0 0 {dst_chan} {src_chan} -1:0 -1`
  `dst_chan=0` → channels 1/2, `dst_chan=2` → channels 3/4.
- Emit `VOLPAN` from `track.volume` / `track.pan`. Reaper volume is linear amplitude (`1.0` = 0 dB).
- `Track.mainsend` / `AuxTrack.mainsend` (0/1). Sends are collected from every node.

### Sidechain (the guide example above is wrong)

MPVST **Compressor has no `key=`**. `NoiseGate(duck=True)` and `Expander(key=)` do. The renderer emits a custom payload for those: `audioeffects.create(..., key=host, duck=True, ...)`.

A 4-channel key into MPVST is **not reliable**. `Project.apply_sidechain_duck()` also writes volume-envelope dips at kick hits — that is what makes ducking audible.

```python
drums.add_send(bass, 1.0, dst_chan=2, mode=1)
bass.add_insert("NoiseGate", sidechain=True, duck=True, threshold_db=-30,
                attack_ms=1.0, hold_ms=30, release_ms=110, range_db=-8)
song.apply_sidechain_duck(drums, bass, "kick", depth=0.38, attack_beats=0.02,
                          hold_beats=0.07, release_beats=0.18)
```

### Mix bus, limiter, and the VST chunk

Use `Project.add_mix_bus()` + `route_to_mix_bus()`: a summing aux with a Limiter insert; instrument tracks and return auxes get `mainsend=0` and send into the bus. Put **drive on limiter `gain_db`**, not on a post-FX mix fader — Reaper `VOLPAN` is after the insert, so a fader boost will clip a ceilinged signal. Leave `mix.volume = 1.0` unless you need a trim *below* the ceiling.

`MASTERFXLIST` with the real Limiter CID is unproven either way. The bounce that "proved master FX is ignored" was using the Script Host CID (`default_effect.py`, a wire).

**Constructor kwargs only stick if they are also in the VST3 state chunk.** A rejected chunk is silent: the host drops it and the instance plays the catalog two-liner (`run("Limiter")`, no arguments). The old composer wrote `<uint32 length><script>`, which the plug-in read as `version=1150` and rejected. Layout (little-endian), copied from `reaper/matrix/build_effect_project.py`:

| Field | Type | Notes |
|---|---|---|
| version | `int32` | `2` |
| bypass | `int32` | 0 or 1 |
| macros | `float32` × 16 | normalized 0–1; unused slots stay 0.5 |
| pipeline blocks | `int32` | `4` |
| script length | `int32` | bytes |
| script | bytes | UTF-8, no terminator |

REAPER wraps that in a header of `uint32` words (first word = per-class numeric id, not Script Host `0x35700DF5` / `0x5996706A`), then `len+flag` + component + 8 zero bytes, base64 with a 6-zero footer.

**Put values in the macros array, not only in `run(...)` kwargs.** Limiter: Ceiling (−24…0 dB), Gain (0…24 dB) so `gain_db=8` → macro 1 = `8/24 = 0.3333`. Named patches and MIDI `program_change` still work; the 16 floats are what the plug-in restores and replays. `PARMENV` on macro index 0–15 is a real parameter change and also sticks (IDs 100–115 in the plug-in). Constructor-only options with no macro (Reverb `preset=`, Saturation `character=`) need a valid chunk so the embedded script actually runs.

Do not post-fader a limited bus. If true peak still overshoots the ceiling by a few tenths, set `ceiling_db` a bit below −1 (the test cue uses −1.6).

### Pattern length and drums

- Pattern span is last-event, not “bars you meant.” `repeat` multiplies `length_measures`. A 4-chord cell at 4 beats each is 4 bars; `repeat=6` covers 24 bars. Gaps in that math become digital-black holes.
- One-shot drums (808/909/Linn) decay below −80 dBFS between hits. If no pad/bass is holding, QC sees mid-file dropouts >400 ms. Put 8th-note hats under sparse outros, or keep a bed.
- `resolve_drum_note` prefers per-instrument `NOTE_MAP`, then GM aliases (`kick`, `closed_hihat`, `cowbell`, toms, …).
- `create_arp` fills `bars` (default 1). `beats_per_bar` is not hardcoded 4/4.

### Headless bounce and QC

RPP render block: `SAMPLERATE 48000 1 0` (second field enables the project-rate checkbox), `RENDER_FILE`, `RENDER_FMT 0 2 48000` (third field is the render rate — `0` falls back to 44.1 kHz), `RENDER_RANGE 1 0 0 0 {tail_ms}`, `RENDER_CFG ZXZhdxgAAQ==` (24-bit WAV). GUIDs wrapped in `{...}`. `MAINSEND`, `TRACKID`, `NCHAN` (4 when a sidechain dest), `FX 1`.

`bounce_qc.py` contract: 24-bit / 48 kHz, integrated **−15.5..−13.0 LUFS** (target −14), true peak **≤ −1.0 dBTP**, lead silence <400 ms, trail slack for reverb, fail on digital-black or mid-file runs of silence >400 ms at −80 dBFS. True peak is 4× `resample_poly`. Packages: `soundfile`, `pyloudnorm`, `scipy`, `numpy`.

```
python bounce_qc.py 00_test_cue --timeout 240
python bounce_qc.py --timeout 400
```

### dump_patches

Walk `audioinstruments.ALL` and effect **classes** (`NAME` / `PATCHES` / `MACRO_LABELS`). Nested format:

```json
{
  "instruments": {
    "minimoog": {
      "patches": {"1": ["Deep Bass", []]},
      "macros": [],
      "note_map": null
    }
  },
  "effects": {
    "Chorus": {"patches": {}, "macros": []}
  }
}
```

`resolve_instrument_patch` reads the nested `"patches"` object, with a fallback to legacy flat keys. Load `patches_dump.json` from CWD or the workspace root.

### Afterimage bounce (measured)

| Stem | LUFS | TP dBTP | Length |
|---|---|---|---|
| `00_test_cue` | −14.50 | −1.53 | 16.3 s |
| `01_glass_corridor` | −14.15 | −1.54 | 5:03 |
| `02_night_shift` | −14.91 | −1.04 | 3:16 |
| `03_loading_dock` | −15.13 | −1.50 | 3:37 |
| `04_second_hand` | −13.99 | −1.57 | 3:12 |
| `05_service_elevator` | −13.99 | −1.52 | 4:17 |
| `06_under_the_overpass` | −14.99 | −1.54 | 3:40 |
| `07_hold_pattern` | −14.11 | −3.14 | 5:20 |

