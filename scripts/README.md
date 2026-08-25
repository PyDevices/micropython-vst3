# Scripts

Maintainer and bootstrap automation - things a fresh clone or a release
needs, not day-to-day dev workflow (see [`../tools/`](../tools/README.md)
for that). Every script here is idempotent: safe to rerun.

- **`bootstrap.sh`** - one-shot setup for a fresh clone: runs every
  script below in order, then configures, builds, and runs the test
  suite as a final verification. Start here.
- **`fetch-sibling-repos.sh`** - clones/updates the sibling `cmods` and
  `audioif` repos the engine build depends on.
- **`fetch-vst3-sdk.sh`** - downloads the pinned VST3 SDK into `.deps/vst3sdk`.
- **`build-micropython-engine.sh [--port windows|unix]`** - builds the
  MicroPython sidecar engine (defaults to the Windows engine, the
  shipping product; `--port unix` builds the same module set for Linux).
- **`install-reaper-portable.sh [--platform linux|windows]`** -
  downloads and portable-installs the pinned REAPER build
  `tools/daw-matrix/` and `tools/piece/launch.sh` expect. Not needed for
  the core build/test, only for that DAW-driven tooling. The Windows
  install needs one UAC prompt approved by a human - it isn't fully
  unattended.
- **`install-plugin-windows.sh [--no-build]`** - builds the Windows VST3
  bundle and installs it into the per-user VST3 directory a DAW scans,
  which is where `tools/piece/` and `tools/daw-matrix/` expect it.
- **`package-linux.sh`** / **`package-windows.sh`** - assemble the
  release archive for each platform's VST3 bundle.
- **`check-cross-platform-parity.sh`** - renders a fixed score through
  both platforms' real sidecars and compares the PCM byte for byte.
