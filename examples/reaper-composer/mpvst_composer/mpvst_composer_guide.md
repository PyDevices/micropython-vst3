# MPVST Composer Framework Guide

The `mpvst_composer` framework is a Python-based Domain Specific Language (DSL) for programmatically generating DAW project files (currently supporting Reaper `.RPP`). 

By writing your compositions in Python rather than static file formats, you unlock the ability to use variables, loops, mathematical patterns, and music theory logic to rapidly generate complex arrangements.

---

## 🚀 Getting Started

You need a way to know what the instruments are, and a way to hear them.

1. **The components.** The composer has to learn every instrument, effect,
   patch and macro before it can write one. It asks
   `pydevices-audioinstruments` and `pydevices-audioeffects` if pip has them,
   and reads `catalog.json` out of an installed MPVST bundle otherwise. Either
   answers; `MPVST_BUNDLE` points at the plug-in if you put it somewhere
   unusual.
2. **Something to render with.** Reaper plays the `.RPP` you write. With no
   DAW at all, the CPython audio packages render it here instead. See
   [Rendering](#-rendering).
3. **This folder.** `mpvst_composer` itself needs nothing but the Python
   standard library - no build, no checkout of the plug-in's source.

Writing a Reaper project is the one thing that does need MPVST installed,
because an `.RPP` has to name each plug-in by its VST3 class ID and only the
bundle knows those. Everything else - the notes, the patches, the macros, an
offline render - works without it.

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

Add an instrument track and name the patch you want. The framework resolves
that name against `catalog.json` inside the installed plug-in, so the names
are the ones the instrument itself declares.

```python
bass_track = song.add_track("Synth Bass", instrument="minimoog", patch="Classic Lead")
```

Patch names are per instrument - `minimoog` has *Classic Lead*, *Deep Bass*
and *Screaming Lead*, while a drum machine may only have *Default*. If you
name one that does not exist you get patch 0 and a warning.

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

**Sidechain Ducking:**
To duck the bass when the kick hits, send the drums into the bass track's
auxiliary channels (3/4, which is `dst_chan=2`) and insert something that
listens to them. Note that **Compressor has no sidechain input** - the effects
that take a key are `NoiseGate(duck=True)` and `Expander(key=...)`.

```python
# Send the kick into the bass track's channels 3/4
drums.add_send(bass, 1.0, dst_chan=2, mode=1)

# A gate on the bass, ducking on what it hears there
bass.add_insert("NoiseGate", sidechain=True, duck=True, threshold_db=-30,
                attack_ms=1.0, hold_ms=30, release_ms=110, range_db=-8)

# And the volume dip that makes it audible
song.apply_sidechain_duck(drums, bass, "kick", depth=0.38, attack_beats=0.02,
                          hold_beats=0.07, release_beats=0.18)
```

The third line is doing more work than it looks. A four-channel key into the
plug-in is not reliable on its own, so `apply_sidechain_duck` also writes
volume-envelope dips at every kick hit - that is what you actually hear.

**A Mix Bus:**
`add_mix_bus()` gives you a summing aux with a Limiter on it, and
`route_to_mix_bus()` points everything at it. Put your drive on the limiter's
`gain_db` rather than on a fader: Reaper's volume is applied *after* the
insert, so a fader boost will push a ceilinged signal straight back through
the ceiling. Leave the bus fader at `1.0` unless you want a trim below it.

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

Two ship. `ReaperRenderer` writes a `.RPP` for a host to play; `OfflineRenderer`
plays it here and writes the WAV.

---

## 🎧 Rendering

There are two ways to hear a project, and they are for different moments.
(Four across the whole repo - the other two render the soundtrack's pieces.
[`docs/rendering.md`](../../../docs/rendering.md) is the chooser.)

**While you are writing it**, render it here - no DAW, no plug-in, nothing
installed:

```bash
python from_yaml.py my_song.yaml my_song.wav
```

The `.wav` picks `OfflineRenderer`, which plays the project through the same
`audioinstruments` and `audioeffects` packages the sidecar imports. Sixteen
voices over two and a half minutes take about two and a half minutes, against
the several a scan-load-and-bounce costs. From Python it is the same seam:

```python
from mpvst_composer.backends.offline import OfflineRenderer

song.render("my_song.wav", OfflineRenderer)
```

It needs `pydevices-audioif`, `pydevices-audioinstruments` and
`pydevices-audioeffects` from pip.

**Before you believe it**, bounce it through Reaper:

```bash
python bounce.py my_song.rpp
```

Run that from `examples/`. It drives Reaper headless and comes back with the
WAV your project names, needing Reaper and a Python interpreter and nothing
else.

Both paths agree closely - sixteen-voice Canon comes out 150.00 s and
-14.4 LUFS offline against 150.00 s and -14.1 LUFS bounced - but only the
bounce exercises the class IDs, the state chunk, the item timing and the
sends, because those are things the project file asserts and only a host can
honour. The offline render also leaves pan automation and sidechain keys
unmixed.

When you want to know how it came out:

```bash
python ../tools/audio_qc.py my_song.wav
```

That reports integrated loudness, true peak and any silence - a digitally
black file, a silent head, or holes in the middle usually mean a plug-in did
not load rather than anything about your music. It needs `numpy`, `soundfile`,
`pyloudnorm` and `scipy`.

---

## 🧯 Things that will bite you

- **Pattern span is the last event, not the bars you meant.** `repeat`
  multiplies `length_measures`, so a four-chord cell at four beats each is
  four bars and `repeat=6` covers twenty-four. Miscount and the gap renders as
  silence.
- **One-shot drums decay to nothing.** An 808 or a Linn under a sparse outro
  will fall below -80 dBFS between hits, which reads as a dropout. Keep
  something holding underneath, or accept the gaps.
- **Name the patch, not the index.** `program_change(N)` is how a patch is
  selected; there is no `patch_index=` argument on the adapter.
- **Don't put a fader after a limiter.** See the mix bus note above.
