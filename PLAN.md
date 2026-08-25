# MicroPython VST3 implementation plan

Last updated: 2026-08-25

This file is the source of truth for implementation status. A phase is marked
complete only when its exit criteria and evidence are recorded here.

## Locked product decisions

- Windows VST3 was the first target; the Linux port now ships alongside it.
- Each plug-in instance owns one headless MicroPython sidecar process.
- The first product is an instrument only; live audio-input effects are later.
- Scripts retain the full capabilities of the desktop MicroPython build.
- The MVP uses the DAW's generic parameter editor; LVGL is not required.
- The sibling `audioif` repository is read-only while another agent works there.

## Status summary

| Phase | Status | Evidence |
|---|---|---|
| 0. Architecture contract | Complete | `docs/architecture/phase-0.md` and `docs/architecture/ipc-v1.md` |
| 1. Silent VST3 instrument shell | Complete | Validator 47/47 on Windows and Linux; Test Host scan/instantiate; CLI state/lifecycle/unload hooks pass |
| 2. Real-time sidecar transport | Complete | MSVC/GCC protocol tests, eight-instance isolation, crash/stall restart, VST lifecycle, and exact 512-sample latency pass |
| 3. Headless MicroPython engine | Complete | Full-capability bundled Python/synthio render and in-instance syntax/runtime/reload recovery pass; REAPER plays the instrument on Windows and Linux |
| 4. MIDI and sample timing | Complete | 16-channel CC/pitch/pressure mapping validates; exact delayed note, bend, and variable-block boundary PCM checks pass |
| 5. Automation and project state | Complete | Stable labeled macros, v1-compatible bounded v2 state, deleted-source restore, fresh sidecar render, and exact sample 1041 hook pass |
| 6. Usable Windows instrument release | Complete | The REAPER matrix passes every step and every PCM check on Windows; `docs/evidence/reaper-matrix-report.txt` |
| 7. Offline rendering and hardening | Complete | Telemetry, transport discontinuity, soak, and fuzz harnesses pass; the soak and fuzzer each found and fixed a defect |
| 8. Linux port | Complete | Unix sidecar, Linux bundle and archive, REAPER on Linux, and byte-identical cross-platform PCM |

## Phase 0 — Architecture contract

Status: **Complete**

Deliverables:

- Define process, thread, sidecar, IPC, latency, state, and failure boundaries.
- Fix the initial audio shape at one event input and stereo float32 output.
- Keep all Python and blocking work outside the VST audio callback.
- Establish MSVC for the VST shell and the existing MicroPython toolchain for
  the sidecar, joined only by a versioned shared-memory ABI.
- Reserve protocol evolution for optional UI traffic without implementing UI.

Exit criteria:

- Architecture decisions cover lifecycle, real-time rules, pipeline timing,
  multiple instances, underruns, crashes, state, and security posture.

Evidence:

- `docs/architecture/phase-0.md`
- `docs/architecture/ipc-v1.md`

## Phase 1 — Silent VST3 instrument shell

Status: **Complete**

Deliverables:

- Build a VST3 instrument with one event input and one stereo output.
- Support float32 processing and reject unsupported sample sizes.
- Expose bypass, script-reload, and 16 stable automatable macro parameters.
- Produce deterministic silence without allocation or locking in `process()`.
- Persist processor parameter state with an explicit state version.
- Pin the official VST3 SDK and add reproducible build instructions.

Exit criteria:

- Source builds with MSVC for Windows.
- Steinberg validator accepts the bundle.
- A DAW can scan, instantiate, save, restore, deactivate, and unload it.

Evidence recorded 2026-08-25:

- Windows Release build succeeded with MSVC 19.51.36256.0 using the Visual
  Studio 18 2026 generator.
- Steinberg's Windows validator passed all 47 plug-in tests with zero failures.
- A native Linux Release build also passed all 47 validator tests with zero
  failures, providing an additional ABI and lifecycle check.
- The initial bundle reported one stereo audio output, one event input, no audio
  input, 18 user-facing parameters, and the Instrument/Synth category as
  intended. Phase 4 later added 2,080 hidden MIDI mapping parameters while
  retaining those 18 user-facing controls; Phase 6 added two read-only status
  controls, for 20 visible and 2,100 total parameters.
- REAPER 7.79 later scanned and instantiated the same bundle on Windows and on
  Linux; see the Phase 6 and Phase 8 evidence.
- Steinberg VST3PluginTestHost 3.11.0, from the matching full SDK package,
  scanned the explicit Release folder, instantiated the instrument, opened its
  generic editor, and loaded the expected `MicroPythonVST3.vst3` module.
- The distributable Test Host has no source or automation API. Automated close
  messages did not exit all of its custom GUI windows, so that process was
  forcibly terminated during cleanup rather than counted as an unload pass.
- A source-controlled CLI host built from Steinberg's public hosting classes now
  provides explicit hooks for module load, class scan, fresh-instance component
  state round-trip, setup/activate/process/deactivate/terminate, and module
  unload. Every hook passes under GCC and MSVC, covering the Test Host's missing
  deterministic control surface.

## Phase 2 — Real-time sidecar transport

Status: **Complete**

Deliverables:

- Implement versioned shared-memory audio, event, command, status, and error
  regions with fixed-width fields and compile-time layout checks.
- Start the sidecar during activation, never from `process()`.
- Prove the transport with a native sine-wave sidecar before MicroPython.
- Pipeline block `t` into output at `t + L`, initially with four maximum host
  blocks of reported latency.
- Return silence on underrun and expose counters outside the audio callback.
- Detect sidecar exit and schedule bounded restart outside the audio callback.

Exit criteria:

- Stable output through repeated activation and sample-rate/block-size changes.
- Eight simultaneous instances operate independently.
- Deliberately killed or stalled sidecars never block the audio callback.

Evidence recorded 2026-08-25:

- Protocol v1 now has fixed-width, C-compatible header, status, command, event,
  work-slot, and output-slot records with exact size and offset assertions.
- GCC and MSVC pass the same layout, validation, corruption, ring-full,
  wraparound, planar-output, and stale-generation tests.
- Native engine executables built with GCC and MSVC each open a named mapping
  as a real child process, render a 440 Hz sine through 64 variable-size blocks
  with repeated ring wraparound, and perform a bounded cooperative shutdown.
- Plug-in activation starts one child process, the bounded audio callback moves
  planar float32 blocks without allocating or locking, and deactivation performs
  a bounded cooperative shutdown.
- The source-controlled Windows CLI host proves four maximum-blocks of initial
  silence followed by output at the reported fixed 512-sample latency.
- A supervisor thread outside the audio callback detects process exit or 500 ms
  of stalled work, quiesces callbacks using atomics, advances the protocol
  generation, and performs at most three consecutive restart attempts. The
  callback emits silence and continues advancing host sample time meanwhile.
- The same transport stress test under MSVC and GCC runs eight independent
  mappings and engine processes, then forces a child exit and a non-responsive
  child. Audio calls remain below the test's 20 ms upper bound and rendering
  resumes after exactly one automatic restart in each failure scenario.

## Phase 3 — Headless MicroPython engine

Status: **Complete**

Deliverables:

- Add `micropython-vst-engine.exe` with no REPL or device-audio ownership.
- Preserve full desktop MicroPython capabilities.
- Add a native `vstaudio` user module owned by this repository.
- Let scripts register an audiosample graph as the instrument output.
- Pull the native audiosample protocol without the allocating Python debug
  wrapper, then convert interleaved int16 PCM to planar float32.
- Catch Python exceptions and return structured engine errors.

Constraint:

- Consume `audioif` through public headers/build interfaces only. Do not edit
  the sibling `audioif` repository.

Exit criteria:

- A Python script constructs a `synthio.Synthesizer` and plays from a DAW.
- Syntax/runtime errors and script reloads recover without reloading the VST.

Evidence recorded 2026-08-25:

- This repository owns a `vstaudio` MicroPython user module, bootstrap, default
  instrument, and reproducible Windows engine build wrapper. The wrapper
  consumes `audioif` read-only and leaves both the `audioif` repository and the
  MicroPython source checkout unchanged.
- The dedicated `micropython-vst-engine.exe` imports `vstaudio`, `synthio`, FFI,
  sockets, and TLS, demonstrating the requested full desktop capabilities.
- The VST bundle stages that engine plus its bootstrap and default Python
  instrument next to the native module and prefers it over the native proof
  engine.
- A full VST lifecycle smoke run renders nine zero crossings in the audible
  window: the expected 220 Hz Python `synthio.Synthesizer`, distinct from the
  native fallback's 440 Hz. It also passes module load, state round-trip,
  activation, exact 512-sample latency, termination, and unload.
- The versioned command ring now carries an explicit reload request. Reloading
  first disconnects the old graph, evaluates the script in a fresh namespace,
  preserves the engine process on failure, and clears its structured diagnostic
  after a successful correction.
- The generic host editor exposes `Reload Script` as a stable action parameter.
  A rising edge requests reload, so hosts can invoke it by toggling the control
  off and on without requiring a custom editor.
- A Windows end-to-end test starts the engine with invalid syntax, verifies its
  `SyntaxError`, replaces the script with one that raises `RuntimeError`, reloads
  and verifies that diagnostic, then replaces it with a valid `synthio` graph.
  The same VST-side transport resumes audible output without process or VST
  reload. Windows now passes five CTest cases; Linux remains four of four.
- Note-driven playback was later confirmed in REAPER on both platforms; see the
  Phase 6 and Phase 8 evidence.

## Phase 4 — MIDI and sample timing

Status: **Complete**

Deliverables:

- Carry absolute sample positions for note, controller, and parameter events.
- Support note-on/off, velocity, pitch bend, aftertouch, and MIDI controllers.
- Preserve event offsets through the fixed-latency pipeline.
- Render around event boundaries instead of quantizing to the normal 256-frame
  audioif chunk. Implement any adapter in this repository while `audioif` is
  read-only; propose upstream changes separately if a generic API is required.
- Verify timing by inspecting rendered PCM.

Exit criteria:

- Note and controller changes appear at the expected delayed sample for events
  at the start, middle, and end of variable-size host blocks.

Evidence recorded 2026-08-25:

- The VST processor translates note-on, note-off, and poly-pressure events into
  a fixed 256-record callback-owned array without allocating. The transport
  converts block-relative offsets to absolute positions including reported
  latency, uses bounded producer/consumer accounting, and counts overflow or
  work-queue drops.
- `vstaudio.on_event()` exposes the full event record to Python. The default
  instrument maps note-on/off into its `synthio.Synthesizer`; reload clears the
  old callback together with the old graph.
- A repository-owned direct-synthio adapter bounds render spans at event
  boundaries without changing `audioif`. This prevents its normal 256-frame
  pull from pre-rendering across a pending event.
- The cross-platform native gate test places note-on and note-off at offsets 17
  and 49 and verifies the PCM gate opens only from samples 273 through 304 after
  the configured 256-sample latency.
- The Windows CLI VST host now injects MIDI note 57 at offset 64. With the
  plug-in's reported 512-sample latency, the bundled MicroPython/synthio graph's
  first audible PCM sample is exactly 576. The native fallback ignores this
  event, so the hook also proves Python dispatch.
- The default Python instrument now creates one `synthio.Note` per VST note ID,
  applies note-on velocity as amplitude, includes VST tuning in its frequency,
  and gives each voice an explicit 50 ms release. The CLI host sends note-off
  at delayed sample 1312 and verifies the release continues to sample 3967
  before becoming silent.
- After adding the reload action, the current Linux and Windows builds still
  pass all 47 Steinberg validator checks. Linux passes four of four CTest cases;
  Windows passes five of five, including engine reload and MIDI timing.
- The controller implements VST3 `IMidiMapping` for all 16 channels, all 128
  MIDI CC numbers, channel pressure, and pitch bend. Each assignment has a
  stable hidden parameter ID so the processor recovers both channel and
  controller from sample-positioned parameter queues. The Steinberg MIDI
  mapping test accepts all assignments.
- Pitch bend on channel 3 changes the native PCM marker from 0.125 to 0.25 at
  delayed sample 768 exactly. Channel pressure and ordinary CC records use the
  same tested conversion path; poly-pressure remains a native VST event.
- A variable-block PCM test uses block sizes from 1 through 128 frames and
  verifies gate transitions produced by events at block start, middle, and the
  final frame. Expected audible intervals after latency are exactly 256–285,
  287–334, and 384–447.
- The bundled example applies poly-pressure, channel pressure, and a conventional
  ±2-semitone pitch bend to active voices. All raw records remain available to
  user scripts through `vstaudio.on_event()`.
- The native sidecar now has an independent staging target, so rebuilding the
  engine refreshes an otherwise unchanged VST bundle. This closes a packaging
  issue found by the pitch-bend lifecycle hook.

## Phase 5 — Automation and project state

Status: **Complete**

Deliverables:

- Deliver 16 normalized script-visible macros with stable VST parameter IDs.
- Allow script-provided labels without changing automation identity.
- Store script source/bundle, macro values, engine settings, and schema version
  in component state; external paths are development conveniences only.
- Restore a fresh sidecar completely before processing resumes.

Exit criteria:

- A project reopens reproducibly after its original development script moves.
- Automation remains attached across script label and state-schema changes.

Evidence recorded 2026-08-25:

- Macro IDs remain stable at 100–115 and their latest normalized values remain
  in versioned component state.
- Every automation point, rather than only the last point in a host block, is
  converted to `MPVST_EVENT_PARAMETER`. Python receives macro index 0–15 in
  `data0`, normalized value in `value0`, and the latency-adjusted absolute
  sample position through the ordinary `vstaudio.on_event()` callback.
- The native VST lifecycle hook automates Macro 01 to 0.75 at block offset 17
  and observes its PCM marker change at delayed sample 1041 exactly.
- `vstaudio` now exports named constants for all seven event types, so scripts
  do not depend on protocol numeric literals.
- State schema v2 retains the v1 bypass/macro prefix and adds the pipeline
  setting plus a length-bounded embedded script (maximum 1 MiB). Both processor
  and controller continue to accept legacy v1 state; the lifecycle hook tests
  that compatibility explicitly.
- On restore, embedded source is written to a private per-instance temporary
  script and a fresh sidecar is started. The file is reused for supervised
  engine restarts and removed when the instance stops.
- A Windows end-to-end state test creates a development script, saves component
  state, deletes the original file, restores a new component, and renders its
  330 Hz `synthio` graph from the embedded copy. Windows now passes six of six
  CTest cases; Linux remains four of four.
- Scripts may provide generic-editor macro titles with the metadata line
  `# mpvst-macro-labels: Gain | Tone | ...`. The controller reads labels from
  embedded state, updates parameter titles, and reports `kParamTitlesChanged`;
  IDs 100–115 never change. The deleted-source test verifies Macro 01 remains
  ID 100 while its restored title is `Gain`.

## Phase 6 — Usable Windows instrument release

Status: **Complete**

Deliverables:

- Ship generic-host-editor workflow and example synthio instruments.
- Add structured error/status presentation through host-visible mechanisms.
- Add click-free pipeline reset and script reload fades.
- Produce installable Windows artifacts and a DAW smoke-test matrix.
- Document that scripts execute with unrestricted desktop capabilities.

Exit criteria:

- Install, scan, play, automate, save, reload, and uninstall succeed across the
  selected Windows DAW matrix.

Evidence recorded 2026-08-25:

- `docs/windows-workflow.md` documents per-user/system installation, generic
  editor operation, development reload, state restore, uninstall, and the
  unrestricted desktop-script security model. Two copyable `synthio` examples
  cover a velocity instrument and a macro-controlled drone.
- Read-only `Engine Ready` and integer `Engine Error` parameters expose status
  in generic host editors. The lifecycle host observes ready=1/error=0; error
  codes 1 and 2 correspond to script-load and render exceptions whose bounded
  text remains available through the transport diagnostic API.
- Reload now applies an allocation-free 128-sample fade-out, holds silence for
  the 640-sample pipeline/refill interval, and applies a 128-sample fade-in.
  A native VST hook verifies every PCM sample of that envelope.
- `tools/package-windows.sh` produces a 2.3 MiB versioned ZIP containing the
  complete VST bundle, workflow, README, and examples plus a SHA-256 sidecar.
  `unzip -t` reports no errors.
- Current automated results are Steinberg validator 47/47 on both platforms,
  Windows seven of seven CTest cases, and Linux five of five.
Evidence recorded 2026-08-25 (physical DAW):

- REAPER 7.79 was installed on Windows and the packaged ZIP was installed to
  `%LOCALAPPDATA%\Programs\Common\VST3`. REAPER scans it as
  `VST3i: MicroPython Instrument (PyDevices)` and reports 2,103 parameters,
  which is the plug-in's 2,100 plus REAPER's own three.
- `tools/daw-matrix` drives REAPER headlessly through a startup ReaScript. All
  fourteen steps pass: instantiate, engine ready, play, automate, edit and
  reload, restore, save, reopen, reopen-ignores-edit, malformed script,
  recovery, four concurrent sidecars, and removal.
- Every rendered PCM check passes. A note gates at exactly 0.125 with Macro 01
  at zero and 0.25 at full scale, an edited script reloads to its own 0.375, a
  reopened project reproduces the saved 0.25, a malformed script renders exact
  silence with `Engine Error` 1 while the sidecar stays ready, and recovery
  returns to 0.125.
- Finding Macro 01 under the name `Level` confirms script label metadata reaches
  the host's generic editor.
- The report is in `docs/evidence/reaper-matrix-report.txt`.
- Driving a real DAW exposed two defects the automated hosts could not: restored
  and automated macro values never reached the script, and a reload replayed the
  source as it was when the instance was created rather than what was on disk.
  Both are fixed and covered by regression tests.
- REAPER is the only host tested. A second host on each platform remains
  recommended follow-up work rather than a release blocker.

## Phase 7 — Offline rendering and hardening

Status: **Complete**

Deliverables:

- Add an offline-processing path that cannot be outrun by faster-than-realtime
  host export.
- Stress GC, allocation, many instances, constrained heaps, changing block
  sizes, transport discontinuities, and sidecar failure.
- Add render-time, queue-depth, underrun, and crash telemetry.
- Fuzz protocol messages and state payloads.

Exit criteria:

- Long soaks and offline exports complete deterministically without callback
  blocking or cross-instance interference.

Evidence recorded 2026-08-25:

- VST `kOffline` processing uses a separate bounded-wait path; the realtime
  path remains non-blocking and unchanged. After the initial reported latency,
  offline calls wait up to five seconds for their exact output slot rather than
  registering a false underrun when a host exports faster than realtime.
- A no-sleep offline test submits eight consecutive blocks faster than the
  sidecar can naturally schedule and verifies exact silence through sample 255
  and exact 0.125 PCM from sample 256 onward under both MSVC and GCC.
- The protocol test mutates magic, major version, header/mapping sizes, endian
  marker, channel count, and every required region offset; all malformed
  headers are rejected. The VST lifecycle state corpus rejects empty state,
  invalid pipeline depth, oversized source, and truncated source while still
  accepting legacy v1.
- Both engines now write `render_time_ns`, which the ABI declared but nothing
  populated. `SidecarTransport::telemetry()` returns a lock-free snapshot of
  queue depth, render time, underruns, event drops, restarts, error code, and
  the last exit reason, with peaks tracked from the audio thread and a distinct
  code for an engine the supervisor killed for hanging.
- The work slot carried a placeholder timeline. The processor now reads the host
  process context and passes real position, tempo, and time signature through,
  detects locates, loop wraps, and play-state changes, and emits
  `MPVST_EVENT_TRANSPORT`. `vstaudio.transport()` exposes the same to scripts.
  A smoke-host hook proves a held note is silenced by a locate.
- `mpvst_soak_tests` runs four instances at real-time pace with a different
  block size every callback, events, periodic bypass, and periodic locates. A
  sixty-second run completes about 5,500 blocks per instance with zero
  underruns, zero event drops, and zero restarts.
- The soak found two defects. Bypassed blocks submitted work but never consumed
  the output, leaking a ring slot each time until the engine could not publish
  and the supervisor restarted a healthy sidecar. Separately, the supervisor
  treated a quiet host as a hung engine, so pausing a transport restarted the
  sidecar and lost script state. Both are fixed and covered by a regression
  test.
- `tests/fuzz` exposes libFuzzer entry points for the shared mapping and the
  project-state parser, with a portable deterministic driver so the targets run
  under GCC and MSVC too. `-DMPVST_ENABLE_LIBFUZZER=ON` builds the
  coverage-guided variants on clang. The fuzzer found that
  `mpvst_validate_mapping` never checked the optional region offsets it derives,
  so a mapping with an attacker-chosen `optional_offset` was accepted.
- `MPVST_HEAP_BYTES` caps the MicroPython heap per instance, so a runaway script
  fails inside its own sidecar rather than growing until it disturbs the DAW.

## Phase 8 — Linux port

Status: **Complete**

Deliverables:

- Build the Linux VST3 bundle and Unix MicroPython sidecar.
- Reuse the IPC protocol, scripts, states, and timing tests unchanged.
- Package and test installation in selected Linux VST3 hosts.

Exit criteria:

- The same saved patch produces matching PCM on Windows and Linux within the
  defined conversion tolerance.

Evidence recorded 2026-08-25:

- The `vstaudio` usermod is no longer Windows-only. Shared-mapping open and
  teardown, the monotonic clock, the idle and yield waits, and the atomics all
  have POSIX implementations, so the same module builds for the unix port.
  `./tools/build-micropython-engine.sh --port unix` produces the sidecar.
- The Linux bundle stages the MicroPython engine alongside the plug-in, and
  `tools/package-linux.sh` produces a versioned tarball with a SHA-256 sidecar
  that preserves the executable bits the engine needs.
- The MicroPython-only tests are no longer gated on Windows. Linux now runs
  twelve of twelve, including the reload, embedded-state, and MicroPython
  lifecycle hooks that previously only ran on Windows.
- REAPER 7.79 for Linux was installed to `~/opt/REAPER`, and the plug-in
  installed to `~/.vst3` from the release tarball. The same matrix passes all
  fourteen steps and every PCM check, with identical measured levels to Windows.
  The report is in `docs/evidence/reaper-matrix-report-linux.txt`.
- `tools/check-cross-platform-parity.sh` renders a fixed synthio score through
  the real MicroPython sidecar on each platform and compares the raw float32
  PCM. The two files share a SHA-256, so the platforms agree exactly rather than
  within a tolerance.
- A host without a live audio device only processes during a render, which the
  Linux REAPER under WSLg made visible: status parameters are published from
  `process()`, so the matrix forces a render before reading one. Real-time
  playback on Linux audio hardware has not been exercised.

## Extension - audio-input effect

Status: **Complete** (2026-08-25)

The bundle now registers a second class, **MicroPython Effect** (category
Fx), sharing the instrument's processor with a stereo audio-input bus.

- Protocol minor 1: the shared mapping's optional region carries one
  input-audio block per work slot (planar float32, cache-line strides),
  written before the slot's sequence publish so the existing acquire
  covers it. Instrument mappings are byte-identical to minor 0.
- The engine converts each block to interleaved int16 symmetrically
  (x32768 with clamp, so int16-sourced audio round-trips exactly) into a
  ring the script reads through `vstaudio.input()`, an audiosample
  source. Any audioif chain - filters, echo, chorus, freeverb, mixer -
  can therefore process live host audio; when a chain's internal
  buffering pulls ahead it receives silence once, self-priming to its
  own depth. `examples/fx_space.py` is a scripted filter/echo/hall send.
- Bypass on the effect is a pass-through delayed by the reported
  pipeline latency, so toggling it never shifts time under host delay
  compensation.
- Evidence: protocol layout/validation tests cover the input region and
  reject partial coverage; the fuzz harness asserts the region's
  invariants; `effectCarriesHostAudio` proves the native engine halves
  host audio sample-exactly through the pipeline latency;
  `mpvst_effect_audio_smoke` drives the real MicroPython engine through
  the VST3 effect class with a pass-through script and matches input to
  output within int16 quantisation at exactly 512 samples; the Steinberg
  validator passes both classes (94 checks); and the REAPER matrix loads
  a generated project that embeds the gate instrument and the halving
  effect in per-instance state, then measures the gate passing unchanged
  through the bypassed effect and at exactly half level through the
  active one, on both platforms.
- A limitation surfaced by the matrix is now documented behaviour: two
  developer-file instances cannot follow different scripts, because
  MPVST_SCRIPT_PATH is process-wide and instances re-read it on restart
  and on save. Instrument-plus-effect projects embed per-instance state
  instead, which `tools/daw-matrix/build_effect_project.py` demonstrates
  by synthesizing the chunks directly.
- The engine no longer resets its output sample on registration:
  audiomixer's reset stops every voice, so `vstaudio.output(mixer)` after
  `voice.play(...)` - the idiomatic order - used to silence the chain.

## Deferred extensions

- LVGL editor and shared framebuffer/input protocol.
- Effect extras: wet/dry mix parameter and sidechain input buses.
- Float64 host processing and a native floating-point audioif graph.
- macOS bundles, signing, notarization, and universal binaries.
