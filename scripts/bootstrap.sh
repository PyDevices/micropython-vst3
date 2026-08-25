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

log "fetching sibling repos (cmods, audioif)"
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
if ! "$repo_dir/scripts/install-reaper-portable.sh"; then
    log "REAPER install did not complete - see the message above for a manual fallback." \
        "The rest of bootstrap continues without it; tools/daw-matrix/ and" \
        "tools/piece/launch.sh need it, the core build/test does not."
fi

log "configuring and building"
cmake -S "$repo_dir" -B "$repo_dir/build-linux" -G Ninja || die "cmake configure failed"
cmake --build "$repo_dir/build-linux" || die "cmake build failed"

log "running the test suite"
ctest --test-dir "$repo_dir/build-linux" --output-on-failure || die "ctest failed"

log "done - workspace ready at $repo_dir"
