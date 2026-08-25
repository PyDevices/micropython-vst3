# Tools

Build, packaging, and test infrastructure for the plug-in and the shared
`lib/effects/` and `lib/instruments/` libraries.

## Build & package

- **`fetch-vst3-sdk.sh`** - downloads the VST3 SDK into `.deps/vst3sdk`.
- **`build-micropython-engine.sh [--port windows|unix]`** - builds the
  MicroPython sidecar engine (defaults to the Windows engine, the
  shipping product; `--port unix` builds the same module set for Linux).
- **`package-windows.sh`** / **`package-linux.sh`** - assemble the
  release archive for each platform's VST3 bundle.

## Testing

- **`preview/`** - a CPython stand-in for the sidecar, built on the
  `audioif` wheel (the same `synthio`/`audiocore` DSP the real engine
  runs). Lets any instrument or effect script run without the compiled
  engine or a VST3 host, in milliseconds instead of the seconds a full
  plug-in load takes. `harness.py` provides `InstrumentRun`; `vstaudio.py`
  is the shim module scripts see as `import vstaudio`.
- **`test-instruments-lib.py`** - runs every `lib/instruments/*.py`
  script against `preview/`: sweeps each declared macro through
  `0.0/0.5/1.0` under held notes, then checks a fresh instance produces
  audible output at default settings. No engine or VST3 host needed;
  a full pass over all 53 scripts takes single-digit seconds. Registered
  as the `mpvst_instruments_library` ctest.
- **`test-instruments-plugin.py <smoke_host> <bundle.vst3>`** - the same
  scripts through the real packaged MicroPython Instrument VST3 class
  (real protocol, real macro/state handling), via `smoke_host`'s
  `--instrument-script` probe. Slower, higher-fidelity; the final gate.
  Registered as `mpvst_instruments_plugin`.
- **`test-effects-lib.py <smoke_host> <bundle.vst3>`** - the equivalent
  suite for `lib/effects/`: builds each class from `vstaudio.input()` and
  asserts the behavior it promises (squeezes, mutes, or passes a
  quiet/loud sine pair) through the real Effect class. Registered as
  `mpvst_effects_library`.
- **`smoke_host/`** - the C++ host used by every `--expect-*`/`--*-script`
  probe above and by the ctest suite in `../tests/`. Loads the built
  bundle directly (no DAW) and drives it through the real VST3 processor.
- **`check-cross-platform-parity.sh`** - renders a fixed score through
  both platforms' real sidecars and compares the PCM byte for byte.
- **`daw-matrix/`** - drives the instrument+effect chain through a real
  copy of REAPER with no GUI interaction (`run-reaper-matrix.sh`), for
  the things only a real DAW host can exercise: FX chain add/remove,
  parameter automation, project save/reload, macro resync. See
  `run-reaper-matrix.sh`'s header for the platform-specific setup.

None of the `preview`-based tools prove a script sounds like the
hardware it's named after, or like anything in particular - only that it
doesn't crash and isn't silent. Hearing it is still on you.
