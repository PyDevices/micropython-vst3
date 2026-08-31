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

# The engine is a deliberately narrow scripting core: compositions and racks
# are code, and scan_plugins.py runs at DAW scan time, so the shipped
# interpreter must not reach the network (sockets/SSL) or arbitrary native
# code (FFI). On windows those arrive as cmods overlay patches 0001/0003 —
# skipped here; on unix they are port defaults — forced off on the make
# command line. Overlay source of truth: micropython-pydevices
# profiles/vst3-engine.series. Rebuilding with them enabled is possible but
# is then the builder's own informed choice, not the shipped default.
engine_overlay_skip=""
engine_make_extra=""
case "$port" in
    # mkrules.mk appends .exe itself for mingw targets, so PROG must be the
    # bare name; the installed artifact still carries the extension.
    windows) prog_name=micropython-vst-engine; engine_name=micropython-vst-engine.exe; variant=dev
             engine_overlay_skip="0001 0003" ;;
    unix)    prog_name=micropython-vst-engine; engine_name=micropython-vst-engine; variant=standard
             engine_make_extra="MICROPY_PY_SOCKET=0 MICROPY_PY_SSL=0 MICROPY_PY_FFI=0" ;;
    *) echo "error: unsupported port '$port'" >&2; exit 2 ;;
esac

repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
workspace_dir=$(cd "$repo_dir/.." && pwd)
cmods_dir=${CMODS_DIR:-"$workspace_dir/cmods"}
mp_dir=${MICROPYTHON_DIR:-"$cmods_dir/micropython"}
output_dir="$repo_dir/.deps/engine"

if [[ ! -f "$mp_dir/ports/$port/Makefile" ]]; then
    echo "error: no Makefile at $mp_dir/ports/$port - the sibling cmods/micropython" \
        "checkout is missing or incomplete. Run scripts/fetch-sibling-repos.sh," \
        "or point CMODS_DIR/MICROPYTHON_DIR at an existing checkout." >&2
    exit 1
fi
if [[ ! -f "$workspace_dir/audioif/micropython.mk" ]]; then
    echo "error: no micropython.mk at $workspace_dir/audioif - the sibling audioif" \
        "checkout is missing or incomplete. Run scripts/fetch-sibling-repos.sh." >&2
    exit 1
fi

mkdir -p "$output_dir"

# cmods applies its mailbox overlays transactionally and reverses them on
# exit; the engine build skips the networking/FFI ones (see above). Add only
# this repository's modules to its ignored discovery root for the duration
# of the build.
links=()
for module in vstaudio vstui; do
    link="$cmods_dir/$module"
    if [[ -e "$link" && ! -L "$link" ]]; then
        echo "error: $link already exists and is not a symlink" >&2
        exit 1
    fi
    ln -sfn "$repo_dir/usermods/$module" "$link"
    links+=("$link")
done
cleanup() {
    local link
    for link in "${links[@]}"; do
        if [[ -L "$link" && "$(readlink "$link")" == "$repo_dir/usermods/$(basename "$link")" ]]; then
            unlink "$link"
        fi
    done
}
trap cleanup EXIT

BUILD=build-vst-engine \
PROG="$prog_name" \
MP_OVERLAY_SKIP="$engine_overlay_skip" \
MP_MAKE_EXTRA="$engine_make_extra" \
    "$cmods_dir/build_mp.sh" --port "$port" --variant "$variant"

install -m 755 \
    "$mp_dir/ports/$port/build-vst-engine/$engine_name" \
    "$output_dir/$engine_name"

echo "Built $output_dir/$engine_name"
