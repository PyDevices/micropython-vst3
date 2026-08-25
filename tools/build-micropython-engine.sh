#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
workspace_dir=$(cd "$repo_dir/.." && pwd)
cmods_dir=${CMODS_DIR:-"$workspace_dir/cmods"}
mp_dir=${MICROPYTHON_DIR:-"$cmods_dir/micropython"}
output_dir="$repo_dir/.deps/engine"

test -f "$mp_dir/ports/windows/Makefile"
test -f "$workspace_dir/audioif/micropython.mk"

mkdir -p "$output_dir"

# cmods applies its Windows networking/SSL/FFI overlays transactionally and
# reverses them on exit. Add only this repository's module to its ignored
# discovery root for the duration of the build.
vstaudio_link="$cmods_dir/vstaudio"
if [[ -e "$vstaudio_link" && ! -L "$vstaudio_link" ]]; then
    echo "error: $vstaudio_link already exists and is not a symlink" >&2
    exit 1
fi
ln -sfn "$repo_dir/usermods/vstaudio" "$vstaudio_link"
cleanup() {
    if [[ -L "$vstaudio_link" && "$(readlink "$vstaudio_link")" == "$repo_dir/usermods/vstaudio" ]]; then
        unlink "$vstaudio_link"
    fi
}
trap cleanup EXIT

BUILD=build-vst-engine \
PROG=micropython-vst-engine \
    "$cmods_dir/build_mp.sh" --port windows --variant dev

install -m 755 \
    "$mp_dir/ports/windows/build-vst-engine/micropython-vst-engine.exe" \
    "$output_dir/micropython-vst-engine.exe"

echo "Built $output_dir/micropython-vst-engine.exe"
