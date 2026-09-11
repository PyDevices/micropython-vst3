# Icon art

`mpvst.ico` is a **placeholder**, and is drawn to look like one: one flat
colour, the letters knocked out of a rounded tile so the shape still reads at
16 px. It exists so the icon mechanism could be finished and exercised before
anyone commits to a mark. [make-placeholder-icon.py](make-placeholder-icon.py)
is how it was drawn; nothing in the build runs it, and nothing downstream cares
where the `.ico` came from. Replacing it is one file.

Two Windows surfaces read this one file, and both of them used to carry
somebody else's mark:

- **The sidecar executable.** `scripts/build-micropython-engine.sh` passes it to
  `build_mp.sh --icon`, which rewrites `ports/windows/micropython.rc` for the
  build and restores it afterwards. Without it the engine wears MicroPython's
  logo.
- **The bundle folder in Explorer.** `src/plugin/CMakeLists.txt` sets
  `SMTG_PACKAGE_ICON_PATH`, which the VST3 SDK copies into the bundle root as
  `PlugIn.ico` with a `desktop.ini` beside it. Without it the SDK defaults to
  Steinberg's VST logo.

Neither is the installer's own icon, which is deliberately NSIS stock.

To replace it: put a real `.ico` here under the same name. It must be a true
Windows icon - `build_mp.sh` checks the `00 00 01 00` header and refuses a
renamed `.png` rather than letting `windres` fail deep in a build. Ship at
least 16, 32, 48 and 256 px; the small sizes are what a taskbar and a file
list actually show.
