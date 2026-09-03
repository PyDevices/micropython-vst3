# MicroPython VST3

Programmable VST3 instruments and audio effects backed by dedicated
MicroPython engine processes. One bundle ships a whole library: every
`audioinstruments` module and every `audioeffects` class appears in the
DAW's browser under its own name and category - **TR-808** under
Instrument|Drum, **Tape Delay** under Fx|Delay - alongside two generic
**MicroPython Script Host** classes that run any script you point them at.

The list is not compiled in. `scan_plugins.py`, run by the engine itself,
reads what each library module declares about itself and writes the
`moduleinfo.json` the plug-in loads at startup - the same file a host reads
to enumerate classes without loading the binary. Adding an instrument is
writing a script and re-scanning; there is no build step and no compiler
involved.

The VST audio callback stays native and real-time safe. Python, garbage
collection, filesystem access, and engine lifecycle work all happen in a
separate sidecar process - one per active plug-in instance - so a script
that loops forever or exhausts memory takes down its own sidecar and gets
restarted, rather than taking the DAW with it.

Windows and Linux builds both ship, each with an LVGL editor of its own -
a generic panel built from what the instance already declares, painted by
the engine into shared memory and blitted by a native view. The host's
generic parameter editor still reaches everything it did. The same script
and project state render byte-identical PCM on both platforms, with or
without an editor attached.

## Repository layout

| | |
|---|---|
| `src/` | the C++ that builds the plug-in: `plugin/` (VST3 classes), `protocol/` (the shared-memory wire format), `runtime/` (shared memory and child processes) |
| `usermods/` | the MicroPython C modules the engine binds to: `vstaudio/` (the audio API scripts use) and `vstui/` (the editor's framebuffer, input and edit rings) |
| `lib/` | everything staged into the bundle beside the engine: the bootstrap, the adapters, `scan_plugins.py`, the default instrument, and the editor's Python half (`vst_editor.py`, `vst_board_config.py`, `vst_panel/`) |
| `tools/` | developer tooling - `piece.py` and `render_preview.py` for compositions, the `harness.py` CPython sidecar stand-in, and the library test sweeps |
| `tests/` | the ctest suite and `smoke_host/`, a minimal VST3 host that loads the bundle with no DAW |
| `scripts/` | build, packaging and setup automation |
| `reaper/` + `reaper.sh` | everything that drives REAPER. Deletable as a unit; nothing outside it depends on it |
| `soundtrack/` | example pieces, each with its own `composition.py` |

The architecture is written down in
[docs/architecture/phase-0.md](docs/architecture/phase-0.md) (the system
boundary and what each process owns) and
[docs/architecture/ipc-v1.md](docs/architecture/ipc-v1.md) (the
shared-memory protocol rules), with
[docs/architecture/ui-v1.md](docs/architecture/ui-v1.md) covering the
editor. `ipc-v1.md` and `ui-v1.md` describe the shipping design;
`phase-0.md` is historical - the Windows-only, no-editor design accepted
before Linux shipped and before the LVGL editor existed - kept for its
still-valid process/thread/state reasoning, not as a description of
what ships today. The canonical structure sizes and offsets live in
`src/protocol/include/mpvst/protocol.h` and `src/protocol/include/mpvst/ui.h`.

## Prerequisites

- A C++17 toolchain: MSVC on Windows, GCC or Clang on Linux.
- CMake 3.25+ and Ninja (`cmake -S . -B .build-linux -G Ninja` is the
  documented invocation below).
- On Linux, X11 development headers (`src/plugin/CMakeLists.txt` runs
  `find_package(X11 REQUIRED)` for the editor's native window) - e.g.
  `libx11-dev` on Debian/Ubuntu.
- Python 3.x for `tools/`, `scripts/`, and the `ctest`-registered Python
  suites; `numpy`, `pydevices-audioif`, `pydevices-audioinstruments` and
  `pydevices-audioeffects` (all from TestPyPI - see
  [`tools/README.md`](tools/README.md)) for the instrument/effect tests
  and preview renders, and `flake8` for the `mpvst_lint` ctest.
  `scripts/bootstrap.sh` creates a repo-local `.venv` with these.
- The Steinberg VST3 SDK, fetched by `scripts/fetch-vst3-sdk.sh` into the
  gitignored `.deps/vst3sdk` (see [License](#license) for its terms).
- The sibling `audioif` checkout and the org's optional build-aggregator
  workspace the MicroPython engine build depends on, and the sibling
  `audiocomponents` checkout whose `audioinstruments` and `audioeffects`
  packages the plug-in build stages into the bundle - all three fetched
  by `scripts/fetch-sibling-repos.sh`.
- On WSL, building the Windows engine/plugin needs a reachable Windows
  host: `scripts/build-micropython-engine.sh --port windows` and
  `scripts/install-plugin-windows.sh` both shell out to `powershell.exe`,
  and `scripts/bootstrap.sh` skips the Windows engine port automatically
  when `/mnt/c/Users` or `powershell.exe` is not available.

## Getting started

A fresh clone has none of the external dependencies this repo needs - the
VST3 SDK, the sibling `audioif` and build-aggregator repos the engine build
depends on, the sibling `audiocomponents` repo the plug-in build stages its
instruments and effects from, or REAPER for the DAW-driven tooling. `.deps/`
and those sibling checkouts are all gitignored. One command sets all of it
up:

```bash
./scripts/bootstrap.sh
```

See [scripts/README.md](scripts/README.md) for what it does and how to run
each step individually.

## Building and testing

The MicroPython sidecar is built separately from the plug-in, and only
needs rebuilding when `usermods/vstaudio`, `usermods/vstui`, or the
sibling audioif checkout's C sources change. It lands in the ignored
`.deps/engine/`, and the plug-in build stages it into the bundle. CMake
never detects a stale engine on its own - it only re-stages the file at
`MPVST_MICROPYTHON_ENGINE` if that path's mtime changes, so after any of
those three changes you must rerun the build script yourself before
reconfiguring/rebuilding the plug-in:

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
`cmake -S . -B .build-linux -U MPVST_MICROPYTHON_ENGINE`. It remembers
`MPVST_AUDIOIF_LIB` the same way - the name the components path had while
the packages lived in audioif, still honoured for one release with a
warning - so a build directory configured before the move keeps staging
from audioif until you reconfigure with `-U MPVST_AUDIOIF_LIB`.

Steinberg hosting tools are off by default so a plug-in-only build does
not pull in editor-host dependencies. Enable them in a dedicated validator
build with `-DSMTG_ENABLE_VST3_HOSTING_EXAMPLES=ON`. `VST3_SDK_ROOT` may
point at an existing SDK checkout instead of the fetched one.

## Writing a script

A script registers a callback and an output. For a cataloged audioif
component, the provider metadata is mandatory; a consumer such as this
plug-in remains tolerant of missing optional fields.
The bundled `lib/default_instrument.py` is the working reference - it
tracks voices by VST note ID, maps velocity to amplitude, applies pressure
and pitch bend, and uses an explicit 50 ms release.

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

`lib/mpvst_adapter.py` is the seam between the two. `vstaudio` speaks the
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

Nothing is published yet: `VERSION` currently holds `0.0.1` as a
placeholder, and every archive `package-linux.sh`/`package-windows.sh`
produce is built and distributed locally, by hand. A real release channel
is expected to arrive with the planned post-program rename/refactor, not
before.

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

This repository deliberately has no hosted CI. The 14-test `ctest` suite
(lint included) is the gate, and it is run locally - by a developer before
pushing, or by `scripts/bootstrap.sh` as its final verification step.
Hosted CI is planned to arrive with the post-program refactor, not before.

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

The sibling `audioif` and `audiocomponents` repositories are consumed
read-only - no build or formatting command here writes into either. The
engine builder likewise leaves
the sibling MicroPython checkout unchanged: it uses the build workspace's
existing transactional overlay, and removes the temporary `vstaudio` module
link on exit, including after a failed build.

## Security: what the shipped engine cannot do

Compositions, instruments, and racks are Python code, and some of it —
`scan_plugins.py` reading module declarations — runs at plugin-scan time,
before you consciously play anything. Because people share pieces, the
shipped sidecar engine is a deliberately narrow interpreter: **no sockets,
no SSL, and no FFI** (the windows build skips the networking and FFI
overlays; the Linux build compiles them out — see
`scripts/build-micropython-engine.sh` and the `vst3-engine` profile in
`micropython-pydevices`). A hostile script therefore has no exfiltration
channel and no route to arbitrary native code; its blast radius is the
file I/O the engine legitimately needs for its own library.

This is a safe default, not a sandbox. You can rebuild the engine with
networking or FFI enabled and drop it into the bundle — at that point the
capability was your informed choice as the builder, which is exactly the
line this default draws: nothing a downloaded piece can switch on by
itself. Do not redistribute bundles containing a widened engine without
saying so.

## Known limitations

- No host-visible diagnostic string. Both editors show only the ready and
  error parameters; the bounded diagnostic text is available through the
  transport API.
- The editor is one generic panel. Per-script panels, a shared knob widget,
  meters, and resizable or zoomable editors are all deferred.
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

- Effect extras: a wet/dry mix parameter and sidechain input buses.
- Float64 host processing and a native floating-point audioif graph.
- macOS bundles, signing, notarisation, and universal binaries.
- Coverage-guided fuzzing. `tests/fuzz` exposes libFuzzer entry points;
  configure with `-DMPVST_ENABLE_LIBFUZZER=ON` on a clang toolchain and
  keep interesting inputs in `tests/fuzz/corpus`. The portable driver runs
  on every toolchain as an ordinary test regardless.

## License

MIT, in [LICENSE](LICENSE) — the same terms as the rest of PyDevices.

That covers this repository's own source. The Steinberg VST3 SDK is **not**
vendored here: `scripts/fetch-vst3-sdk.sh` clones it into `.deps/`, which is
ignored. It carries its own dual license (GPLv3 or a proprietary Steinberg
agreement), and anyone distributing a **built** plug-in binary has to satisfy
one of those two for the SDK it links. Building from source for your own use
does not change anything here.
