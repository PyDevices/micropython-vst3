"""What the panel is allowed to know about the instance it is editing.

The panel gets one of these and nothing else: no `vstui`, no `vstaudio`, no
protocol. That is what keeps the panel runnable on a desktop under
`lvgl-python` against a mock of this class, which is both the development loop
and the portability requirement.

Values here are MIDI 0-127, the units an instrument, a keyboard, a sequencer
and a saved patch all speak. The protocol speaks normalized 0.0-1.0, which is
what the VST3 parameter API wants. The conversion happens at this seam, once,
the same way `mpvst_adapter` does it for audio events - and it is a multiply,
not a quantization, so a host automating a macro with more than seven bits of
resolution keeps every bit of it on the way back in.
"""

# Permanent parameter IDs, matching src/plugin/source/parameters.h. The panel
# never sees these; it names controls, and this class names parameters.
BYPASS = 0
RELOAD = 1
PATCH = 4
FIRST_MACRO = 100
MACRO_COUNT = 16
PATCH_COUNT = 128

# How long a control must sit still before its gesture is closed. A slider
# drag and a burst of wheel ticks are both "one edit" to a host's automation
# lane, and both arrive as a stream of value changes with no reliable end
# marker, so quiescence is what ends them. Long enough to ride out the gap
# between two deliberate wheel notches, short enough that letting go of a
# slider records an edit that ends when it looks like it ended.
GESTURE_IDLE_MS = 180


class EngineAdapter:
    """Bridges the panel to the engine's shared-memory edit and event paths."""

    def __init__(self, ui, script_path=None, ticks_ms=None):
        self._ui = ui
        self._ticks_ms = ticks_ms
        self._open = {}
        self._values = {}
        self._listeners = []
        self.script_name = _script_name(script_path)
        self.macro_labels = _macro_labels()
        # How many of the sixteen this instance actually uses. The parameter
        # space never changes - a host that automated macro 12 keeps doing so
        # whatever the panel draws - but a control that moves nothing is worse
        # than no control, so the panel stops at what was declared.
        self.macro_count = len(self.macro_labels)
        self.macro_values = [64] * MACRO_COUNT
        self.patches = _patch_names()
        self.patch_index = 0
        self.bypass = False
        self.engine_ready = True
        self.engine_error = 0

    # ---- what the engine tells us -------------------------------------

    def on_external_change(self, callback):
        """Register `callback(kind, index, value)` for host-driven changes.

        The panel treats incoming parameter state as truth. That is stable
        rather than circular because the echo equals what the panel already
        shows: the host sends back the value the panel just published.
        """
        self._listeners.append(callback)

    def note_parameter(self, index, normalized):
        """A macro moved somewhere else - automation, a reload replay, a
        controller. Called from the engine's event observer."""
        if index < 0 or index >= MACRO_COUNT:
            return
        value = _to_midi(normalized)
        if self.macro_values[index] == value:
            return
        self.macro_values[index] = value
        self._notify("macro", index, value)

    def note_program(self, index):
        if index < 0 or index >= PATCH_COUNT or self.patch_index == index:
            return
        self.patch_index = index
        self._notify("patch", index, index)

    def _notify(self, kind, index, value):
        for listener in self._listeners:
            listener(kind, index, value)

    # ---- what the panel tells the engine ------------------------------

    def set_macro(self, index, value):
        self.macro_values[index] = value
        self._perform(FIRST_MACRO + index, value / 127.0)

    def set_patch(self, index):
        self.patch_index = index
        # A patch selector is a discrete choice, not a gesture: publish it as
        # a complete edit so the host records one change rather than waiting
        # out a quiescence timer for something that will never move again.
        self._discrete(PATCH, index / float(PATCH_COUNT - 1))

    def set_bypass(self, enabled):
        self.bypass = bool(enabled)
        self._discrete(BYPASS, 1.0 if enabled else 0.0)

    def request_reload(self):
        # The processor latches a rising edge and then fades, so the button
        # has to return to zero for the next press to be seen at all.
        self._discrete(RELOAD, 1.0)
        self._discrete(RELOAD, 0.0)

    def tick(self):
        """Close gestures that have gone quiet. Called every UI tick."""
        if not self._open:
            return
        now = self._now()
        for parameter in list(self._open):
            if now - self._open[parameter] >= GESTURE_IDLE_MS:
                del self._open[parameter]
                self._ui.edit(self._ui.EDIT_END, parameter, self._last(parameter))

    def close_all(self):
        """End every open gesture immediately - editor closing, panel going
        away. Leaving one open would strand an automation write in the host."""
        for parameter in list(self._open):
            del self._open[parameter]
            self._ui.edit(self._ui.EDIT_END, parameter, self._last(parameter))

    # ---- gesture bookkeeping -------------------------------------------

    def _perform(self, parameter, normalized):
        normalized = _bounded(normalized)
        self._values[parameter] = normalized
        if parameter not in self._open:
            self._ui.edit(self._ui.EDIT_BEGIN, parameter, normalized)
        self._open[parameter] = self._now()
        self._ui.edit(self._ui.EDIT_PERFORM, parameter, normalized)

    def _discrete(self, parameter, normalized):
        normalized = _bounded(normalized)
        self._values[parameter] = normalized
        self._ui.edit(self._ui.EDIT_BEGIN, parameter, normalized)
        self._ui.edit(self._ui.EDIT_PERFORM, parameter, normalized)
        self._ui.edit(self._ui.EDIT_END, parameter, normalized)
        self._open.pop(parameter, None)

    def _last(self, parameter):
        return self._values.get(parameter, 0.0)

    def _now(self):
        if self._ticks_ms is None:
            from multimer import ticks_ms

            self._ticks_ms = ticks_ms
        return self._ticks_ms()


def _bounded(value):
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _to_midi(normalized):
    value = int(_bounded(normalized) * 127.0 + 0.5)
    return 0 if value < 0 else (127 if value > 127 else value)


def _script_name(script_path):
    """What to call this instance in the panel's header.

    Read off the module or class this instance is playing, which is loaded in
    this same interpreter and declares its own NAME. A materialised script is
    written to a temporary file named after nothing in particular, so the
    filename is only worth using when there is no declaration to read - a
    hand-written sketch that never went through either adapter.
    """
    declared = _declared("DISPLAY_NAME") or _declared("NAME")
    if declared:
        return declared
    if not script_path:
        return "script"
    name = script_path.replace("\\", "/").rsplit("/", 1)[-1]
    return name[:-3] if name.endswith(".py") else name


def _macro_labels():
    """The macros this instance declares, named. Missing means none drawn.

    Provider components declare the tuple: on the module for an instrument,
    on the class for an effect, and at module level in a bare script. This
    consumer also accepts a missing field for compatibility and draws none;
    `NAME` remains the only metadata it must require.
    """
    declared = _declared("MACRO_LABELS")
    labels = []
    for index, text in enumerate(declared or ()):
        if index >= MACRO_COUNT:
            break
        labels.append(str(text) if text else "Macro {:02d}".format(index + 1))
    return labels


def _patch_names():
    """The patches this instance declares, named. Missing means none drawn.

    Providers declare PATCHES. This consumer tolerates a missing declaration,
    so a program change selects from nothing and no list is drawn. The Patch
    parameter itself stays permanent, and a host may still automate it.
    """
    declared = _declared("PATCHES")
    if not isinstance(declared, dict) or not declared:
        return []
    count = min(max(declared) + 1, PATCH_COUNT)
    names = ["Patch {:03d}".format(index + 1) for index in range(count)]
    for index, entry in declared.items():
        if 0 <= index < count and entry:
            names[index] = str(entry[0])
    return names


def _declared(name):
    """What this instance declared for `name`, wherever it declared it.

    Three places, because there are three kinds of plug-in and the library's
    own shape decides which: an instrument is one plug-in per module so it
    declares at module level; an effect file holds several classes so each
    declares on itself; and a script that went through neither adapter is
    exec'd into a namespace of its own and declares there. The name is the
    same in all three - MACRO_LABELS is MACRO_LABELS - which is the point.
    """
    import sys

    try:
        import mpvst_adapter
        module = sys.modules.get(getattr(mpvst_adapter, "module_name", None))
        if module is not None:
            return getattr(module, name, None)
    except ImportError:
        pass

    try:
        import mpvst_effect_adapter
        package = sys.modules.get(
            getattr(mpvst_effect_adapter, "module_name", None))
        owner = getattr(mpvst_effect_adapter, "class_name", None)
        if package is not None and owner:
            return getattr(getattr(package, owner, None), name, None)
    except ImportError:
        pass

    try:
        import mpvst_script
        if mpvst_script.namespace:
            return mpvst_script.namespace.get(name)
    except ImportError:
        pass
    return None
