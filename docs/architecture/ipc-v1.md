# IPC protocol v1 design

This document fixes the rules for Phase 2. The canonical exact structure sizes,
offsets, and compile-time checks are in `src/protocol/include/mpvst/protocol.h`.

## Compatibility

- Magic: four-byte ASCII `MPV3`.
- Protocol major: `1`; incompatible layout or semantic changes increment it.
- Protocol minor: starts at `0`; readers ignore unknown optional regions whose
  offsets and sizes are outside the known set.
- Every region carries its byte size and generation.
- All persisted integers are fixed-width little-endian values.
- Shared atomics are naturally aligned 32- or 64-bit integers whose Windows
  interlocked implementation is verified lock-free in both toolchains.
- No `bool`, enum-sized field, native pointer, `size_t`, C++ object, or implicit
  compiler padding appears in the wire layout.

## Regions

The mapping begins with a fixed header containing offsets and sizes for:

1. host-to-engine control ring;
2. timestamped VST event/parameter ring;
3. host-to-engine audio/work slots;
4. engine-to-host float32 output slots;
5. engine status and bounded diagnostics; and
6. optional future non-audio payloads.

The instrument MVP has no input audio samples, but work slots still describe
the requested sample interval, rate, channel count, and transport context.

Protocol v1 record sizes are deliberately cache- and compiler-independent:

| Record | Bytes | Role |
|---|---:|---|
| `mpvst_shared_header` | 128 | ABI identity, capacities, offsets, generation, lifecycle |
| `mpvst_status` | 128 | heartbeat, counters, event-consumer cursor, bounded diagnostic |
| `mpvst_command` | 64 | non-audio lifecycle and reload commands |
| `mpvst_event` | 32 | absolute-sample event or parameter change |
| `mpvst_work_slot` | 64 | bounded render request and transport context |
| `mpvst_output_slot` | 64 | output metadata followed by planar float32 samples |

`mpvst_event.type` distinguishes note-on, note-off, poly-pressure, pitch bend,
control change, generic parameter, and channel pressure. VST3 MIDI controller
parameters are decoded before entering the ring: `channel` retains the MIDI
channel, `data0` retains the controller number, `value0` is normalized 0–1,
and pitch bend also carries its bipolar -1–1 value in `value1`.

Every region starts on a 64-byte boundary. Each output slot has a 64-byte
header followed by `max_frames` left samples and `max_frames` right samples;
the full stride is rounded to the next 64-byte boundary.

## Slot lifecycle

Each fixed-capacity slot has an atomic sequence value. A producer owns a slot
only when its expected sequence is free, writes the payload, then publishes the
completed sequence with release ordering. A consumer acquires the sequence,
copies the bounded payload, and releases the slot for its next wrap. Neither
side waits for a slot on the VST audio thread.

Output slots are keyed by absolute start sample and generation. The VST side
accepts a slot only when generation, start sample, frame count, channel count,
and format match the requested output interval.

## Bounded data

- Maximum frames per slot is fixed when the mapping is created from VST
  `maxSamplesPerBlock`.
- Output storage is planar stereo float32 for protocol v1.
- Event payloads have fixed maximum size; oversized messages are rejected
  outside the audio callback.
- Text diagnostics use fixed UTF-8 buffers with explicit byte counts and
  truncation flags.
- Counters saturate rather than wrapping into misleading success values.

## Lifecycle

1. Processor setup chooses sample rate, maximum block size, and latency.
2. Non-audio lifecycle code creates a unique mapping and engine process.
3. Engine validates the complete header before marking itself ready.
4. Activation increments the generation and clears logical cursors.
5. Audio processing begins with `L` samples of silence.
6. Deactivation marks the generation closed and requests engine shutdown.
7. Lifecycle code waits and tears down handles after audio processing stops.

## Phase 2 conformance tests

- Both MSVC and GCC report identical offsets, sizes, and alignments. A MinGW
  build remains useful but is no longer an ABI boundary requirement because
  the sidecar is now also built with MSVC in the Windows proof.
- Producer/consumer wraparound does not overwrite unread slots.
- A stale generation is never played.
- Full rings cause bounded drops, not waits.
- Engine death while publishing cannot expose a partially completed slot.
- Variable host block sizes preserve absolute sample continuity.
