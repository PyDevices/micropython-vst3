# MicroPython VST3

Programmable VST3 instrument and audio effect backed by dedicated
MicroPython engine processes. One bundle ships two plug-ins: the
**MicroPython Instrument** (event input, stereo out) and the
**MicroPython Effect** (stereo in and out), whose script reads the host
audio through `vstaudio.input()` and can run it through any audioif
chain - filters, echoes, chorus, freeverb, mixers - or synthesize
alongside it. `lib/effects` ships a library of ready-made effect
classes (compressors, EQs, reverbs, delays, modulation, drive, pitch
and stereo tools) importable from any effect script.
The VST audio callback remains native and real-time safe; Python, garbage
collection, filesystem access, and engine lifecycle work stay in the sidecar.

Windows and Linux VST3 builds both ship, using the host's generic parameter
editor. An LVGL editor and audio-input effects are deliberately deferred.

See [PLAN.md](PLAN.md) for phase status and
[docs/architecture/phase-0.md](docs/architecture/phase-0.md) for the locked
architecture contract.

## Current milestone

All eight phases are complete. The instrument runs in REAPER on Windows and on
Linux, and the same script and project state render byte-identical PCM on both.
Current capabilities include:

- one 16-channel event input with sample-positioned note-on/off, velocity,
  tuning, poly-pressure, channel pressure, pitch bend, and all 128 MIDI CCs;
- one stereo float32 output;
- bypass, a generic-editor `Reload Script` action, and 16 stable macro
  parameters;
- bounded component-state persistence including script source, macros, and
  engine settings;
- no allocation, locking, or Python execution in `process()`;
- one independent MicroPython process per active plug-in instance;
- structured syntax and runtime error reporting; and
- script correction and reload without reloading the VST or sidecar process;
- an edit-and-reload developer loop that re-reads the script from disk, while a
  saved project keeps rendering from the source embedded in its state;
- host transport position, tempo, and time signature, with locates and loop
  wraps delivered to the script as transport events; and
- queue-depth, render-time, underrun, drop, restart, and exit-reason telemetry.

The generic editor also exposes read-only `Engine Ready` and integer
`Engine Error` status. Reloads use a deterministic 128-sample fade-out, pipeline
hold, and 128-sample fade-in.

The bundled example instrument tracks voices by VST note ID, maps velocity to
voice amplitude, applies pressure and ±2-semitone pitch bend, and uses an
explicit 50 ms release envelope. User scripts can replace that policy through
`vstaudio.on_event()`.

Macro 01–16 automation is delivered through the same callback as
`vstaudio.EVENT_PARAMETER`: `data0` is the zero-based macro index, `value0` is
the normalized value, and `sample_position` is the absolute delayed render
sample. Named `vstaudio.EVENT_*` constants are available for every event type.

Project state embeds the active development script, so reopening a project does
not depend on the original path. State v2 accepts legacy v1 state and limits
embedded source to 1 MiB. A script can label the stable Macro 01–16 automation
IDs for the generic editor with a header comment:

```python
# mpvst-macro-labels: Gain | Tone | Attack | Release
```

Changing these labels does not change parameter IDs or detach automation.

Create the Windows release archive with `./scripts/package-windows.sh`. The
script verifies all bundled engine/bootstrap files and emits a versioned ZIP
plus SHA-256 file under ignored `dist/`. See
[docs/windows-workflow.md](docs/windows-workflow.md) for installation and the
desktop-script security model.

In a DAW's generic parameter editor, toggle `Reload Script` off and then on to
request each subsequent reload. The rising edge is the action; the value itself
is not saved as project state.

## Getting started

A fresh clone has none of the external dependencies this repo needs
(the VST3 SDK, the sibling `cmods`/`audioif` repos the engine build
depends on, or REAPER for the DAW-driven tooling) - `.deps/` and those
sibling checkouts are all gitignored. One command sets all of it up:

```bash
./scripts/bootstrap.sh
```

See [scripts/README.md](scripts/README.md) for what it does and how to
run each step individually.

## Configure

Fetch the pinned VST3 SDK dependency:

```bash
./scripts/fetch-vst3-sdk.sh
```

Build the Windows MicroPython sidecar before configuring the Windows VST. This
uses the sibling `audioif` repository read-only and places the result under the
ignored `.deps/engine` directory:

```bash
./scripts/build-micropython-engine.sh
```

Configure and build with CMake:

```bash
cmake -S . -B build -G Ninja
cmake --build build
```

Steinberg hosting tools are off by default so a plug-in-only build does not
pull in editor-host dependencies. Enable them in a dedicated validator build
with `-DSMTG_ENABLE_VST3_HOSTING_EXAMPLES=ON`.

`VST3_SDK_ROOT` may point at an existing checkout instead:

```bash
cmake -S . -B build -G Ninja -DVST3_SDK_ROOT=/path/to/vst3sdk
```

The release VST shell will be built with MSVC. A native Linux build is also
kept compiling during early phases because it gives fast source-level feedback
from WSL without changing the Windows-first product scope.

## Workspace isolation

The sibling `audioif` repository is an external dependency and must remain
read-only while its current independent work is in progress. No build or
formatting command in this repository writes into `audioif`.

The engine builder also leaves the sibling MicroPython checkout unchanged. It
uses the existing `cmods` transactional overlay mechanism and removes the
temporary `vstaudio` module link on exit, including failed builds.
