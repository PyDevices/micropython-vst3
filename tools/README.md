# Tools

Developer-workflow and test infrastructure for the plug-in and the
shared `lib/effects/` and `lib/instruments/` libraries: things you run
repeatedly while developing, not maintainer/CI automation. For fetching
dependencies, building the engine, packaging a release, or bootstrapping
a fresh clone (including REAPER), see [`../scripts/`](../scripts/README.md).

## Composing a piece

`../soundtrack/` is example content, not infrastructure - it might be
renamed, restructured, or replaced independently of this. Two scripts
here can resolve and render a piece with no DAW involved at all - neither
one imports or knows about REAPER:

- **`piece.py`** - resolves a piece name (case-insensitive) to
  its `composition.py` and `instruments/` under `../soundtrack/`. The one
  place that hardcodes that location.
- **`render_preview.py [--piece NAME] [out.wav] [--stems DIR]`**
  - offline render through `harness.py` (needs the `audioif` wheel's venv:
  this repo's own `.venv` if set up - `pip install pydevices-audioif` from
  TestPyPI, plus `numpy` - else a sibling `audioif` checkout's, e.g.
  `../../audioif/.venv/bin/python`); reports peaks, RMS per section, and
  simultaneous-track counts.

Turning a piece into a real REAPER project, and driving REAPER itself, is
a separate, deletable concern - see [`../reaper/README.md`](../reaper/README.md)
and the root [`../reaper.sh`](../reaper.sh) entry point.

## Testing

- **`harness.py`** and **`vstaudio.py`** - a CPython stand-in for the
  sidecar, built on the `audioif` wheel (the same `synthio`/`audiocore`
  DSP the real engine runs). Lets any instrument or effect script run
  without the compiled engine or a VST3 host, in milliseconds instead of
  the seconds a full plug-in load takes. `harness.py` provides
  `InstrumentRun` and `EffectRun`; `vstaudio.py` is the shim module
  scripts see as `import vstaudio`. A sibling `audioif` checkout, when
  present, is preferred over any installed wheel.
- **`test-instruments-lib.py`** - runs every `lib/instruments/*.py`
  script against `harness.py`: sweeps each declared macro through
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
The two scripts above take a `smoke_host` path because they drive
[`../tests/smoke_host/`](../tests/) - a minimal C++ VST3 host that loads
the built bundle directly (no DAW) and runs one script through the real
processor. It lives with the tests because it is built only under
`BUILD_TESTING`; `ctest` passes its path automatically, and you only name
it by hand when running these two scripts yourself.

The one test that needs a real DAW - FX chain add/remove, parameter
automation, project save/reload, macro resync - lives in
[`../reaper/matrix/`](../reaper/README.md) instead of here, for the same
reason `tools/` and `reaper/` are split at all: everything in this
directory runs with no DAW.

None of the `preview`-based tools prove a script sounds like the
hardware it's named after, or like anything in particular - only that it
doesn't crash and isn't silent. Hearing it is still on you.
