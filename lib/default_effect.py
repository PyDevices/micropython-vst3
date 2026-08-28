"""The effect the Fx script host runs when you have not given it one.

It passes its input through unchanged, which is the right thing for an empty
effect slot to do and the right thing to start from. Copy it somewhere of your
own, point MPVST_SCRIPT_PATH at the copy, and edit - the plug-in re-reads that
file every time you toggle Reload Script.

The whole of the pass-through is the last line. `vstaudio.input()` is the audio
the host sends this track; `vstaudio.output()` is what the host gets back. To
make it do something, build a chain between the two:

    import audioeffects
    delay = audioeffects.create("TapeDelay", vstaudio.input(),
                                vstaudio.sample_rate())
    vstaudio.output(delay.output)

`NAME` is what the editor's header shows. Change it in your copy - a plug-in
that says "DEFAULT - passthrough only" while running your code is confusing in
exactly the way the name is meant to prevent.

To have macro sliders, declare them - that is the whole contract, and it is
the same `MACRO_LABELS` an audioeffects class or an audioinstruments module
declares. Undeclared means the plug-in has none, and the editor draws none
rather than sixteen that do nothing:

    MACRO_LABELS = ("Mix", "Time")

    def handle_event(event_type, channel, note_id, data0, value0, value1,
                     sample_position):
        if event_type == vstaudio.EVENT_PARAMETER:
            # data0 is the zero-based macro index and value0 is 0.0-1.0.
            delay.set_macro(data0, value0 * 127.0)

    vstaudio.on_event(handle_event)

An effect gets no notes, so EVENT_PARAMETER is the only event worth reading
here. `lib/default_instrument.py` is the instrument-side counterpart and shows
the note handling instead.
"""

import vstaudio

# What the editor calls this instance. Every script may declare one, and this
# one says what it is so nobody wonders which effect they are looking at: an
# empty slot, not something they chose. Rename it in your copy.
NAME = "default_effect"
DISPLAY_NAME = "DEFAULT - passthrough only"
MACRO_LABELS = ()
MACRO_MODES = {}
PATCHES = {0: ("Default", ())}

vstaudio.output(vstaudio.input())
