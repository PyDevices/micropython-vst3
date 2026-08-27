# UI v1 design (LVGL editor)

Status: draft for review, 2026-08-26. Companion to `phase-0.md` (process
boundary) and `ipc-v1.md` (wire rules). Nothing here weakens either: the
audio thread rules, slot lifecycle, and bounded-data rules apply to every
structure this document adds.

## Decisions

- **LVGL is the product UI toolkit, permanently part of the engine.** The
  shipped engines already contain LVGL 9.5 with the PyDevices integration
  frozen in (`display_driver`, `displaydev`, `multimer`, `appdev`), so this
  is a requirement to hold, not work to do. A ctest imports `lvgl` and
  `display_driver` from the staged engine so the module set cannot silently
  regress.
- **The editor is a PyDevices display target, not an LVGL-specific
  integration.** The engine exposes a framebuffer and a pointer device
  through the same board contract every PyDevices board uses. LVGL is what
  the product panel is written in; other layers on the contract (pdwidgets,
  pygraphics) remain available to script authors without any change here.
- **UI code runs in the engine process.** The shared-memory UI region never
  encodes which process paints it, so a dedicated UI sidecar remains a
  drop-in fallback if GC or scheduling coupling is ever measured.
- **Fixed logical resolution, declared from Python.** The panel calls
  `vstui.configure(width, height)` once at startup, bounded by a
  compile-time maximum of 1024x600. The stock panel uses 800x480. The size
  is fixed for the life of the engine generation; the view scales, the
  engine never re-lays-out.
- **Pointer and wheel input, no keyboard.** Mouse down/up/move is delivered
  as the same mouse-as-touch model the desktop board configs use. The wheel
  is delivered as encoder input — the board contract's `encoder_read` — so
  it surfaces in LVGL as encoder events on the virtual encoder device
  `display_driver` already creates. The panel keeps its controls in an
  input group: clicking focuses a control, wheel deltas adjust the focused
  control (the slider now, the knob later). No keyboard focus handling.

  Only the vertical wheel axis drives this in v1. That is a zero-cost
  consequence of the existing shared `display_driver.py` (canonical copy in
  `lvgl-bindings`, synced to every sister project): its `_encoder_cb` reads
  only the neutral wheel event's `.x` field, which is what a normal vertical
  scroll populates; horizontal scroll populates `.y`, which nothing reads.
  Wiring horizontal in would mean editing that shared, release-gated file —
  a cross-repo change affecting lvgl-micropython/-circuitpython/-python, not
  a change scoped to this plug-in — so it stays a deferred option, not a v1
  gap to close here.

  A two-finger trackpad swipe, tested under WSLg during this design pass,
  did not resolve the question either way: a bare `appdev`-level probe (no
  LVGL, no `display_driver.py`) showed a swipe in *either* direction
  producing the identical event shape — `Wheel(x=±1, y=0)` — with `y`
  always zero and no `FINGERMOTION` events at all. Whichever physical axis
  was swiped, it collapses onto one scroll channel somewhere in the
  Windows-Precision-Touchpad → WSLg virtual channel → X11/SDL2 pipeline,
  upstream of every layer this project controls. That may well be specific
  to testing through WSLg's remoting rather than true of a DAW host running
  natively — re-test on a native Windows or Linux session (no remoting
  layer in between) before concluding a two-axis encoder is or isn't
  possible.

  A click moving group focus always drops the group out of edit mode as
  part of that same transition (this is `lv_group_focus_obj` in LVGL core,
  not a PyDevices choice), so the panel must not re-enable editing from a
  `PRESSED` handler — that runs before the drop and gets silently
  overwritten. It has to run from the control's own `FOCUSED` handler,
  which fires after focus (and the mode drop) has settled.
- **v1 ships exactly one panel**: a generic panel built from metadata the
  bundle already carries (macro labels, `PATCHES`, engine status), using
  stock `lv.slider` and `lv.switch` controls. A single shared knob widget
  may later replace sliders as a panel-internal change with no protocol
  impact. Per-script custom panels are deferred but must require no
  protocol change when they arrive: they replace the panel module, not the
  surface under it.

## System boundary

The UI is one new optional region set in the existing mapping, using the
region slot ipc-v1 reserves for future non-audio payloads. Protocol minor
version increments; readers that ignore unknown optional regions remain
valid, so an old engine under a new plug-in (or the reverse) simply has no
editor.

Ownership is split by process and thread:

- The **engine** paints the framebuffer, consumes input events, and
  publishes parameter edits. All of it happens in the housekeeping step of
  the engine loop, never inside audio rendering work.
- The **view** (one `IPlugView` implementation serving instrument and
  effect alike) blits the framebuffer, injects input events, and turns
  published edits into `beginEdit`/`performEdit`/`endEdit` on the
  controller. It never interprets pixels.
- The **processor** creates the region with the rest of the mapping and
  never touches it again. `process()` has no UI involvement of any kind.

The controller learns the mapping identity (name plus generation) through a
processor-to-controller `IConnectionPoint` message — new traffic, standard
SDK plumbing. The view maps only the UI region.

When no editor is open the engine does no UI work: no LVGL timers, no
painting, no input polling. The cost of the feature with the editor closed
is untouched pages.

## Board-contract seam

A `vstui` module joins `vstaudio` in the engine usermod:

| Call | Role |
|---|---|
| `vstui.configure(w, h)` | declare logical size, once, within the compiled maximum |
| `vstui.framebuffer()` | memoryview of the RGB565 framebuffer |
| `vstui.publish(x, y, w, h)` | seqlock-wrapped dirty-rect publication |
| `vstui.poll()` | drain pending input events |
| `vstui.editor_open()` | host's editor-attached flag |

`lib/vst_board_config.py` wraps that into the standard board contract: a
`display_drv` whose `blit_rect` copies into the shared framebuffer and
publishes, plus `touch_read` (pointer) and `encoder_read` (wheel deltas)
both fed from `vstui.poll()`. Above that line the stack is stock
PyDevices: `display_driver` wires LVGL to the board config exactly as it
does on hardware — including the virtual encoder device that turns wheel
deltas into LVGL encoder events — with one loop rule — `app.run()` is never
called in the sidecar. The engine pumps the same synchronous tick
`display_driver.event_loop` uses, from its housekeeping step.

The panel itself imports neither `vstui` nor `vstaudio`; it sees a board
config and an adapter object (mirroring the `mpvst_adapter` seam) for
macro values, labels, patches, and status. That keeps the panel runnable
under `lvgl-python` on the desktop with a mock adapter — which is both the
development loop and the portability requirement satisfied for free.

## Region layout

All records observe ipc-v1 wire rules: fixed-width little-endian integers,
no padding, 64-byte region alignment, every region carrying size and
generation. Normalized parameter values are float32, matching output-slot
sample precision.

| Record | Bytes | Role |
|---|---:|---|
| `mpvst_ui_state` | 128 | logical and maximum size, pixel format, editor-open flag, content scale, frame seqlock, ring cursors, UI error code, heartbeat |
| `mpvst_ui_rect` | 16 | dirty rectangle keyed to a frame sequence |
| `mpvst_ui_input` | 32 | input event: type, buttons, logical x/y, signed wheel delta, sequence |
| `mpvst_ui_edit` | 32 | parameter edit: kind (begin/perform/end), parameter ID, normalized float32 value, sequence |
| framebuffer | 1024x600x2, 64-byte aligned | RGB565 little-endian pixels at the maximum size; the logical size indexes into the same stride |

Ring capacities: 64 dirty rectangles, 256 input events, 64 edits. Rings
overflow by bounded, counted degradation, never by waiting: a full dirty
ring coalesces to one full-frame rectangle, pointer-move events coalesce to
the latest position, wheel events coalesce by summing their deltas, and a
full edit ring drops `perform` records but never a `begin` or `end`.

**Frame publication** is a seqlock, not slot exchange, because a frame is
too large to double-buffer per instance and a torn read costs only one
repaint. The engine sets the frame sequence odd, writes pixels and
rectangles, then sets it even. The view samples the sequence, copies the
rectangles it covers, and re-checks; on mismatch it discards and retries on
its next timer tick. Neither side ever waits.

**Coordinates** are logical pixels everywhere in the protocol. The view
divides window coordinates by the content scale on the way in and multiplies
on the way out; the engine never sees DPI.

**Edits** flow engine-to-host so panel gestures become recordable
automation: slider drag produces `begin`, a bounded stream of `perform`,
then `end`, which the view replays into the controller on its timer. A
burst of wheel ticks on a focused control is one gesture: `begin` on the
first tick, `end` after a short quiescence, so wheel adjustments record as
one automation edit rather than dozens. The
host echoes the change back through the normal `EVENT_PARAMETER` path and
the existing macro replay rules; the panel treats incoming parameter state
as truth, which is stable because the echo equals what the panel already
shows. The editable set in v1 is exactly the patch selector and the 16
macros (permanent IDs 100–115).

## Scheduling

Phase-0 already states the rule: audio work takes priority over optional
housekeeping, and the UI is the canonical optional housekeeping. The engine
runs the LVGL tick only when the editor is open and the output queue is
ahead of its deadline, with a per-tick time budget targeting roughly 30 Hz
refresh. Under pressure the frame rate degrades; audio never does.

The known risk is GC coupling: panel allocations feed the same MicroPython
heap the instrument renders from, and pipeline slack is the latency `L`.
The acceptance gate is empirical — the REAPER matrix run with an editor
open must show zero underruns, using the telemetry counters that already
exist. If coupling is ever measured, the fallback is a second sidecar
process mapping the same UI region; the protocol above is deliberately
indifferent to which process serves it.

## Failure behavior

- A Python exception in panel code is caught at the tick boundary: the
  panel is torn down, `ui_error` is set with the bounded diagnostic path
  ipc-v1 already provides, and audio is unaffected. If LVGL can still
  paint, the bootstrap shows a minimal error card; either way the view
  renders its own native "editor unavailable" text whenever `ui_error` is
  nonzero, so a broken panel is visible rather than frozen.
- Engine restart follows the existing supervisor rules. The view observes
  the generation change, re-syncs, and the panel rebuilds from replayed
  macro state — the same mechanism that restores an automated instance
  today.
- Editor close clears nothing in flight: the engine simply observes
  `editor_open` false and stops painting. Input and edit cursors reset on
  the next open, so stale gestures are never replayed.
- Editor open must not change rendered audio. The cross-platform parity
  check is the enforcement: PCM hashes with and without an editor attached
  are identical.

## The view

One implementation, written once, generic forever:

- Fixed size: logical size times content scale, reported through
  `checkSizeConstraint`/`getSize`; not user-resizable in v1.
  `IPlugViewContentScaleSupport` writes the scale into `mpvst_ui_state`.
- A 30–60 Hz timer per platform idiom (Windows HWND timer, X11 runloop
  timer on Linux) samples the seqlock, converts RGB565 to the native
  surface format during the dirty-rect copy, drains the edit ring into
  controller edits, and forwards pointer and wheel events.
- Attach/detach toggles `editor_open` and starts/stops the timer. The view
  holds no state worth preserving across detach.

## Build and packaging

- The engine module set permanently includes `lvgl-micropython` via the
  existing cmods workspace discovery; the new ctest pins it. The only
  engine-rebuild event this design introduces is the `vstui` usermod
  itself, under the usual rebuild ritual.
- The bundle stages `vst_board_config.py` and the panel package beside the
  bootstrap, like every other `lib/` file.
- The panel package keeps its host-neutral shape (panel + adapter split) so
  it can graduate to a sibling repo as a portable PyDevices example later
  without surgery. It starts here.

## Acceptance

1. ctest: staged engines import `lvgl` and `display_driver`; protocol
   conformance extends to the UI records (identical offsets under MSVC and
   GCC, seqlock torn-read detection, ring overflow degradation).
2. Smoke host: open/close editor cycles across engine restarts without
   leaking mappings or replaying stale input.
3. REAPER matrix with editor open: zero underruns, panel slider and wheel
   gestures recorded as automation, echoed parameter state stable (no
   oscillation).
4. Parity: PCM identical with and without an editor attached.

## Deferred

- Per-script custom panels (the panel-module replacement path above).
- The shared knob widget, meters and scope taps, and host keyboard focus.
- User-resizable or zoomable editors.
- A dedicated UI sidecar process (kept possible, not built).
- macOS, with the rest of the platform work.
