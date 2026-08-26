# MicroPython VST3

Programmable VST3 instrument and audio effect backed by dedicated
MicroPython engine processes. One bundle ships two plug-ins: the
**MicroPython Instrument** (event input, stereo out) and the
**MicroPython Effect** (stereo in and out), whose script reads the host
audio through `vstaudio.input()` and can run it through any audioif
chain - filters, echoes, chorus, freeverb, mixers - or synthesize
alongside it.

The VST audio callback stays native and real-time safe. Python, garbage
collection, filesystem access, and engine lifecycle work all happen in a
separate sidecar process - one per active plug-in instance - so a script
that loops forever or exhausts memory takes down its own sidecar and gets
restarted, rather than taking the DAW with it.

Windows and Linux builds both ship, using the host's generic parameter
editor. The same script and project state render byte-identical PCM on
both platforms.

## Repository layout

| | |
|---|---|
| `src/` | the C++ that builds the plug-in: `plugin/` (VST3 classes), `protocol/` (the shared-memory wire format), `runtime/` (shared memory and child processes) |
| `usermods/vstaudio/` | the MicroPython C module that gives scripts their audio API |
| `lib/` | everything staged into the bundle beside the engine: `instruments/`, `effects/`, the bootstrap, and the default instrument |
| `tools/` | developer tooling - `composition/` and `preview/` for pieces, plus the library test sweeps |
| `tests/` | the ctest suite and `smoke_host/`, a minimal VST3 host that loads the bundle with no DAW |
| `scripts/` | build, packaging and setup automation |
| `reaper/` + `reaper.sh` | everything that drives REAPER. Deletable as a unit; nothing outside it depends on it |
| `soundtrack/` | example pieces, each with its own `composition.py` |

The architecture is written down in
[docs/architecture/phase-0.md](docs/architecture/phase-0.md) (the system
boundary and what each process owns) and
[docs/architecture/ipc-v1.md](docs/architecture/ipc-v1.md) (the
shared-memory protocol rules). Both still describe the shipping design;
the canonical structure sizes and offsets live in
`src/protocol/include/mpvst/protocol.h`.

## Getting started

A fresh clone has none of the external dependencies this repo needs - the
VST3 SDK, the sibling `cmods`/`audioif` repos the engine build depends
on, or REAPER for the DAW-driven tooling. `.deps/` and those sibling
checkouts are all gitignored. One command sets all of it up:

```bash
./scripts/bootstrap.sh
```

See [scripts/README.md](scripts/README.md) for what it does and how to run
each step individually.

## Building and testing

The MicroPython sidecar is built separately from the plug-in, and only
needs rebuilding when `usermods/vstaudio` changes. It lands in the ignored
`.deps/engine/`, and the plug-in build stages it into the bundle:

```bash
./scripts/build-micropython-engine.sh --port windows
./scripts/build-micropython-engine.sh --port unix
```

Linux:

```bash
cmake -S . -B .build-linux -G Ninja
cmake --build .build-linux
ctest --test-dir .build-linux --output-on-failure
```

Windows, driven from WSL with the vendored CMake. `scripts/install-plugin-windows.sh`
wraps the build and installs the result into the per-user VST3 directory a
DAW scans:

```bash
./scripts/install-plugin-windows.sh
```

The Linux CMake cache remembers the engine path. After switching engines,
reconfigure with
`cmake -S . -B .build-linux -U MPVST_MICROPYTHON_ENGINE`.

Steinberg hosting tools are off by default so a plug-in-only build does
not pull in editor-host dependencies. Enable them in a dedicated validator
build with `-DSMTG_ENABLE_VST3_HOSTING_EXAMPLES=ON`. `VST3_SDK_ROOT` may
point at an existing SDK checkout instead of the fetched one.

## Writing a script

A script registers a callback and an output; everything else is optional.
The bundled `lib/default_instrument.py` is the working reference - it
tracks voices by VST note ID, maps velocity to amplitude, applies pressure
and pitch bend, and uses an explicit 50 ms release.

Events arrive through `vstaudio.on_event()` at absolute delayed sample
positions - note on/off with velocity and tuning, poly and channel
pressure, pitch bend, and all 128 MIDI CCs across 16 channels. Named
`vstaudio.EVENT_*` constants cover every type.

Macro automation arrives through the same callback as
`vstaudio.EVENT_PARAMETER`: `data0` is the zero-based macro index, `value0`
the normalised value, `sample_position` the absolute render sample. A
header comment labels them for the generic editor:

```python
# mpvst-macro-labels: Gain | Tone | Attack | Release
```

Changing labels does not change parameter IDs or detach automation.

Every instrument in `lib/instruments/` also declares `PATCHES`, whose
first entry is the sound its module-level defaults describe. That is what
an unset macro resolves to - not 0.5, which is the middle of a range
rather than anything intended. `tools/derive_patches.py` generates the
block by measuring the script rather than guessing.

`lib/effects/` is a library of forty-plus effect classes (dynamics, EQ,
reverb, delay, modulation, drive, pitch and stereo) importable from any
effect script. It compensates for two CircuitPython biquad quirks that
audioif reproduces deliberately: filters in a stereo `audiofilters.Filter`
centre at twice the requested frequency, so the library halves what it
asks for; and peaking EQ's `b2` sign is wrong upstream, so bells are built
from notch and band-pass sections instead.

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

## Releases

`VERSION` at the repository root is the single source of truth - CMake and
both packaging scripts read it, so a binary and the archive around it
cannot disagree about which version they are.

```bash
./scripts/package-linux.sh
./scripts/package-windows.sh
```

Each produces a versioned archive plus a SHA-256 sidecar under the ignored
`dist/`, after verifying the bundle carries its engine and bootstrap.
See [docs/windows-workflow.md](docs/windows-workflow.md) and
[docs/linux-workflow.md](docs/linux-workflow.md) for installation and the
desktop-script security model.

## Testing against a real DAW

`ctest` covers the plug-in with no DAW involved. Two further harnesses use
REAPER, and both need the packaged plug-in installed first because they
exercise the installed bundle:

```bash
./reaper/matrix/run-reaper-matrix.sh --platform windows
./reaper/matrix/run-reaper-matrix.sh --platform linux
```

The matrix drives REAPER headlessly through a startup ReaScript, covering
what only a real host can - FX chain add/remove, parameter automation,
project save/reload, macro resync. It overwrites `Scripts/__startup.lua`
in REAPER's resource path, so remove that file before using REAPER
interactively. A host with no live audio device only processes during a
render, so the matrix forces a short render before reading any status
parameter.

```bash
./scripts/check-cross-platform-parity.sh
```

Both smoke hosts render a fixed score through the real MicroPython sidecar
and the raw float32 PCM is compared. The current result is an identical
SHA-256 - the platforms agree exactly, not within a tolerance.

`./reaper.sh` renders and plays the example pieces; see
[reaper/README.md](reaper/README.md) and
[soundtrack/README.md](soundtrack/README.md).

## Workspace isolation

The sibling `audioif` repository is consumed read-only - no build or
formatting command here writes into it. The engine builder likewise leaves
the sibling MicroPython checkout unchanged: it uses the existing `cmods`
transactional overlay, and removes the temporary `vstaudio` module link on
exit, including after a failed build.

## Known limitations

- No custom editor and no host-visible diagnostic string. The generic
  editor shows only the ready and error parameters; the bounded diagnostic
  text is available through the transport API.
- State embeds one source file, not a dependency bundle. Imports must
  resolve in the sidecar's own MicroPython environment.
- `MPVST_SCRIPT_PATH` is process-wide, so two developer-file instances
  cannot follow different scripts - they re-read it on restart and on
  save. Projects that need per-instance scripts embed them in state
  instead, which `reaper/matrix/build_effect_project.py` demonstrates by
  synthesizing the chunks directly.
- The 2,080 hidden MIDI parameters are standards-compliant and
  validator-clean but unprofiled for scan and project-load overhead in
  real DAWs.
- Installer packaging, code signing, and uninstall flows beyond copying
  and removing the bundle have not been built.
- The Linux REAPER used for testing runs under WSLg with no audio device.
  Real-time playback on Linux hardware has not been exercised.
- REAPER is the only DAW tested.

## Deferred

- An LVGL editor and its shared framebuffer/input protocol.
- Effect extras: a wet/dry mix parameter and sidechain input buses.
- Float64 host processing and a native floating-point audioif graph.
- macOS bundles, signing, notarisation, and universal binaries.
- Coverage-guided fuzzing. `tests/fuzz` exposes libFuzzer entry points;
  configure with `-DMPVST_ENABLE_LIBFUZZER=ON` on a clang toolchain and
  keep interesting inputs in `tests/fuzz/corpus`. The portable driver runs
  on every toolchain as an ordinary test regardless.
