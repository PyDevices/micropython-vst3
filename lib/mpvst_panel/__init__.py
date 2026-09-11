"""The editor's Python half: a generic panel and the adapter it edits through.

Kept host-neutral on purpose. `panel` imports only LVGL and `panel_adapter` imports
nothing at all from the engine, so the pair can graduate to a sibling repo as
a portable PyDevices example without surgery. It starts here.
"""

from .panel_adapter import EngineAdapter
from .panel import Panel, build

__all__ = ["EngineAdapter", "Panel", "build"]
