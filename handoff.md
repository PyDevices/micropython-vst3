# MicroPython VST3 handoff

Updated: 2026-08-25

All eight phases are complete. The instrument runs in REAPER on Windows and on
Linux, and the same script and project state render byte-identical PCM on both
platforms.

## Repository and constraints

- Repository: `/home/brad/gh/pydevices/micropython-vst3`
- Canonical workspace: `/home/brad/gh/pydevices`
- Treat sibling `/home/brad/gh/pydevices/audioif` as read-only. Consume its
  public headers and build interface only.
- Do not make persistent changes in
  `/home/brad/gh/pydevices/cmods/micropython`. The engine build creates a
  temporary `/home/brad/gh/pydevices/cmods/vstaudio` symlink and removes it on
  exit. Confirm it is absent after any engine build.
- The only expected MicroPython change is the independently existing
  `ports/esp32/lockfiles/dependencies.lock.esp32p4` modification.

## Product decisions

- Instrument only: one 16-channel event input, no audio input, stereo float32
  output.
- One unrestricted, headless MicroPython sidecar process per active instance.
- The DAW generic parameter editor; LVGL is not required.
- Scripts retain full desktop MicroPython capabilities. This is process
  isolation for stability, not a security sandbox.

## Where things stand

`PLAN.md` is the source of truth and records every phase as complete.

- Steinberg validator: 94/94 on Windows and Linux (both classes).
- Automated tests: 14 of 14 on Linux and on Windows.
- REAPER matrix: 17 of 17 steps and every PCM check, on both platforms,
  including an instrument-into-effect chain rendered from embedded state
  and a latency-matched effect bypass. Evidence in `docs/evidence/`.
- Cross-platform parity: identical SHA-256 over the reference render.

## Implemented behaviour

- Two plug-in classes ship in one bundle: the **MicroPython Instrument**
  and the **MicroPython Effect**, which adds a stereo audio-input bus.
  An effect script reads the host audio through `vstaudio.input()` - an
  audiosample source any audioif chain can consume - and its bypass is a
  latency-matched pass-through. `examples/fx_space.py` shows the shape.
- `lib/effects` is a shared library of forty-plus effect classes
  (dynamics, EQ, reverb, delay, modulation, drive, pitch/stereo) staged
  into the bundle and importable from any script. It rides on two engine
  DSP nodes - `vstaudio.Dynamics` (envelope-follower gain computer) and
  `vstaudio.Splitter` (parallel branches) - and compensates for two
  oracle-faithful CircuitPython biquad quirks: filters in a stereo
  audiofilters.Filter center at twice the asked frequency (the library
  halves what it requests), and peaking EQ is broken upstream (bells are
  built from notch and band-pass sections). `tools/test-effects-lib.py`
  runs every class through the real sidecar as `mpvst_effects_library`.
- 20 visible parameters (bypass, reload, ready/error status, 16 macros) plus
  2,080 hidden 16-channel MIDI mapping parameters, 2,100 total. REAPER reports
  2,103 because it appends its own three.
- All 128 CCs, pitch bend, channel and poly pressure, note velocity and tuning,
  and note-on/off reach Python at absolute delayed sample positions.
- Macro IDs are permanently 100-115 and arrive as `vstaudio.EVENT_PARAMETER`
  with a zero-based index in `data0`. Optional labels:
  `# mpvst-macro-labels: Gain | Tone | Attack | Release`.
- Current macro values are replayed to the script whenever a script loads,
  reloads, or is restored from project state, so an automated or reopened
  instance sounds the way it was saved.
- An instance started from `MPVST_SCRIPT_PATH` follows that file: toggling
  `Reload Script` re-reads what is on disk, and saving embeds the current
  source. A project restored from state keeps using its embedded snapshot and
  ignores later edits to the original file.
- Reload is a rising-edge action and is only observed while the plug-in is
  processing. Output uses a 128-sample fade-out, a 640-sample hold at the
  current 128-frame/512-latency setup, then a 128-sample fade-in.
- Host transport position, tempo, and time signature reach the work slot.
  Locates, loop wraps, and play-state changes arrive as
  `vstaudio.EVENT_TRANSPORT`; `vstaudio.transport()` returns
  `(playing, seconds, bpm, numerator, denominator)`.
- `SidecarTransport::telemetry()` reports queue depth, render time, underruns,
  event drops, restarts, error code, and the last exit reason, with peaks
  tracked from the audio thread. `-1000` as an exit code means the supervisor
  killed an engine that had hung.
- `Engine Error`: 0 clear, 1 script load or reload failure, 2 render failure.
- Offline mode may wait up to five seconds for the exact output slot; the
  real-time path stays non-blocking.
- `MPVST_HEAP_BYTES` caps the MicroPython heap per instance.

## Building and testing

Linux:

```bash
cmake --build .build-linux -j 4
ctest --test-dir .build-linux --output-on-failure
```

Windows, from WSL:

```bash
./.deps/cmake-4.4.2-windows-x86_64/bin/cmake.exe \
  --build 'C:\Users\bradb\AppData\Local\Temp\micropython-vst3-build' \
  --config Release --parallel 4

./.deps/cmake-4.4.2-windows-x86_64/bin/ctest.exe \
  --test-dir 'C:\Users\bradb\AppData\Local\Temp\micropython-vst3-build' \
  -C Release --output-on-failure
```

Rebuild a MicroPython sidecar only when `usermods/vstaudio` changes, then
rebuild the plug-in so the engine is restaged:

```bash
./tools/build-micropython-engine.sh --port windows
./tools/build-micropython-engine.sh --port unix
```

The Linux CMake cache remembers the engine path. After switching engines,
reconfigure with `cmake -S . -B .build-linux -U MPVST_MICROPYTHON_ENGINE`.

## DAW matrix

REAPER is driven headlessly by a startup ReaScript. Install the packaged
plug-in first, because the matrix exercises the installed bundle:

```bash
./reaper/matrix/run-reaper-matrix.sh --platform windows
./reaper/matrix/run-reaper-matrix.sh --platform linux
```

REAPER is installed at `C:\Users\bradb\REAPER` and `~/opt/REAPER`; its resource
paths are `%APPDATA%\REAPER` and `~/.config/REAPER`. The matrix overwrites
`Scripts/__startup.lua` in the resource path, so remove that file before using
REAPER interactively.

A host with no live audio device only processes during a render, so the matrix
forces a short render before reading any status parameter.

## Cross-platform parity

```bash
./tools/check-cross-platform-parity.sh
```

Both smoke hosts render a fixed score through the real MicroPython sidecar and
the raw float32 PCM is compared. The current result is an identical SHA-256, so
the platforms agree exactly rather than within a tolerance.

## Packaging

```bash
./tools/package-windows.sh
./tools/package-linux.sh
```

Artifacts land in `dist/` with SHA-256 sidecars. `dist/` is ignored, as are
`.deps/` and the build directories.

## Recommended next work

1. A second host on each platform. REAPER is the only DAW currently tested, and
   the 2,080 hidden MIDI parameters deserve scan and project-load profiling in a
   host that handles parameters differently.
2. Coverage-guided fuzzing. `tests/fuzz` already exposes libFuzzer entry points;
   configure with `-DMPVST_ENABLE_LIBFUZZER=ON` on a clang toolchain and keep
   any interesting inputs in `tests/fuzz/corpus`.
3. Multi-hour soaks. `mpvst_soak_tests <engine> <seconds>` runs the scenario for
   any duration; the suite only runs the five-second form.
4. macOS bundles, signing, and notarisation, still deferred.
5. The deferred extensions: an LVGL editor, an audio-input effect component,
   float64 processing.

## Known limitations and cautions

- No custom editor, and no host-visible detailed diagnostic string. The generic
  editor shows only the ready and error parameters; the bounded diagnostic text
  is available through the transport API.
- State embeds one source file, not a dependency bundle. Imports must resolve in
  the sidecar's own MicroPython environment.
- The 2,080 hidden MIDI parameters are standards-compliant and validator-clean
  but unprofiled for scan and project-load overhead in real DAWs.
- Installer packaging, code signing, and uninstall flows beyond copying and
  removing the bundle have not been built.
- The Linux REAPER used for testing runs under WSLg without an audio device.
  Real-time playback on Linux hardware has not been exercised.
