#!/usr/bin/env bash
# Build the MicroPython sidecar engine.
#
#   ./scripts/build-micropython-engine.sh [--port windows|unix]
#
# Defaults to the Windows engine, which is the shipping product. The unix port
# builds the same module set for the Linux bundle.
set -euo pipefail

port=windows
while [[ $# -gt 0 ]]; do
    case "$1" in
        --port) port="$2"; shift 2 ;;
        *) echo "usage: $0 [--port windows|unix]" >&2; exit 2 ;;
    esac
done

case "$port" in
    # mkrules.mk appends .exe itself for mingw targets, so PROG must be the
    # bare name; the installed artifact still carries the extension.
    windows) prog_name=micropython-vst-engine; engine_name=micropython-vst-engine.exe; variant=dev ;;
    unix)    prog_name=micropython-vst-engine; engine_name=micropython-vst-engine; variant=standard ;;
    *) echo "error: unsupported port '$port'" >&2; exit 2 ;;
esac

repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
workspace_dir=$(cd "$repo_dir/.." && pwd)
cmods_dir=${CMODS_DIR:-"$workspace_dir/cmods"}
mp_dir=${MICROPYTHON_DIR:-"$cmods_dir/micropython"}
output_dir="$repo_dir/.deps/engine"

test -f "$mp_dir/ports/$port/Makefile"
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
PROG="$prog_name" \
    "$cmods_dir/build_mp.sh" --port "$port" --variant "$variant"

install -m 755 \
    "$mp_dir/ports/$port/build-vst-engine/$engine_name" \
    "$output_dir/$engine_name"

echo "Built $output_dir/$engine_name"
