# Working on MPVST itself

Building the plug-in from source, running its gates, and cutting a release.
To write instruments or effects *for* MPVST - which needs none of this - see
[writing-scripts.md](writing-scripts.md).

## Repository layout

| | |
|---|---|
| `src/` | the C++ that builds the plug-in: `plugin/` (VST3 classes), `protocol/` (the shared-memory wire format), `runtime/` (shared memory and child processes) |
| `usermods/` | the MicroPython C modules the engine binds to: `vstaudio/` (the audio API scripts use) and `vstui/` (the editor's framebuffer, input and edit rings) |
| `lib/` | everything staged into the bundle beside the engine: the bootstrap, the adapters, `mpvst_scan_plugins.py`, the default instrument, and the editor's Python half (`mpvst_editor.py`, `mpvst_board_config.py`, `mpvst_panel/`) |
| `tools/` | developer tooling - `piece.py` and `render_preview.py` for compositions, the `harness.py` CPython sidecar stand-in, and the library test sweeps |
| `tests/` | the ctest suite and `smoke_host/`, a minimal VST3 host that loads the bundle with no DAW |
| `scripts/` | build, packaging and setup automation |
| `installer/` | what a user runs rather than builds: `windows.nsi` (the NSIS installer, cross-built from Linux) and `install-linux.sh`, which ships inside the tarball as `install.sh` |
| `reaper/` + `reaper.sh` | everything that drives REAPER. Deletable as a unit; nothing outside it depends on it |
| `soundtrack/` | example pieces, each with its own `composition.py` |

The architecture is written down in
[docs/architecture/phase-0.md](architecture/phase-0.md) (the system
boundary and what each process owns) and
[docs/architecture/ipc-v1.md](architecture/ipc-v1.md) (the
shared-memory protocol rules), with
[docs/architecture/ui-v1.md](architecture/ui-v1.md) covering the
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
  [`tools/README.md`](../tools/README.md)) for the instrument/effect tests
  and preview renders, and `flake8` for the `mpvst_lint` ctest.
  `scripts/bootstrap.sh` creates a repo-local `.venv` with these.
- The Steinberg VST3 SDK, fetched by `scripts/fetch-vst3-sdk.sh` into the
  gitignored `.deps/vst3sdk` (see [the licence note](../README.md#license) for its terms).
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

See [scripts/README.md](../scripts/README.md) for what it does and how to run
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

## Building a release

`VERSION` at the repository root is the single
source of truth - CMake and both packaging scripts read it, and editing it
re-runs CMake's configure step, so a binary and the archive around it
cannot disagree about which version they are.

```bash
./scripts/fetch-nsis.sh          # once, for the Windows installer
./scripts/package-linux.sh
./scripts/package-windows.sh
```

Each produces a versioned archive plus a SHA-256 sidecar under the ignored
`dist/`, after verifying the bundle carries its engine and bootstrap;
`package-windows.sh` also builds the installer, from the same staging tree
the archive is made from, so the two cannot ship different bytes. The
installer is built by NSIS, which cross-builds a Windows installer from
Linux - `fetch-nsis.sh` unpacks it into `.deps/` rather than installing it
on the machine, so it needs no root and removing `.deps` removes it.
See [docs/windows/README.md](windows/README.md) and
[docs/linux/README.md](linux/README.md) for the development
install paths and the desktop-script security model.

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
[reaper/README.md](../reaper/README.md) and
[soundtrack/README.md](../soundtrack/README.md).

## Workspace isolation

The sibling `audioif` and `audiocomponents` repositories are consumed
read-only - no build or formatting command here writes into either. The
engine builder likewise leaves
the sibling MicroPython checkout unchanged: it uses the build workspace's
existing transactional overlay, and removes the temporary `vstaudio` module
link on exit, including after a failed build.

## Deferred

- Effect extras: a wet/dry mix parameter and sidechain input buses.
- Float64 host processing and a native floating-point audioif graph.
- macOS bundles, signing, notarisation, and universal binaries.
- Coverage-guided fuzzing. `tests/fuzz` exposes libFuzzer entry points;
  configure with `-DMPVST_ENABLE_LIBFUZZER=ON` on a clang toolchain and
  keep interesting inputs in `tests/fuzz/corpus`. The portable driver runs
  on every toolchain as an ordinary test regardless.
