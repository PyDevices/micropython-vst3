"""The editor's lifecycle inside the engine process.

The bootstrap calls `start()` once and hands the returned `tick` to
`vstaudio.run()`, which calls it from the engine's housekeeping step - the
moment where there is no audio to render. Everything the editor costs is
inside that call.

Three things are deliberate here.

Nothing is built until the host actually opens the editor. An instance that is
never opened pays for an unmapped region and one `editor_open()` read per
housekeeping pass; no LVGL, no panel, no allocations.

The app never owns a timer that fires by itself. `multimer`'s `polling`
backend only advances when something pumps it, and `App.poll()` is what pumps
it, so LVGL's tick, its task handler and the display refresh all happen inside
this module's `tick()` and nowhere else. That is the whole reason the panel can
share a heap with an audio renderer without a callback landing mid-render.

A panel that raises is torn down rather than retried. The failure is recorded
for the view to render, and audio carries on: a broken editor must be visible,
not fatal, and not a source of repeated exceptions in the render loop.
"""

import sys

import vstaudio
import vstui


def start(mapping_name, script_path=None):
    """Open the UI mapping. Returns an `Editor`, or None when there is none.

    A missing or unreadable mapping is not an error: the plug-in may not have
    been able to create one, and an instance without an editor still plays.
    """
    if not mapping_name or not vstui.open(mapping_name):
        return None
    return Editor(script_path)


class Editor:
    def __init__(self, script_path):
        self._script_path = script_path
        self._app = None
        self._panel = None
        self._adapter = None
        self._pump = None
        self._failed = False
        self._was_open = False

    # ---- the engine's housekeeping step --------------------------------

    def tick(self):
        if self._failed:
            return
        if not vstui.editor_open():
            if self._was_open:
                self._on_close()
            return
        if not self._was_open:
            self._was_open = True
        try:
            if self._app is None:
                self._setup()
            if self._panel is None:
                self._build_panel()
            self._adapter.tick()
            # Pump the timer provider, not App.poll(). They look
            # interchangeable and are not: App.poll() drains every registered
            # device itself, and the host-event device is the one display_driver
            # drains through its own pump on the way to LVGL's indevs. Calling
            # poll() here consumed the clicks before LVGL ever saw them, which
            # is also why nothing does it on the desktop - display_driver.main()
            # calls app.stop_timer(), so the app's own service tick is gone by
            # the time any of this is wired and the pump is the only reader.
            self._pump()
        except Exception as exc:  # noqa: BLE001 - the panel must not be fatal
            self._fail(exc)

    def script_reloaded(self, script_path=None):
        """The instance script was replaced. Rebuild the panel around it.

        Labels and the patch list come from the script, so keeping the old
        panel would leave the editor describing code that is no longer
        running. Only the widgets are rebuilt: LVGL, the board and the app
        belong to the process, not to the script, and tearing them down would
        make a reload cost what the first open cost.
        """
        if script_path is not None:
            self._script_path = script_path
        self._release_panel()
        # A panel that failed against the old script deserves a fresh try
        # against the new one - editing the script is how a user fixes it.
        self._failed = False

    def stop(self):
        self._release_panel()
        app = self._app
        self._app = None
        if app is None:
            return
        try:
            app.request_quit()
        except Exception:
            pass

    # ---- construction ---------------------------------------------------

    def _setup(self):
        import displaydev

        # Must be set before anything imports multimer: `polling` is the only
        # backend that never delivers a callback on its own.
        displaydev.env_set("MULTIMER_BACKEND", "polling")

        import appdev

        import vst_board_config

        width, height = vstui.size()
        vst_board_config.configure(width, height)
        # Constructing the app before importing display_driver is what makes
        # this board the active one: display_driver adopts `App.current()` and
        # only falls back to importing a module literally named board_config
        # when there is no app at all.
        self._app = appdev.App(vst_board_config)

        import display_driver

        # The tested two-axis mapping: the axis parallel to the control
        # adjusts it, the perpendicular one steps between controls. Signs are
        # per-input-path facts; these are calibrated against the native deltas
        # the view packs into mpvst_ui_input, and tests/smoke_host pins them.
        display_driver.set_wheel_mapping(
            adjust_axis="h", adjust_sign=1, navigate=True, navigate_sign=-1
        )

        from multimer import auto as timer

        self._pump = timer.pump
        # Anything display_driver queued for "when the loop starts" has to be
        # armed by hand, because in this process the loop never starts: there
        # is no run(), no host loop, and no timer that fires by itself.
        self._app.arm_async_refresh()

    def _build_panel(self):
        import lvgl as lv

        from vst_panel import EngineAdapter, build

        lv.screen_active().clean()
        group = lv.group_get_default()
        if group is not None:
            group.remove_all_objs()
        self._adapter = EngineAdapter(vstui, self._script_path)
        vstaudio.observe(self._observe)
        self._panel = build(self._adapter, group=group)
        vstui.error(vstui.ERROR_NONE)

    def _observe(self, event_type, channel, note_id, data0, value0, value1,
                 sample_position):
        """Mirror host-driven parameter state into the panel.

        This is why `vstaudio.observe` exists: `on_event` belongs to the
        script, and the panel must not displace it to find out that
        automation moved a macro.
        """
        adapter = self._adapter
        if adapter is None:
            return
        if event_type == vstaudio.EVENT_PARAMETER:
            adapter.note_parameter(data0, value0)
        elif event_type == vstaudio.EVENT_PROGRAM_CHANGE:
            adapter.note_program(data0)

    # ---- teardown --------------------------------------------------------

    def _on_close(self):
        """The host detached the view. Stop painting; keep the panel.

        Rebuilding LVGL on every open would make reopening an editor cost
        what opening the first one cost, and the panel's state is exactly the
        state the host is about to echo back anyway. What must not survive is
        an unfinished gesture: an automation write left open across a close
        would strand the host's lane.
        """
        self._was_open = False
        if self._adapter is not None:
            try:
                self._adapter.close_all()
            except Exception:
                pass

    def _fail(self, exc):
        self._failed = True
        sys.print_exception(exc)
        try:
            vstui.error(vstui.ERROR_PANEL_FAILED)
        except Exception:
            pass
        self._release_panel()

    def _release_panel(self):
        """Drop the widgets and the adapter, keeping LVGL and the app."""
        self._was_open = False
        try:
            vstaudio.observe(None)
        except Exception:
            pass
        if self._adapter is not None:
            try:
                self._adapter.close_all()
            except Exception:
                pass
        self._panel = None
        self._adapter = None
