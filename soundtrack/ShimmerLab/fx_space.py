"""A send-style space, loaded from the shared effects library.

This rack used to live here whole; `audioeffects` now ships it as
`AirSpace` (pydevices-audioeffects 0.1.1), ported from this very file
with patch 0 verified numerically identical. What remains is the same
loader shape the plug-in synthesizes for any library effect, plus the
static declarations a host reads out of an embedded source without
importing anything.
"""

NAME = "fx_space"
DISPLAY_NAME = "Air Space"
CATEGORIES = ("Effect Rack", "Reverb")
VERSION = "0.0.1"
VENDOR = "PyDevices"
MACRO_LABELS = ("Space", "Echo", "Tone")
MACRO_MODES = {0: "UNIPOLAR", 1: "UNIPOLAR", 2: "UNIPOLAR"}
PATCHES = {0: ("Air Space", (64, 53, 85))}

import mpvst_effect_adapter

mpvst_effect_adapter.run("AirSpace")
