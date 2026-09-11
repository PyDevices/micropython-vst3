"""The editor as an ordinary PyDevices board.

`vstui` gives the engine a framebuffer, an input queue and an edit queue in
shared memory. This turns those into the board contract every PyDevices board
implements - a `display_drv` and a source of host events - so everything above
this line is stock: `appdev.App` registers the devices, `display_driver` wires
LVGL to them exactly as it does on a panel with a touchscreen and an encoder,
and the panel itself never imports `vstui` or `vstaudio` at all.

Two rules are load-bearing enough to state here.

`share_framebuffer` stays False. That flag tells the LVGL bridge to hand LVGL
a standing pointer into this driver's own buffer and render into it directly
(`DISPLAY_RENDER_MODE.DIRECT`, no `blit_rect` call at all), which is right for
scanout memory owned by one process and wrong for a seqlock-protected region
another process reads: the odd/even toggle and the rectangle publish have to
happen at one deliberate copy step, not smeared through LVGL's render and
flush internals. Leaving it False keeps the default PARTIAL path, where LVGL
renders into its own small draw-buffer pair and calls `blit_rect` per band -
which is exactly the seam `vstui.blit` hooks.

And the wheel arrives as a `MOUSEWHEEL` host event rather than through
`encoder_read`. The board contract's encoder is a single absolute position, so
it cannot express two axes; a host event carries both, which is what the
two-axis mapping needs. It also means the whole canonical wheel path in
`display_driver` applies unchanged, `set_wheel_mapping` included.
"""

import events
from displaydev import DisplayDriver

import vstui

# The engine's wheel deltas are already in notch units (Win32's WHEEL_DELTA,
# which the X11 path scales to match), so one notch is one LVGL encoder step.
_NOTCH = float(vstui.WHEEL_NOTCH)


class VstDisplay(DisplayDriver):
    """RGB565 into the shared framebuffer, one published rectangle per band."""

    # See the module docstring: the seqlock needs a single deliberate copy.
    share_framebuffer = False
    # Every blit publishes itself, so there is no separate present step and
    # nothing for the app's refresh timer to do.
    needs_refresh = False

    def __init__(self, width, height, quiet=True):
        self._width = width
        self._height = height
        self._requires_byteswap = False
        self._rotation = 0
        self.color_depth = 16
        super().__init__(quiet=quiet)

    def init(self):
        pass

    def blit_rect(self, buf, x, y, w, h):
        vstui.blit(buf, x, y, w, h)
        return (x, y, w, h)

    def fill_rect(self, x, y, w, h, c):
        # LVGL never calls this - it renders into its own draw buffers and
        # flushes through blit_rect - but the driver contract includes it, and
        # a caller that reaches for it should not get a silent no-op.
        row = (c & 0xFFFF).to_bytes(2, "little") * w
        vstui.blit(bytearray(row * h), x, y, w, h)
        return (x, y, w, h)

    def pixel(self, x, y, c):
        return self.fill_rect(x, y, 1, 1, c)

    def show(self, _timer=None):
        pass


class _HostEvents:
    """Drain `vstui.poll()` into the PyDevices events LVGL already reads."""

    def __init__(self):
        self._buttons = (0, 0, 0)
        self._position = (0, 0)

    def __call__(self):
        pending = vstui.poll()
        if not pending:
            return []
        out = []
        for kind, buttons, x, y, wheel_v, wheel_h in pending:
            if kind == vstui.INPUT_WHEEL:
                if wheel_v == 0 and wheel_h == 0:
                    continue
                # Both the integer and the precise pair are filled from the
                # same numbers, so no consumer has to guess which one carries
                # real data - the ambiguity that costs SDL builds so much
                # simply does not exist on this path.
                out.append(
                    events.Wheel(
                        events.MOUSEWHEEL,
                        False,
                        int(wheel_h // vstui.WHEEL_NOTCH),
                        int(wheel_v // vstui.WHEEL_NOTCH),
                        wheel_h / _NOTCH,
                        wheel_v / _NOTCH,
                        False,
                        None,
                    )
                )
                continue

            position = (int(x), int(y))
            pressed = (1 if buttons & 1 else 0, 0, 0)
            if kind == vstui.INPUT_POINTER_DOWN:
                self._buttons = pressed
                self._position = position
                out.append(
                    events.Button(events.MOUSEBUTTONDOWN, position, 1, False, None)
                )
            elif kind == vstui.INPUT_POINTER_UP:
                self._buttons = (0, 0, 0)
                self._position = position
                out.append(
                    events.Button(events.MOUSEBUTTONUP, position, 1, False, None)
                )
            elif kind == vstui.INPUT_POINTER_MOVE:
                rel = (position[0] - self._position[0], position[1] - self._position[1])
                self._buttons = pressed
                self._position = position
                out.append(
                    events.Motion(
                        events.MOUSEMOTION, position, rel, self._buttons, False, None
                    )
                )
        return out


display_drv = None
get_events = None
# The sidecar drives LVGL from the engine's own housekeeping step, so the app
# must never create a timer that fires on its own. `polling` is the multimer
# backend that only advances when something pumps it, which App.poll() does.
timer_async = False


def configure(width=None, height=None):
    """Declare the logical size and build the board. Call once, before
    importing `display_driver`."""
    global display_drv, get_events
    if width is None or height is None:
        width, height = vstui.DEFAULT_WIDTH, vstui.DEFAULT_HEIGHT
    vstui.configure(width, height)
    display_drv = VstDisplay(width, height)
    get_events = _HostEvents()
    return display_drv
