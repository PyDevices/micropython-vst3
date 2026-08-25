# MicroPython VST3 handoff

Updated: 2026-08-25

## Repository and constraints

- Repository: `/home/brad/gh/pydevices/micropython-vst3`
- Canonical workspace: `/home/brad/gh/pydevices`
- The repository has been initialized but has no initial commit; every project
  file is currently untracked. Review and create the initial commit before
  beginning work that depends on a clean Git baseline.
- Treat sibling `/home/brad/gh/pydevices/audioif` as read-only. Another agent is
  porting it to CPython. Consume its public headers/build interface only.
- Do not make persistent changes in
  `/home/brad/gh/pydevices/cmods/micropython`. The engine wrapper creates a
  temporary `/home/brad/gh/pydevices/cmods/vstaudio` symlink and removes it on
  exit. The symlink is currently absent.
- Current MicroPython status contains only the independently existing
  `ports/esp32/lockfiles/dependencies.lock.esp32p4` modification. Current
  `audioif` changes are concurrent work and do not belong to this repository.

## Product decisions

- Windows VST3 first; Linux product work follows the Windows instrument.
- Instrument only: one 16-channel event input, no audio input, stereo float32
  output.
- One unrestricted, headless MicroPython sidecar process per active instance.
- Use the DAW generic parameter editor; LVGL is not required.
- Scripts retain full desktop MicroPython capabilities. This is not a security
  sandbox.

## Current phase status

- Phases 0–2: complete (architecture, VST shell, realtime sidecar transport).
- Phase 3: functionally complete under automated hosts; still marked in
  progress because a physical DAW play test has not occurred.
- Phase 4: complete (sample-exact MIDI/CC/pressure/pitch and variable blocks).
- Phase 5: complete (macros, labels, bounded embedded v2 state, legacy v1,
  deleted-source restore into a fresh sidecar).
- Phase 6: in progress. Workflow, examples, status parameters, reload fades,
  and packaging are complete. The real Windows DAW matrix is the blocker.
- Phase 7: in progress. Offline faster-than-realtime processing and deterministic
  malformed state/protocol corpora pass. Soaks, telemetry, discontinuities,
  coverage-guided fuzzing, and constrained heaps remain.
- Phase 8: pending as a product phase, although Linux builds and validation are
  continuously green.

`PLAN.md` is the source of truth and must be updated as work completes.

## Implemented behavior

- Steinberg validator passes 47/47 on Windows and Linux.
- VST exposes 20 visible parameters: bypass, reload, ready/error status, and 16
  stable macros. It also exposes 2,080 hidden 16-channel MIDI mapping
  parameters, for 2,100 total.
- All 128 CCs, pitch bend, channel/poly pressure, note velocity/tuning, and
  note-on/off reach Python at absolute delayed sample positions.
- Macro IDs are permanently 100–115. Every automation point reaches Python as
  `vstaudio.EVENT_PARAMETER` (`data0` is zero-based macro index).
- Optional script label syntax:

  `# mpvst-macro-labels: Gain | Tone | Attack | Release`

- State v2 preserves the v1 bypass/macro prefix and appends pipeline depth and
  up to 1 MiB of script source. Restored source is materialized to an
  instance-private temporary file and removed on stop.
- Reload is a rising-edge action. Hosts must toggle `Reload Script` off and on
  for each reload. Output uses 128 samples out, a 640-sample hold at the current
  128-frame/512-latency setup, then 128 samples in.
- `Engine Error`: 0 is clear, 1 is script load/reload failure, 2 is render
  failure. Detailed bounded text is available from the transport diagnostic
  API; the generic host control presents the integer code.
- Offline mode may wait up to five seconds for the exact sidecar output slot;
  the realtime path remains non-blocking.

## Test evidence

Latest results:

- Windows: 7/7 CTest cases.
- Linux: 5/5 CTest cases.
- Steinberg validator: 47/47 on each platform.
- Exact hooks include note-on sample 576, pitch bend sample 768, Macro 01 sample
  1041, note-off sample 1312, release tail ending at 3967, variable block
  boundaries, deleted-source state restore, and exact reload fade samples.
- Offline no-sleep rendering is silent through sample 255 and exactly 0.125
  from sample 256.

Linux verification:

```bash
cmake --build build-linux -j 4
ctest --test-dir build-linux --output-on-failure
```

Windows verification from WSL:

```bash
./.deps/cmake-4.4.2-windows-x86_64/bin/cmake.exe \
  --build 'C:\Users\bradb\AppData\Local\Temp\micropython-vst3-build' \
  --config Release --parallel 4

./.deps/cmake-4.4.2-windows-x86_64/bin/ctest.exe \
  --test-dir 'C:\Users\bradb\AppData\Local\Temp\micropython-vst3-build' \
  -C Release --output-on-failure
```

Explicit MicroPython hook:

```bash
'/mnt/c/Users/bradb/AppData/Local/Temp/micropython-vst3-build/tools/smoke_host/Release/mpvst_smoke_host.exe' \
  'C:\Users\bradb\AppData\Local\Temp\micropython-vst3-build\VST3\Release\MicroPythonVST3.vst3' \
  --expect-micropython
```

The source-controlled `tools/smoke_host` supplies deterministic hooks around
Steinberg's public hosting classes. The SDK GUI Plug-in Test Host itself was not
patched; it has no practical deterministic automation/unload surface.

## Builds and artifacts

- Pinned SDK: `.deps/vst3sdk` (ignored).
- Bundled engine: `.deps/engine/micropython-vst-engine.exe` (ignored).
- Linux build: `build-linux`.
- Windows build:
  `/mnt/c/Users/bradb/AppData/Local/Temp/micropython-vst3-build`.
- Windows VST bundle:
  `/mnt/c/Users/bradb/AppData/Local/Temp/micropython-vst3-build/VST3/Release/MicroPythonVST3.vst3`.
- Package command: `./tools/package-windows.sh`.
- Latest ignored artifact:
  `dist/MicroPythonVST3-0.1.0-windows-x86_64.zip`.
- Latest ZIP SHA-256:
  `f197fc19ce23315e8ccb1bd30c619b1c528b8b8a18085e709ab96b65a129e70f`.

Rebuild the MicroPython engine only when `usermods/vstaudio` changes:

```bash
./tools/build-micropython-engine.sh
```

Then rebuild the Windows VST so the engine and Python assets are restaged.

## Recommended next work

1. Install the packaged VST in REAPER on Windows and execute the Phase 6 matrix:
   scan, instantiate, MIDI play, macro automation, save/reopen, script reload,
   malformed-script recovery, multiple instances, and uninstall/rescan.
2. Record DAW/version/audio-driver/block-size results in `PLAN.md`. Add at least
   one second host after REAPER before marking Phase 6 complete.
3. Add Phase 7 telemetry snapshots outside the realtime callback: queue depth,
   render-time high-water mark, underruns, drops, restarts, and crash reason.
4. Add transport-discontinuity/reset semantics and tests.
5. Add long realtime/offline/multi-instance soaks and coverage-guided fuzz
   harnesses for state and shared-memory validation.

## Known limitations and cautions

- There is no custom editor and no host-visible detailed diagnostic string;
  only ready/error code parameters are visible in the generic editor.
- State embeds one source file, not an arbitrary multi-file dependency bundle.
  Imports must still be available through the desktop MicroPython environment.
- The 2,080 hidden MIDI parameters are standards-compliant and validator-clean,
  but should be profiled in real DAWs for scan/state overhead.
- Physical DAW behavior, installer paths, signing, and uninstallation have not
  yet been verified on the available machine.
- Do not claim Phase 3 or Phase 6 complete until the physical DAW evidence is
  recorded.
