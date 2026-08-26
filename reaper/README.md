# reaper/

Everything needed to drive a real copy of REAPER, and nothing else. This
directory and the root [`../reaper.sh`](../reaper.sh) entry point are a
single deletable unit: the plug-in, `lib/instruments/`, `lib/effects/`,
and the composition/preview tooling in
[`../tools/`](../tools/README.md) all work with these two
paths removed. Nothing outside `reaper/` imports or sources anything
inside it - the dependency only runs the other way, from here out to the
rest of the repo.

## Entry point

- **[`../reaper.sh`](../reaper.sh) `[--play|--render] [--piece NAME]`** -
  regenerates a piece's project and hands it to REAPER. `--play` opens
  REAPER and leaves it playing through the speakers. `--render` bounces
  headlessly, checks every engine and macro envelope, and compares the
  bounce against the offline preview.

## Scripts

- **`generate_project.py [--piece NAME] [out.RPP]`** - writes a complete
  REAPER project with every track's instrument script embedded directly
  in synthesized VST3 state, so it opens with no build pass.
- **`verify_song.py --piece NAME <bounce.wav> <preview.wav>`** - compares
  a REAPER bounce against the offline preview section by section. A
  plain wav-diff utility with no REAPER awareness of its own; it lives
  here because `reaper.sh` is its only caller today.
- **`render-all.sh [--piece NAME]`** - the whole pipeline for every piece
  with no interaction: offline preview, REAPER bounce through the real
  plug-in, section-by-section comparison. Needs the plug-in installed
  first (`../scripts/install-plugin-windows.sh`).
- **`install-reaper-portable.sh [--platform linux|windows]`** - downloads
  and portable-installs the pinned REAPER build everything here expects.
  Idempotent. The Windows install needs one UAC prompt approved by a
  human - it isn't fully unattended.
- **`scripts/autoplay.lua`, `scripts/verify.lua`** - the self-deleting
  startup scripts `reaper.sh` installs as REAPER's `Scripts/__startup.lua`
  for play mode and render mode respectively.
- **`matrix/`** - drives the instrument+effect chain through a real copy
  of REAPER with no GUI interaction (`matrix/run-reaper-matrix.sh`), for
  the things only a real DAW host can exercise: FX chain add/remove,
  parameter automation, project save/reload, macro resync. See that
  script's header for platform-specific setup.
