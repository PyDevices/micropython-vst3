# Writing your own instruments and effects

You do not need to build anything to write for MPVST: the installed plug-in
runs any script you point it at, and the library it ships is ordinary Python
you can read. Start from
[`lib/default_instrument.py`](../lib/default_instrument.py), point
`MPVST_SCRIPT_PATH` at your own file, and use the **MPVST Script Host** class.
The per-platform pages ([Windows](windows/README.md), [Linux](linux/README.md))
cover the edit-and-reload loop; this page is what a script can say about
itself and what the plug-in does with it.

If you want to change MPVST itself rather than write for it, that is
[development.md](development.md).

## Writing a script

A script registers a callback and an output. For a cataloged audioif
component, the provider metadata is mandatory; a consumer such as this
plug-in remains tolerant of missing optional fields.
The bundled `lib/default_instrument.py` is the working reference - it
tracks voices by VST note ID, maps velocity to amplitude, applies pressure
and pitch bend, and uses an explicit 50 ms release. **It is also deliberately
silent**: every event path is there, but it does not press a note unless
`MPVST_DEFAULT_INSTRUMENT_AUDIBLE` is set. It is what a Script Host class
loads when nothing else is chosen, so a project wired to a Script Host class
ID instead of a named instrument's would otherwise render a plausible synth
on every track and give nobody a reason to look. Silence is the alarm.

Events arrive through `vstaudio.on_event()` at absolute delayed sample
positions - note on/off with velocity and tuning, poly and channel
pressure, pitch bend, and all 128 MIDI CCs across 16 channels. Named
`vstaudio.EVENT_*` constants cover every type.

Macro automation arrives through the same callback as
`vstaudio.EVENT_PARAMETER`: `data0` is the zero-based macro index, `value0`
the normalised value, `sample_position` the absolute render sample. A script
declares which macros it has the same way a library module does, with a
module-level tuple:

```python
MACRO_LABELS = ("Gain", "Tone", "Attack", "Release")
MACRO_MODES = {0: "UNIPOLAR", 1: "UNIPOLAR", 2: "UNIPOLAR", 3: "UNIPOLAR"}
PATCHES = {0: ("Default", (64, 64, 64, 64))}
```

A bare script without those declarations is still accepted by this consumer
for compatibility and the editor draws no macros or patches. Audioif
providers must declare the empty forms explicitly when they expose no
controls. Renaming a label does not change parameter IDs or detach
automation.

Every instrument also declares `PATCHES`, whose first entry is the sound
its own defaults describe. That is what an unset macro resolves to - not
the middle of its range, which is not "off" and not anything intended.
Values are MIDI integers 0-127. `tools/derive_patches.py` generates the
block by measuring the instrument rather than guessing.

### Where the instruments live

The fifty-three instruments and the effects library are audiocomponents'
`audioinstruments` and `audioeffects` packages - host-neutral Python built
on audioif's audio nodes, that any application can import, not just this
plug-in. They are staged beside the engine from a sibling audiocomponents
checkout (`MPVST_COMPONENTS_LIB` if it is somewhere else; `MPVST_AUDIOIF_LIB`,
the name from when they lived in audioif, is still honoured for one release).

There is no file per instrument. The unit the plug-in deals in is still a
script - the controller parses macro labels out of the embedded source,
and a saved project embeds its bytes - but that script is now *built* from
its catalog entry when a class is instantiated, rather than kept on disk.
Two lines, synthesized in `CatalogEntry::scriptSource`. That is what lets
the library be the single source of truth for a plug-in's name, category
and macro labels: there is no generated copy to drift from it.

An audioif provider declares `NAME`, `MACRO_LABELS`, `MACRO_MODES`, and
`PATCHES`; percussion instruments also declare `NOTE_MAP`. `CATEGORIES`,
`VERSION`, `VENDOR`, and `DISPLAY_NAME` are optional. This consumer requires
only `NAME` when it discovers a component, and uses `DISPLAY_NAME` when
available for the host-facing title. Its class ID is derived from the file
path plus the stable `NAME`, so a copy of one of ours is automatically a
distinct plug-in - and renaming the file or `NAME` is a breaking identity
change.

`mpvst-` marker comments live in `moduleinfo.json` and nowhere else. A `.py`
file - a library module, an effect class, a script you wrote - declares itself
with variables. JSON5 comments are the only extension slot moduleinfo.json
has, which is why they exist there; nothing reads one out of Python.

The consumer reads `MACRO_LABELS` and `PATCHES` when present, and reads
`MACRO_MODES` when a UI wants to distinguish a unipolar, bipolar, or toggle
control. A missing field is treated as absent. The parameters themselves are
unaffected - all sixteen macro slots and the patch parameter are permanent,
because they are what a host automates - but an undeclared optional surface
does not receive a fabricated control.

`lib/mpvst_instrument_adapter.py` is the seam between the two. `vstaudio` speaks the
normalised floats the VST3 parameter API uses; the instrument API speaks
MIDI 0-127, because that is what a keyboard, a sequencer and a saved
patch speak. The conversion happens there and nowhere else, as a multiply
rather than a quantization, so a host automating a macro with more than 7
bits keeps its resolution.

The soundtrack's piece-private instruments stay whole scripts in their
own piece directory - those files *are* the patches - and end in a
`__main__` guard handing `create` to the same adapter.

`audioeffects` is forty-plus effect classes (dynamics, EQ, reverb, delay,
modulation, drive, pitch and stereo) importable from any effect script. Build
them through `audioeffects.create(name, source, sample_rate, **options)` so
the construction boundary stays portable across CPython, MicroPython and
CircuitPython; direct class constructors remain an implementation convenience.
It compensates for two CircuitPython biquad quirks that audioif
reproduces deliberately: filters in a stereo `audiofilters.Filter` centre
at twice the requested frequency, so the library halves what it asks for;
and peaking EQ's `b2` sign is wrong upstream, so bells are built from
notch and band-pass sections instead. The factory configures the sample rate
for each component before construction; scripts do not need to manage a
process-wide rate.

## Choosing the right class ID

A generated project names the plug-in by class ID, and there are two kinds.
Each named instrument and effect has **its own** ID; the two **Script Host**
IDs are the generic ones that run a bare script. Reach for a Script Host only
when the script is the point. Use it for a named instrument and every track
gets `default_instrument.py` instead - which, since it is deliberately silent,
now renders nothing rather than sounding like a plausible synth on every
track. That is the intended alarm.

The IDs live in `Contents/Resources/moduleinfo.json` inside the installed
bundle: match on `Name` and take the `CID` beside it. Do not hardcode one from
a document - including this one - because the file in the bundle is the only
copy that cannot drift.

## Putting a script into a project file yourself

If you generate project files rather than saving them from a DAW - a composer
script emitting `.RPP`, say - the script and its macro values travel in the
plug-in's **state chunk**. Get the layout wrong and the plug-in rejects the
chunk, which is worth knowing about before it costs you a day:

> **A rejected chunk is silent.** `setState` returns an error, the host
> discards it without a message, and the instance falls back to the two-line
> script the catalog synthesizes from the class ID - `run("Limiter")`, no
> arguments. It plays. It sounds plausible. Nothing anywhere says your script
> did not run. If a value you set in a generated project seems to have no
> effect, check the chunk before you suspect the DSP.

The component state is little-endian, in this order:

| Field | Type | Notes |
|---|---|---|
| version | `int32` | `2`. `1` is accepted for old projects |
| bypass | `int32` | 0 or 1 |
| macros | `float32` x 16 | normalized 0.0-1.0, one per macro |
| pipeline blocks | `int32` | 4 is the shipping value |
| script length | `int32` | bytes, not characters |
| script | bytes | UTF-8, no terminator needed |

REAPER wraps that in its own framing before it reaches us: a header of
`uint32` words, then `<uint32 length-of-component-state><uint32 1>`, the
component state, and eight zero bytes. `reaper/matrix/build_effect_project.py`
does exactly this in about twenty lines - `component_state()` at line 24 and
`chunk_lines()` at line 32 - and it is the reference to copy, because it is
run by a test rather than kept in a document.

**Put your values in the macros array, not in constructor arguments.** The
sixteen floats are what the plug-in restores and replays, so they are the
values that survive; a macro you leave alone keeps whatever the component
chose for itself. A constructor argument is not visible to the host at all,
so a project cannot round-trip one.

## Parameters and state

20 visible parameters - bypass, `Reload Script`, read-only `Engine Ready`
and `Engine Error`, a patch selector, and 16 macros - plus 2,080 hidden
16-channel MIDI mapping parameters. REAPER reports three more of its own.

Macro parameter IDs are permanently 100-115. Current macro values are
replayed to the script whenever it loads, reloads, or is restored from
project state, so an automated or reopened instance sounds the way it was
saved.

`Engine Error` reports 0 for clear, 1 for a script load failure, 2 for an
uncaught exception while rendering, and 3 for an uncaught exception in a
reload callback.

Project state embeds the active script source, so reopening a project does
not depend on the original path. State v2 accepts legacy v1 and caps
embedded source at 1 MiB.

An instance started from `MPVST_SCRIPT_PATH` follows that file: toggling
`Reload Script` re-reads what is on disk, and saving embeds the current
source. A project restored from state keeps its embedded snapshot and
ignores later edits to the original file. Reload is a rising edge - toggle
off then on - and is only observed while the plug-in is processing; the
value itself is not saved as state. Output uses a 128-sample fade-out, a
640-sample hold at the current 128-frame/512-latency setup, then a
128-sample fade-in.

Host transport position, tempo and time signature reach the script.
Locates, loop wraps and play-state changes arrive as
`vstaudio.EVENT_TRANSPORT`, and `vstaudio.transport()` returns
`(playing, seconds, bpm, numerator, denominator)`.

`SidecarTransport::telemetry()` reports queue depth, render time,
underruns, event drops, restarts, error code and last exit reason, with
peaks tracked from the audio thread. An exit code of `-1000` means the
supervisor killed an engine that had hung rather than finding one that
exited on its own.

Environment variables: `MPVST_HEAP_BYTES` caps the MicroPython heap per
instance, `MPVST_SCRIPT_PATH` selects a developer script, and
`MPVST_ENGINE_PATH` overrides which engine binary is launched.
