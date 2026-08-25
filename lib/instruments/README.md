# Hardware Emulations

53 classic synthesizers, electromechanical keyboards, and drum machines,
each a self-contained `synthio` script - no samples. See "Testing" and
"Hardware-Accuracy Pass" below before trusting anything above that line
as verified; the two passes after the initial one are what actually ran
these against real audio and real hardware behavior.

## 1. Classic Synthesizers

1. **[`minimoog.py`](minimoog.py)**: Moog Minimoog Model D (3-osc fat monosynth with overdrive and glide)
2. **[`prophet5.py`](prophet5.py)**: Sequential Circuits Prophet-5 (5-voice poly with poly-mod approximation)
3. **[`jupiter8.py`](jupiter8.py)**: Roland Jupiter-8 (Lush cross-modulated polysynth with massive unison spread)
4. **[`juno106.py`](juno106.py)**: Roland Juno-106 (Classic DCO with simulated bucket-brigade chorus and sub-oscillator)
5. **[`cs80.py`](cs80.py)**: Yamaha CS-80 (Dual-layer architecture with fast tremolo/ring mod)
6. **[`ms20.py`](ms20.py)**: Korg MS-20 (Aggressive peaking filters and EG2 sweeps)
7. **[`arp2600.py`](arp2600.py)**: ARP 2600 (3-oscillator semi-modular with VCA/VCF separate envelopes)
8. **[`odyssey.py`](odyssey.py)**: ARP Odyssey (Duophonic tracking with sync and ring mod approximation)
9. **[`dx7.py`](dx7.py)**: Yamaha DX7 (Iconic "E.Piano 1" emulation using additive sine harmonics with disparate envelopes)
10. **[`prophet_vs.py`](prophet_vs.py)**: Prophet VS (4 distinct wavetables mixed dynamically via Joystick X/Y macros)
11. **[`jp8000.py`](jp8000.py)**: Roland JP-8000 (The ultimate Trance "Supersaw" built from 7 heavily detuned/panned sawtooths)
12. **[`nord_lead.py`](nord_lead.py)**: Nord Lead (Virtual Analog edge with Morph macros tied to cutoff/resonance/sync)
13. **[`andromeda.py`](andromeda.py)**: Alesis Andromeda A6 (Dual filters - Moog-style LPF + SEM-style HPF - mixed per voice)
14. **[`k2600.py`](k2600.py)**: Kurzweil K2600 (VAST-inspired 4-layer evolving orchestral/cinematic pad with shimmer delays)

## 2. Electromechanical & Vintage Keyboards

1. **[`rhodes.py`](rhodes.py)**: Fender Rhodes Suitcase (Dual-layer Tine + Body synthesis with auto-pan tremolo and key-off noise)
2. **[`wurlitzer.py`](wurlitzer.py)**: Wurlitzer 200A (Aggressive asymmetrical reed modeling with "bite" and "bark" velocity macros)
3. **[`clavinet.py`](clavinet.py)**: Hohner Clavinet D6 (Plucked string physics with dynamic mute sliders and auto-wah filters)
4. **[`b3.py`](b3.py)**: Hammond B3 Organ (Additive drawbar synthesis, 3rd harmonic percussion, key clicks, and a Doppler/Tremolo Leslie simulation)
5. **[`pianet.py`](pianet.py)**: Hohner Pianet (Sticky-pad reed emulation with mellow sustain and bell attacks)
6. **[`vox_continental.py`](vox_continental.py)**: Vox Continental (Piercing divide-down transistor organ with iconic drawbar voicings)
7. **[`farfisa.py`](farfisa.py)**: Farfisa Compact (Buzzy garage-rock tabs mapped to Bass/Strings/Flute/Oboe with a screaming Multi-Tone Booster)
8. **[`solina.py`](solina.py)**: Solina String Ensemble (Thick ensemble chorus effects derived from modulating 3 panned oscillators per note)
9. **[`mellotron.py`](mellotron.py)**: Mellotron M400 (Tape replay emulation using flute wavetables, magnetic flutter LFOs, bandpass lo-fi filtering, and continuous tape hiss)
10. **[`cp70.py`](cp70.py)**: Yamaha CP-70 Electric Grand (Piezo-picked bright piano strings featuring a hammer strike transient and chorused tails)

## 3. Phase 4: Digital Pioneers & Deep Cuts

1. **[`cz101.py`](cz101.py)**: Casio CZ-101 (Phase Distortion synthesis emulation using sweeping low-pass over rich harmonic tables)
2. **[`d50.py`](d50.py)**: Roland D-50 (Linear Arithmetic synthesis blending short percussive transients with warm subtractive chorus bodies)
3. **[`ppg_wave.py`](ppg_wave.py)**: PPG Wave 2.2 (8-bit crunchy wavetable sweeping with modeled analog filters)
4. **[`tb303.py`](tb303.py)**: Roland TB-303 (The squelchy Acid House king with dynamic Accent envelope scaling)
5. **[`taurus.py`](taurus.py)**: Moog Taurus (Window-shaking bass pedals relying on heavy oscillator beating and low cutoffs)
6. **[`sh101.py`](sh101.py)**: Roland SH-101 (Punchy, fast-decay techno staple with sub-oscillator mixing)
7. **[`obxa.py`](obxa.py)**: Oberheim OB-Xa (Massive poly brass built on unison detuning and 12dB/octave-style filter approximations)
8. **[`polysix.py`](polysix.py)**: Korg Polysix (Raw 1VCO sound thickened heavily by a bucket-brigade style ensemble chorus)
9. **[`music_easel.py`](music_easel.py)**: Buchla Music Easel (West-coast complex oscillators driving a simulated vactrol Low-Pass Gate strike)
10. **[`wasp.py`](wasp.py)**: EDP Wasp (Unstable multi-mode filter fed by gritty digital oscillators)

## 4. Phase 5: Formants, VA, Samplers & Physical Modeling

1. **[`vp330.py`](vp330.py)**: Roland VP-330 Vocoder Plus (Static bandpass formant vocal approximations)
2. **[`fs1r.py`](fs1r.py)**: Yamaha FS1R (Dynamic morphing between vowel formants paired with complex FM carriers)
3. **[`virus.py`](virus.py)**: Access Virus (Ultimate Trance machine with a massive 5-saw "Hypersaw" architecture and overdrive)
4. **[`ms2000.py`](ms2000.py)**: Korg MS-2000 (Gritty Virtual Analog featuring a simulated Mod Sequence filter stepper)
5. **[`microwave.py`](microwave.py)**: Waldorf Microwave (Harsh wavetable crossfading modulated by deep envelope integration)
6. **[`emulator2.py`](emulator2.py)**: E-mu Emulator II (Synthesized 27kHz "Shakuhachi" breathy flute driven by noise bursts and limited bandwidth filters)
7. **[`fairlight.py`](fairlight.py)**: Fairlight CMI (Synthesized approximations of the famous "Arr1" breathy choir and "Orch5" orchestra hit with severe bitcrush filtering)
8. **[`sp1200.py`](sp1200.py)**: E-mu SP-1200 (Hip-hop drum modeling replicating the crunch of pitched-down 12-bit samples via hard-clipped wave layering)
9. **[`karplus.py`](karplus.py)**: Karplus-Strong Synthesis (Pure algorithmic acoustic string modeling using a noise burst exciting a highly resonant ringing low-pass body)
10. **[`vl1.py`](vl1.py)**: Yamaha VL1 (Wind acoustic modeling approximating breath pressure mapping to FM index, cutoff, and pitch growl simultaneously)
11. **[`tr707.py`](tr707.py)**: Roland TR-707 (Digital PCM drum synthesis approximations, focusing on tight rigid envelopes and inharmonic bell-like crash cymbals)
12. **[`drumtraks.py`](drumtraks.py)**: Sequential Circuits Drumtraks (Gritty 8-bit EPROM drum modeling mapping crunch and alias noise to core analog drum models)

## 5. Drum Machines (Previously Created)

1. **[`tr808.py`](tr808.py)**: Roland TR-808 Rhythm Composer
2. **[`tr909.py`](tr909.py)**: Roland TR-909 Rhythm Composer
3. **[`tr606.py`](tr606.py)**: Roland TR-606 Drumatix
4. **[`linndrum.py`](linndrum.py)**: Linn LM-1 / LinnDrum
5. **[`cr78.py`](cr78.py)**: Roland CR-78 CompuRhythm
6. **[`dmx.py`](dmx.py)**: Oberheim DMX
7. **[`simmons_sdsv.py`](simmons_sdsv.py)**: Simmons SDS-V

## Architecture

- Each instrument's control set maps to up to 16 VST automation macros via
  the `# mpvst-macro-labels` header.
- Voice allocation is a fixed pool (`MAX_VOICES`) with oldest-voice
  stealing when a chord or drum roll exceeds it.
- Synthesis is additive harmonic tables (`make_table`), noise generators,
  and `Biquad` filters - no samples.

## Testing

`python3 -m py_compile` only proves a script parses - it does not run a
single line of it, so it can't catch a bad API call or a macro that never
reaches the audio graph (both happened here; see below). Two real test
tools exist, both driving the actual script through actual `synthio`/
`audiocore` DSP:

- **`../../tools/test-instruments-lib.py`** - fast, no compiled engine or
  VST3 host needed. Runs every script (or the ones you name) against
  `../../tools/preview/harness.py`, a CPython stand-in for the sidecar
  built on the `audioif` wheel. Sweeps every declared macro through
  `0.0/0.5/1.0` under held notes, then checks a fresh instance produces
  non-silent audio at default settings. This is what you run while
  editing a script - a full pass over all 53 takes single-digit seconds.
- **`../../tools/test-instruments-plugin.py <smoke_host> <bundle.vst3>`**
  - slower, higher-fidelity: the same scripts through the real packaged
  MicroPython Instrument VST3 class (real protocol, real macro/state
  handling), via `mpvst_smoke_host --instrument-script`. Registered as
  the `mpvst_instruments_plugin` ctest; the fast version is
  `mpvst_instruments_library`.

Neither proves a script sounds like the hardware it emulates - only that
it doesn't crash and isn't silent. Hearing it is still on you.

## Correctness Pass (2026-08-25)

The first version of this library was machine-generated and verified only
with `py_compile`, and it showed: two API-misuse bugs made seven scripts
raise on the very first note (`synthio.Math()` has no `scale=` kwarg;
`synthio.Note()` has no `ring_mod=` kwarg - real ring modulation is
`ring_frequency=`/`ring_waveform=`), and roughly a third of the scripts
exposed a macro - most often "Filter Attack" or "Filter Sustain" - that
was read but never reached the audio graph. Both classes are exactly what
`test-instruments-lib.py` now catches automatically.

## Hardware-Accuracy Pass (2026-08-25)

A follow-up pass went beyond "doesn't crash": every remaining dead macro
now reaches the audio graph, and every emulation was checked against
what the real hardware actually does, not just against `synthio`'s
capabilities. Notable fixes: hard sync approximated by snapping the
slave oscillator toward a harmonic of the master (OB-Xa, Prophet-5,
Odyssey, Nord Lead); real ring modulation via `ring_frequency`/
`ring_waveform` instead of a fake tremolo (MS-20, Odyssey); real
variable-duty-cycle PWM tables instead of a volume-scaled no-op
(Jupiter-8, Juno-106, SH-101, Polysix); Karplus-Strong rebuilt as an
actual noise-into-feedback-delay string model instead of a filtered
noise burst; a Mellotron tape-hiss note whose amplitude was captured
once and never updated; drum machines that were secretly all
808-style pitch-swept synthesis regardless of whether the real machine
(LinnDrum, DMX) was sample-based or (Simmons SDS-V) swept far slower
than what was implemented. `Note.filter` and `Note.amplitude` are
mutable after construction, which is what makes real filter releases,
live channel/poly-pressure response, and reassigned filters at note-off
possible in a scripting model that otherwise builds each note's graph
once at note-on. Table generation (`make_table`, mostly) uses `ulab`
where it's a measured ~10x win, with a plain-Python fallback so
`test-instruments-lib.py` still runs without it.

## Patches

A patch is a named preset of the 16 macro values, selected live by MIDI
Program Change (0-127 - VST3 has no native program-change input event,
so the host maps an incoming Program Change message onto the plug-in's
`kIsProgramChange`-flagged "Patch" parameter, which the processor turns
into an `EVENT_PROGRAM_CHANGE` event data0=index/value0=normalized).

The convention (see `minimoog.py` for the reference implementation):
patches live in the instrument's own file, as a `PATCHES` dict next to
the macro defaults:

```python
PATCHES = {
    0: ("Init", (0.8, 0.35, 0.25, ...)),   # 16 values, macro order
    1: ("Deep Bass", (0.9, 0.2, 0.35, ...)),
}
```

and `handle_event`'s `EVENT_PROGRAM_CHANGE` branch looks the index up
and re-dispatches each value through the script's own `EVENT_PARAMETER`
handling, so the patch format never has to know how a script scales a
normalized macro value into its own units - that logic already exists
once, in the script:

```python
elif event_type == vstaudio.EVENT_PROGRAM_CHANGE:
    patch = PATCHES.get(data0)
    if patch is not None:
        for macro_index, macro_value in enumerate(patch[1]):
            handle_event(vstaudio.EVENT_PARAMETER, channel, note_id,
                         macro_index, macro_value, 0.0, sample_position)
```

Indices are sparse on purpose - give one an entry only when you have a
patch worth naming there. A script with no `PATCHES` dict, or no entry
for the index it receives, just leaves its macros wherever they already
are. Only `minimoog.py` has real patches so far; adding them to the rest
of the library is future work, not yet done.
