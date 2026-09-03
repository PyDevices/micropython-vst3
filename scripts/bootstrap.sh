#!/usr/bin/env bash
# One-shot setup for a fresh clone: sibling repos, VST3 SDK, the
# MicroPython engine, REAPER, then a CMake configure/build/ctest pass as
# the final verification. Idempotent - every step skips work it already
# did, so it's safe to rerun after a partial failure or just to check the
# workspace is still healthy.
#
#   ./scripts/bootstrap.sh
set -euo pipefail

repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

log() { printf 'bootstrap: %s\n' "$*"; }
die() { log "ERROR: $*"; exit 1; }

log "fetching sibling repos (cmods, audioif, audiocomponents)"
"$repo_dir/scripts/fetch-sibling-repos.sh" || die "fetch-sibling-repos.sh failed"

log "fetching VST3 SDK"
"$repo_dir/scripts/fetch-vst3-sdk.sh" || die "fetch-vst3-sdk.sh failed"

log "building the MicroPython engine (unix port, for Linux/WSL testing)"
"$repo_dir/scripts/build-micropython-engine.sh" --port unix \
    || die "build-micropython-engine.sh --port unix failed"

if [[ -d /mnt/c/Users ]] && command -v powershell.exe >/dev/null 2>&1; then
    log "building the MicroPython engine (windows port, the shipping product)"
    "$repo_dir/scripts/build-micropython-engine.sh" --port windows \
        || die "build-micropython-engine.sh --port windows failed"
else
    log "not running under WSL with a reachable Windows host; skipping the windows engine port"
fi

log "installing REAPER (best-effort; not required for the build/test below)"
if ! "$repo_dir/reaper/install-reaper-portable.sh"; then
    log "REAPER install did not complete - see the message above for a manual fallback." \
        "The rest of bootstrap continues without it; reaper/ and" \
        "reaper.sh need it, the core build/test does not."
fi

log "creating .venv (pydevices-audioif, pydevices-audioinstruments," \
    "pydevices-audioeffects from TestPyPI; numpy, flake8)"
if [[ ! -d "$repo_dir/.venv" ]]; then
    python3 -m venv "$repo_dir/.venv" || die "python3 -m venv failed"
fi
# The three PyDevices distributions live on TestPyPI; the extra index
# resolves their ordinary dependencies. The two component distributions
# keep their names across the audioif -> audiocomponents split
# (audiocomponents#2): after it they are published from audiocomponents,
# still as pydevices-audioinstruments and pydevices-audioeffects, so this
# line does not change with the flip.
"$repo_dir/.venv/bin/pip" install -q \
    -i https://test.pypi.org/simple/ \
    --extra-index-url https://pypi.org/simple/ \
    pydevices-audioif pydevices-audioinstruments pydevices-audioeffects \
    numpy flake8 \
    || die "installing the PyDevices audio packages/numpy/flake8 into .venv failed"
log ".venv ready - this is what gates the mpvst_lint, mpvst_instruments_library" \
    "and mpvst_effects_library ctests, and where tools/render_preview.py and" \
    "tools/test-*.py import audioinstruments and audioeffects from."

log "configuring and building"
cmake -S "$repo_dir" -B "$repo_dir/.build-linux" -G Ninja || die "cmake configure failed"
cmake --build "$repo_dir/.build-linux" || die "cmake build failed"

log "running the test suite"
ctest --test-dir "$repo_dir/.build-linux" --output-on-failure || die "ctest failed"

log "done - workspace ready at $repo_dir"
