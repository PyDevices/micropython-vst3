# Phase 0 architecture contract

Status: accepted for implementation on 2026-08-25. Historical: this is the
Windows-only era design, from before Linux shipped and before the LVGL
editor existed (see "Deferred UI" below, superseded by `ui-v1.md`). Kept
for the reasoning behind the process/thread/state rules, which still hold;
not a description of what ships today.

## System boundary

The product consists of two independently built Windows binaries:

1. `MicroPythonVST3.vst3`, an MSVC-built VST3 instrument loaded into the DAW.
2. `micropython-vst-engine.exe`, a headless MicroPython process owned by one
   processor instance.

They exchange only the versioned POD data described in `ipc-v1.md`. No C++
objects, pointers, handles with process-local meaning, or MicroPython objects
cross that boundary. This keeps the VST SDK ABI independent of the existing
MicroPython Windows toolchain.

## Instance model

Every VST processor instance owns a distinct sidecar process and shared-memory
namespace. This avoids MicroPython's process-global VM state, prevents one
script's GC from sharing a heap with another instance, and contains ordinary
Python exceptions and engine-process crashes.

The controller does not own the sidecar. A host may construct a controller
without activating the processor, and the processor must remain valid without
an editor.

## Thread ownership

### VST audio thread

`IAudioProcessor::process()` may only:

- read host-provided buffers, events, and parameter queues;
- copy into or out of preallocated shared-memory slots;
- perform bounded sample conversion when required;
- update lock-free atomics and fixed-size counters; and
- emit silence when the expected output is unavailable.

It must not allocate, free, lock, wait, open files, access the network, start a
process, call MicroPython, log, or call UI APIs.

### Host non-audio threads

Initialization, state transfer, activation requests, sidecar lifecycle, error
formatting, and future editor work happen outside `process()`. State operations
exchange immutable snapshots with the processor; they do not take a mutex also
used by the audio thread.

### Engine process

The engine owns MicroPython, audioif graph construction and rendering, garbage
collection, script I/O, and all unrestricted desktop capabilities. It consumes
timestamped work and publishes completed output slots. Audio work takes
priority over optional housekeeping.

## Audio shape

- One VST event input bus.
- No VST audio input bus in the instrument MVP.
- One stereo VST audio output bus.
- Float32 planar host buffers initially; float64 is rejected.
- Audioif remains interleaved signed int16 internally for the first engine.
- Conversion to planar float32 happens in the engine before publication when
  practical, keeping the VST callback to bounded copies.

## Pipeline and latency

The callback sequence is identified by absolute sample position rather than a
host-block ordinal, because actual host block sizes may vary.

For input/event interval `t`, the engine publishes the corresponding generated
audio at `t + L`. The initial `L` is four times the maximum block size supplied
by VST `setupProcessing()`. The processor reports `L` to the host. Live input
therefore has this additional latency; playback alignment is left to host delay
compensation.

The first `L` samples after activation are silence. Missing or late output is
also silence and increments an underrun counter. The audio thread never waits
for the engine.

Changing sample rate or maximum block size deactivates and rebuilds the
pipeline outside `process()`. A generation number prevents stale slots from a
previous configuration from being consumed.

## Events and parameters

VST event offsets are converted to absolute sample positions before enqueue.
The engine applies them to the delayed render interval, preserving the offset
within that interval. Macro parameters have permanent numeric IDs; labels are
metadata and may change without invalidating automation.

The MVP exposes bypass plus 16 normalized macros. Bypass for an instrument
produces silence.

## State

Component state is a versioned binary envelope containing:

- script source or a self-contained script bundle;
- macro values and engine configuration;
- future extension sections that old readers can skip; and
- integrity bounds before any allocation or engine transfer.

An external script path may be stored as development metadata but is never the
only copy required to restore a project. State restoration builds a fresh
engine generation before audio resumes.

Phase 1 implemented the versioned macro/bypass prefix. Phase 5 state v2 keeps
that prefix, accepts legacy v1, and appends bounded pipeline configuration and
up to 1 MiB of embedded script source. Restore materializes an instance-private
temporary script, starts a fresh engine, and removes the file on shutdown.

## Failure behavior

- Underrun: output silence, increment a counter, continue.
- Protocol/generation mismatch: output silence and request non-audio recovery.
- Python exception: engine reports a bounded structured error and stops the
  affected graph without terminating the VST module.
- Engine exit/hang: output silence; a supervisor outside the callback quiesces
  callback access with atomics, advances the shared-memory generation, and
  makes at most three consecutive restart attempts.
- VST module error: never throw across a VST interface boundary.

## Security posture

The initial product deliberately grants scripts the full capabilities of the
desktop MicroPython build, including filesystem, network, FFI, and process APIs
that are present in that build. Process separation is crash isolation, not a
security sandbox. Distribution and UI must state that loading a script executes
trusted code with the user's permissions.

## Deferred UI

No custom editor is required for the MVP. The host's generic parameter editor
is sufficient. Protocol IDs are reserved for future status/UI traffic, but no
framebuffer or LVGL scheduling requirement is imposed on the audio milestones.

## Workspace dependency rule

The sibling `audioif` repository is read-only during this implementation
campaign because another agent is modifying it. This project may inspect and
consume committed/public interfaces, but must not edit, format, clean, or place
build products in that repository.
