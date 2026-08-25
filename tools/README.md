# Tools

Developer-workflow and test infrastructure for the plug-in and the
shared `lib/effects/` and `lib/instruments/` libraries: things you run
repeatedly while developing, not maintainer/CI automation. For fetching
dependencies, building the engine, packaging a release, or bootstrapping
a fresh clone (including REAPER), see [`../scripts/`](../scripts/README.md).

## Composing a piece

`../soundtrack/` is example content, not infrastructure - it might be
renamed, restructured, or replaced independently of this. The tooling
that generates, renders, and verifies a piece lives here instead:

- **`piece/piece.py`** - resolves a piece name (case-insensitive) to its
  `composition.py` and `instruments/` under `../soundtrack/`. The one
  place that hardcodes that location.
- **`piece/generate_project.py [--piece NAME] [out.RPP]`** - writes a
  complete REAPER project with every track's instrument script embedded
  directly in synthesized VST3 state, so it opens with no build pass.
- **`piece/render_preview.py [--piece NAME] [out.wav] [--stems DIR]`** -
  offline render through `preview/` (needs the `audioif` wheel's venv,
  e.g. `../../audioif/.venv/bin/python`); reports peaks, RMS per section,
  and simultaneous-track counts.
- **`piece/verify_song.py --piece NAME <bounce.wav> <preview.wav>`** -
  compares a REAPER bounce against the offline preview section by section.
- **`piece/launch.sh [--play|--render] [--piece NAME]`** - drives REAPER
  headlessly to either play a piece through the speakers or bounce and
  verify it; see the script's header for the Windows path layout it
  assumes.
- **`piece/reaper/`** - the self-deleting autoplay/verify Lua scripts
  `launch.sh` installs as REAPER's startup script.

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
- **`daw-matrix/`** - drives the instrument+effect chain through a real
  copy of REAPER with no GUI interaction (`run-reaper-matrix.sh`), for
  the things only a real DAW host can exercise: FX chain add/remove,
  parameter automation, project save/reload, macro resync. See
  `run-reaper-matrix.sh`'s header for the platform-specific setup.

None of the `preview`-based tools prove a script sounds like the
hardware it's named after, or like anything in particular - only that it
doesn't crash and isn't silent. Hearing it is still on you.
