# UI v1 design (LVGL editor)

Status: built, 2026-08-27. Companion to `phase-0.md` (process boundary) and
`ipc-v1.md` (wire rules). Nothing here weakens either: the audio thread
rules, slot lifecycle, and bounded-data rules apply to every structure this
document adds.

Three things came out differently from the design below, and each has its
reasoning where it happened rather than only here:

- **The UI surface is a sibling mapping, not a region of the audio one.**
  `mpvst_shared_header` is exactly 128 bytes with nothing reserved, so
  carrying a `ui_offset`/`ui_bytes` pair means growing the header - and both
  the shipped engine and `mpvst_validate_mapping` reject a header whose size
  is not their own, so an old engine under a new plug-in would fail to start
  rather than "simply have no editor". `src/protocol/include/mpvst/ui.h` has
  the full argument. Compatibility now rests on the extra command-line
  argument naming the mapping: an engine that does not understand it ignores
  it and plays without an editor.
- **The panel edits bypass and reload as well as the patch and the macros.**
  Both are ordinary automatable parameters the host already exposes, they
  cost nothing in protocol terms, and a Reload button that did nothing would
  be worse than no button. This is the one place the editable set below is
  deliberately wider than it says.
- **The engine ticks the UI by pumping the timer provider, never by calling
  `App.poll()`.** They look interchangeable and are not; `lib/vst_editor.py`
  records why, because the difference silently swallows every click.

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

  v1 ships the two-axis mapping proven on the desktop mockup (decision
  2026-08-27): the axis parallel to the control adjusts it — horizontal
  swipe on the horizontal sliders, rightward increasing — and the
  perpendicular axis moves group focus between controls, downward going
  to the next. This is not a hand-rolled path: the mockup investigation
  fed the machinery straight into the canonical `display_driver.py`
  (`lvgl-bindings/python/display_driver.py`, released to every sister
  project), whose `set_wheel_mapping(adjust_axis, adjust_sign, navigate)`
  the panel calls with `("h", sign, True)`; every other consumer keeps
  the old single-axis default. Signs are a per-input-path fact (they
  differed between every build tested), so the panel's `adjust_sign` is
  recalibrated against `vstui`'s native deltas at integration and locked
  in by a smoke-host test that injects synthetic wheel events through the
  shared-memory input ring and asserts the focused macro moves in the
  expected direction.

  A `MOUSEWHEEL` event carries both a legacy integer `x`/`y` pair and a
  float `precise_x`/`precise_y` pair, and which one (if either) carries
  real horizontal data turned out to be a **per-`usdl2`-build fact, not a
  general rule** — tested against two different builds of the same
  `usdl2` module on 2026-08-27, same physical gesture:

  - MicroPython (`~/.micropython/lib`, unix port): horizontal works. A
    pure vertical swipe sets a spurious nonzero value on the legacy
    integer `x` field *simultaneously* with the correct `precise_y` —
    real vertical motion, mislabeled onto the x-channel, while real data
    also legitimately arrives on `precise_y`. Reading legacy-or-precise as
    independent per-channel fallbacks double-counts that (one vertical
    swipe drives both a value-adjust and a focus-navigate). Fixed by
    trusting only `precise_x`/`precise_y` for both axes whenever either is
    nonzero, ignoring the legacy pair entirely for that event. With that
    fix, a horizontal swipe cleanly navigates and a vertical one cleanly
    adjusts — this build has a real, usable second axis.
  - CPython (`pydevices-lvgl` wheel, `pydevices-examples` venv): no second
    axis exists at all. Vertical reliably arrives on the legacy integer
    `x` (confirmed all session — this is what backs the v1 vertical-only
    behavior). A horizontal swipe produces `x=0, y=0` and
    `precise_x`/`precise_y` that are either exactly `0.0` or the constant
    `1.401298464324817e-45` — the IEEE-754 bit pattern of the small
    integer `1` reinterpreted as a float32, i.e. a fixed decoding artifact
    in this build's `usdl2`, never real motion. There is no field left to
    read; this build cannot demonstrate horizontal input at all.

  The practical upshot: both builds above are dev/test tooling, not the
  shipping product. `usdl2` (PyDevices' SDL2 binding, behind
  `AutoDisplay`/`SDLDisplay`) exists so a panel can be built and clicked
  around on an ordinary desktop before it ever touches the engine — the
  shipping engine has no SDL window and never links `usdl2` at all. Its
  wheel input takes a completely different, simpler path: the native
  C++ view reads the host platform's own wheel events directly and packs
  them into `mpvst_ui_input`'s pair of signed delta fields, one per axis
  (this document's region layout, above), which `vstui.poll()` surfaces
  through `vst_board_config.py`. On Windows that event (`WM_MOUSEWHEEL`)
  already reports an unambiguous signed multiple of `WHEEL_DELTA` — the
  legacy-vs-precise duality this section spent so long on is purely an
  SDL concept and cannot occur there. Confirmed against a real PyDevices
  reference: `displaydev.windisplay.WinDisplay._wndproc` handles
  `WM_MOUSEWHEEL` and `WM_MOUSEHWHEEL` as two separate, correctly-labeled
  messages with no legacy/precise split at all — vertical and horizontal
  are already distinct signals on native Windows, which is a better
  starting point than either desktop test build gave us today. Linux may
  still have a comparable
  question of its own (X11's legacy button4/5/6/7 wheel clicks vs.
  XInput2 smooth-scroll valuators are a structurally similar but distinct
  split), worth checking empirically once the native view's Linux input
  handling is actually written — but that is a fresh investigation against
  X11, not a rerun of the `usdl2` check performed here. What today
  settles is narrower and still worth having: horizontal-as-navigate is a
  workable interaction (proven against real LVGL group/encoder behavior
  on the MicroPython desktop build), independent of whichever platform
  API ends up feeding it in the shipping engine.

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
| `vstui.open(name)` | map the region the plug-in named; False when there is none |
| `vstui.configure(w, h)` | declare logical size, once, within the compiled maximum |
| `vstui.blit(buf, x, y, w, h)` | copy pixels in and publish, both inside the seqlock |
| `vstui.publish(x, y, w, h)` | publish a rectangle written through `framebuffer()` |
| `vstui.framebuffer()` | memoryview of the RGB565 framebuffer |
| `vstui.poll()` | drain pending input events |
| `vstui.edit(kind, id, value)` | publish one parameter edit |
| `vstui.editor_open()` | host's editor-attached flag |
| `vstui.error(code)` | report a panel failure for the view to render |

`blit` is the one the board config uses, and it is why `publish` is not the
only call: writing pixels through `framebuffer()` and publishing afterwards
leaves a window where the view can read half-written pixels, which is the
torn frame the sequence exists to make detectable rather than to cause. One
call that brackets the copy has no such window. `publish` stays for a caller
that composes its own pixels and knows when it has finished.

`lib/vst_board_config.py` wraps that into the standard board contract: a
`display_drv` whose `blit_rect` copies into the shared framebuffer and
publishes, plus `touch_read` (pointer) and `encoder_read` (wheel deltas)
both fed from `vstui.poll()`. Above that line the stack is stock
PyDevices: `display_driver` wires LVGL to the board config exactly as it
does on hardware — including the virtual encoder device that turns wheel
deltas into LVGL encoder events — with one loop rule — `app.run()` is never
called in the sidecar. The engine pumps the same synchronous tick
`display_driver.event_loop` uses, from its housekeeping step.

Two details of that seam were only settled by building it. The wheel
arrives as a `MOUSEWHEEL` host event rather than through `encoder_read`,
because the board contract's encoder is a single absolute position and
cannot express two axes; a host event carries both, and it means the whole
canonical wheel path in `display_driver` applies unchanged. And the
housekeeping tick pumps `multimer`'s `polling` provider directly rather
than calling `App.poll()`: `poll()` drains every registered device itself,
including the host-event device `display_driver` drains on the way to
LVGL's indevs, so ticking with it consumed every click before LVGL saw one.
Nothing does that on the desktop either — `display_driver.main()` calls
`app.stop_timer()`, which removes the app's own service tick and leaves
display_driver's pump as the only reader.

The panel itself imports neither `vstui` nor `vstaudio`; it sees a board
config and an adapter object (mirroring the `mpvst_adapter` seam) for
macro values, labels, patches, and status. That keeps the panel runnable
under `lvgl-python` on the desktop with a mock adapter — which is both the
development loop and the portability requirement satisfied for free.

`vst_board_config`'s `display_drv` must not set `share_framebuffer`. That
flag (`displaydev.__init__.DisplayDriver`, canonical `display_driver.py`)
tells the LVGL bridge to hand LVGL a direct, standing pointer into the
backend's own buffer (`DISPLAY_RENDER_MODE.DIRECT`, zero-copy, no
`blit_rect` call at all) — correct for native embedded scanout memory
addressed from one process, wrong for a seqlock-protected region another
process reads: the seqlock's odd/even toggle and rectangle-queue publish
have to happen at one deliberate copy step, not be smeared across LVGL's
own render/flush internals. Leaving the flag unset keeps the default
`PARTIAL` path instead — LVGL renders into its own small, process-private
draw buffer pair (`width × height/10` each, per `DisplayDriver`'s default)
and calls `blit_rect` per band, which is exactly the seam `vstui.publish`
hooks. `displaydev.windisplay.WinDisplay` is the reference for this whole
shape already working: an off-GC-heap persistent buffer (`VirtualAlloc`,
not a `bytearray`, so it survives independent of the interpreter's
collector) that its own `blit_rect` writes into and a dirty-band tracker
presents from — the shared UI region plays the same role its `_buffer`
does, `vstui.publish` plays the role its own dirty-band present does. On
Windows specifically, `WinDisplay._present` blits through `StretchDIBits`
over a 16-bit `BI_BITFIELDS` DIB with no conversion pass, since the
framebuffer is already RGB565 — the same technique is available to the
real C++ view's Windows present path for the identical reason.

## Region layout

All records observe ipc-v1 wire rules: fixed-width little-endian integers,
no padding, 64-byte region alignment, every region carrying size and
generation. Normalized parameter values are float32, matching output-slot
sample precision.

| Record | Bytes | Role |
|---|---:|---|
| `mpvst_ui_state` | 128 | logical and maximum size, pixel format, editor-open flag, content scale, frame seqlock, ring cursors, UI error code, heartbeat |
| `mpvst_ui_rect` | 16 | dirty rectangle keyed to a frame sequence |
| `mpvst_ui_input` | 32 | input event: type, buttons, logical x/y, two signed wheel deltas (vertical and horizontal — both axes ship in v1), sequence |
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
shows. The editable set in v1 is the patch selector, the 16 macros
(permanent IDs 100-115), and - see the note at the top - bypass and reload,
which the host already exposes as ordinary automatable parameters.

The panel sees the engine's side of that echo through `vstaudio.observe`,
which is new. `vstaudio.on_event` has exactly one owner, the instance
script, and the panel must not displace it to learn that automation moved a
macro.

Gestures are closed by quiescence rather than by a release event, because a
slider drag and a burst of wheel notches both arrive as a stream of value
changes with no reliable end marker. One rule in the adapter covers both.

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
  holds no state worth preserving across detach. This is host-driven
  (`IPlugView::removed()`), never a close button on a window this plug-in
  owns — the view is a child embedded in whatever frame the host provides,
  so "close the editor" can never mean "quit the engine". That distinction
  does not need enforcing in the real view; it falls out of not having a
  top-level window at all. It matters only for the desktop panel-dev
  mockup (`display_driver`/`appdev.App` owning a real OS window for
  developing the panel standalone), where closing the one window ending
  the test process is exactly the ordinary, correct desktop-app behavior
  — a code path the real view never runs at all.

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

1. ctest: staged engines import `lvgl` and the PyDevices integration
   (`mpvst_engine_modules`); protocol conformance extends to the UI records
   (identical offsets under MSVC and GCC, seqlock torn-read detection, ring
   overflow degradation) in `mpvst_protocol_tests`.
2. Smoke host (`--expect-editor`): the engine paints only while the editor
   is open, injected input reaches the panel, a rightward swipe raises the
   focused macro and a downward one steps to the next control, and a restart
   hands over a fresh mapping with no stale input in it.
3. REAPER matrix with the editor open, on both platforms: the host attaches,
   detaches and *re-attaches* a real view, the mirrored macro does not drift
   while it is open, and the engine is healthy afterwards. On Linux this is
   the only place the X11 window path runs at all, which is why the reopen
   cycle lives here rather than only in the Windows capture.
4. Parity: PCM identical with and without an editor attached, checked in the
   matrix against the same configuration rendered both ways.

5. Windows only, and the only test that looks at a screen
   (`mpvst_editor_window`): the real view is opened in a real window,
   photographed through `WM_PRINTCLIENT`, and required to equal the engine's
   framebuffer pixel for pixel - twice, closing and reopening in between,
   with the second view asked for while the first is still alive, because
   that is the order that broke reopening. `mpvst_gdi_blit_tests` pins the same geometry
   headlessly against GDI itself.

Both of those exist because the editor shipped painting the wrong 480 rows of
its 600-row framebuffer. In `HALFTONE` stretch mode GDI reads `ySrc` from the
bottom of the bitmap even when `biHeight` declares top-down, so the panel's
header fell off the top, unwritten black filled the bottom, and every click
was hit-tested 120 rows from the pixel it hit - which read as an editor whose
controls did not work. Every other test passed throughout: the engine's
framebuffer was correct on both platforms, the protocol was correct, and the
audio was byte-identical. Nothing that stops short of the window could have
seen it, so now something does not stop short.

Reopening an editor had two independent causes of the same black rectangle,
and both are worth stating because each alone was enough.

`createView` refused a second view while the first was still alive, guarding
a race between two readers of the input ring. REAPER builds a replacement
view *before* releasing the one it replaces, so it got a null and drew
nothing from then on. The guard was also unnecessary: only an attached view
runs a timer, only the visible window gets mouse messages, and an edit
drained by either view reaches the controller exactly once. `createView` now
always returns a fresh view and the controller tracks all live ones.

And a view filled its copy of the frame from the rectangle ring alone.
Rectangles say what *changed*, and a reopened editor showing a panel nobody
touched changes nothing - so a view that waits for rectangles waits forever.
A view that has no frame of its own now takes the whole framebuffer instead,
under the same seqlock.

The flag guarding that had to mean the right thing, and at first it did not.
It was set by the paint path, so it read as "this view has drawn something"
rather than "this view holds a frame" - and a window is asked to paint the
moment it is created, well before its first timer tick. The view answered
that first request with its empty buffer, marked itself painted, and never
took the full copy at all. It is set by the sampling path now, which is the
only place that can honestly claim a frame exists.

Attaching also invalidates the whole screen engine-side. That is not what
fixes the above - the view's own fallback is sufficient there, confirmed by
disabling one and re-running the other - but it covers the case the view
cannot: after a sidecar restart the framebuffer is freshly zeroed, and then
only the engine can put the pixels back.

Two notes on where the coverage sits. Gestures becoming automation is
asserted by the smoke test rather than the matrix, because Lua cannot click
a panel; the matrix asserts the half Lua can see, which is that a real host
opens and closes a real window and the audio is untouched. And "zero
underruns" is enforced as sample-exact parity rather than as a counter: the
renders are offline, where the engine is never idle and therefore never
ticks the UI at all, and identical PCM is the stronger statement anyway.

## Deferred

- Per-script custom panels (the panel-module replacement path above).
- The shared knob widget, meters and scope taps, and host keyboard focus.
- User-resizable or zoomable editors.
- A dedicated UI sidecar process (kept possible, not built).
- macOS, with the rest of the platform work.
