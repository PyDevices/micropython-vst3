#!/usr/bin/env bash
# Build and install the Windows VST3 bundle into the per-user VST3
# directory a DAW scans (%LOCALAPPDATA%\Programs\Common\VST3), which is
# where tools/piece/launch.sh and tools/daw-matrix/ expect to find it.
#
#   ./scripts/install-plugin-windows.sh [--no-build]
#
# Run from WSL. Needs the Windows engine built first
# (scripts/build-micropython-engine.sh --port windows) and a configured
# Windows CMake build directory; MPVST_WIN_BUILD overrides where that is.
set -euo pipefail

repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

build=1
[[ "${1:-}" == "--no-build" ]] && build=0

source "$repo_dir/scripts/lib/windows-paths.sh"
mpvst_load_windows_paths || exit 1

win_build=${MPVST_WIN_BUILD:-$WIN_TEMP/micropython-vst3-build}
vst3_dir=${MPVST_VST3_DIR:-$WIN_LOCALAPPDATA/Programs/Common/VST3}
bundle_src="$win_build/VST3/Release/MicroPythonVST3.vst3"
cmake_exe="$repo_dir/.deps/cmake-4.4.2-windows-x86_64/bin/cmake.exe"

[[ -f "$win_build/CMakeCache.txt" ]] || {
    echo "error: no configured Windows build at $win_build" >&2
    echo "  configure it first with the vendored cmake, e.g.:" >&2
    echo "  '$cmake_exe' -S <repo, as a Windows path> -B <build> -G 'Visual Studio 18 2026'" >&2
    exit 1
}

if [[ "$build" == 1 ]]; then
    [[ -x "$cmake_exe" ]] || { echo "error: vendored Windows cmake missing at $cmake_exe" >&2; exit 1; }
    echo "building the Windows bundle"
    # Warnings about missing lowercase \\wsl.localhost\ubuntu\... module
    # paths are a case-sensitivity artifact of building a WSL-hosted tree
    # over the \\wsl.localhost share; the build itself succeeds.
    "$cmake_exe" --build "$(wslpath -w "$win_build")" --config Release >/dev/null \
        || { echo "error: Windows build failed" >&2; exit 1; }
fi

[[ -d "$bundle_src" ]] || { echo "error: no bundle at $bundle_src" >&2; exit 1; }

# A DAW holds the .vst3 DLL open, so a running REAPER blocks the copy -
# and each sidecar holds micropython-vst-engine.exe open, so orphaned
# engines (left behind when a host is force-killed) block it too.
powershell.exe -NoProfile -Command \
    "Get-Process reaper,micropython-vst-engine,micropython-vst-native-engine -EA SilentlyContinue | Stop-Process -Force -EA SilentlyContinue" \
    >/dev/null 2>&1 || true
sleep 1

mkdir -p "$vst3_dir"
rm -rf "$vst3_dir/MicroPythonVST3.vst3"
cp -r "$bundle_src" "$vst3_dir/MicroPythonVST3.vst3"

echo "installed: $vst3_dir/MicroPythonVST3.vst3"
