"""Run an `audioeffects` component inside the sidecar.

The instrument twin of this is `mpvst_instrument_adapter`, and the split is the same:
the effect library lives in audiocomponents and knows nothing about this
plug-in, so this module is the one place that knows both halves. An effect
factory takes the host input and sample rate and returns an object exposing
an `output` to pull from, which is exactly what `vstaudio.input()` and
`vstaudio.output()` provide.

    import mpvst_effect_adapter
    mpvst_effect_adapter.run("TapeDelay")

That line is what the plug-in builds for a named effect class, from the entry
`moduleinfo.json` carries for it - there are no generated shim files.

The adapter calls `audioeffects.create(name, source, sample_rate, **kwargs)`;
it does not instantiate an effect class directly. That package factory is the
audioif component factory boundary.

Macros work the same way they do for instruments - normalized 0.0-1.0 on the
wire, MIDI 0-127 to the library. The provider declares an empty macro surface
explicitly when an effect has no knobs; this consumer remains tolerant and
simply does not wire the parameter path for one. Such an effect still
processes audio, while a provider with macros receives those events here.
"""

import sys

import vstaudio

# What the last `attach` built, and where it came from. The editor panel reads
# these for its labels and patch list, the same way it does for instruments.
effect = None
module_name = None
class_name = None

# The node the engine is currently pulling from, so `rebind()` can tell a
# rebuilt graph from an unchanged one without asking the engine.
bound_output = None


def bind(node):
    """Hand `node` to the engine and remember that we did."""
    global bound_output
    bound_output = node
    vstaudio.output(node)


def _midi_byte(value):
    """Convert a normalized VST scalar to the provider's MIDI data byte."""
    value = max(0.0, min(1.0, float(value)))
    return int(value * 127.0 + 0.5)


def attach(factory, **kwargs):
    """Build a component through its factory around the host input bus."""
    global effect
    effect = factory(vstaudio.input(), vstaudio.sample_rate(), **kwargs)

    labels = getattr(effect, "MACRO_LABELS", ())
    patches = getattr(effect, "PATCHES", {})
    if labels or patches:
        # A component may REBUILD its graph when a setting changes, and then
        # `effect.output` is a different object from the one the engine was
        # handed - the old node is still reachable from our reference but
        # nothing feeds it any more, so the plug-in goes silent for good.
        # Phaser and Vibrato both do this, and the host pushes every macro
        # at 0.5 the moment a script loads, so it happened before a note was
        # ever played. Rebinding costs one identity test per event and is
        # safe mid-stream: `vstaudio.output()` swaps the root pointer and
        # resets the pull cursor without resetting the graph.
        def rebind():
            global bound_output
            current = effect.output
            if current is not bound_output:
                bound_output = current
                vstaudio.output(current)

        def dispatch(event_type, channel, note_id, data0, value0, value1,
                     sample_position):
            # Effects take no notes. A parameter change is the only event
            # that means anything here, and patches are the one other
            # component event an effect may consume.
            if event_type == vstaudio.EVENT_PARAMETER:
                if 0 <= data0 < len(labels):
                    effect.set_macro(data0, value0 * 127.0, channel, note_id,
                                     sample_position)
            elif event_type == vstaudio.EVENT_PROGRAM_CHANGE:
                effect.program_change(data0, channel, note_id,
                                      sample_position)
            elif event_type == vstaudio.EVENT_PITCH_BEND:
                effect.pitch_bend(int(max(0.0, min(1.0, float(value0))) *
                                  16383.0 + 0.5), channel, sample_position)
            elif event_type == vstaudio.EVENT_CONTROL_CHANGE:
                effect.control_change(data0, _midi_byte(value0), channel,
                                      sample_position)
            elif event_type == vstaudio.EVENT_CHANNEL_PRESSURE:
                effect.channel_pressure(_midi_byte(value0), channel,
                                        sample_position)
            elif event_type == vstaudio.EVENT_POLY_PRESSURE:
                effect.poly_pressure(data0, _midi_byte(value0), channel,
                                     note_id,
                                     sample_position)
            rebind()

        vstaudio.on_event(dispatch)

    bind(effect.output)
    return effect


def run(name, **kwargs):
    """Import `audioeffects` fresh and attach the effect called `name`."""
    global module_name, class_name
    # Same reason as the instrument adapter: a reload re-execs the script, but
    # an import is cached, so an edit to the library would not be picked up
    # without dropping the whole package first.
    for cached in list(sys.modules):
        if cached == "audioeffects" or cached.startswith("audioeffects."):
            del sys.modules[cached]
    import audioeffects

    def factory(source, sample_rate, **options):
        return audioeffects.create(name, source, sample_rate, **options)

    module_name = "audioeffects"
    class_name = name
    return attach(factory, **kwargs)
