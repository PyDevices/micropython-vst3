#!/usr/bin/env bash
# Phase 8 exit criterion: the same script, state, and events must produce the
# same PCM on Windows and on Linux.
#
# Both smoke hosts render a fixed score through the real MicroPython sidecar and
# write raw float32 PCM. This compares the two files byte for byte and, when
# they differ, reports the largest sample difference so a genuine tolerance
# question can be told apart from a structural one.
set -euo pipefail

repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
linux_build=${LINUX_BUILD:-"$repo_dir/.build-linux"}
source "$repo_dir/scripts/lib/windows-paths.sh"
mpvst_load_windows_paths || exit 1
windows_build_unix=${WINDOWS_BUILD_UNIX:-$WIN_TEMP/micropython-vst3-build}
windows_build_win=${WINDOWS_BUILD_WIN:-$(wslpath -w "$windows_build_unix")}
work=${WORK_DIR:-$(mktemp -d)}

linux_pcm="$work/reference-linux.pcm"
windows_pcm_unix="$windows_build_unix/reference-windows.pcm"
windows_pcm_win="$windows_build_win\\reference-windows.pcm"

echo "Rendering the Linux reference..."
"$linux_build/tests/smoke_host/mpvst_smoke_host" \
    "$linux_build/VST3/Release/MicroPythonVST3.vst3" \
    --render-reference "$linux_pcm" >/dev/null

echo "Rendering the Windows reference..."
smoke_exe="$windows_build_unix/tests/smoke_host/Release/mpvst_smoke_host.exe"
test -x "$smoke_exe" || chmod +x "$smoke_exe"
"$smoke_exe" "$windows_build_win\\VST3\\Release\\MicroPythonVST3.vst3" \
    --render-reference "$windows_pcm_win" >/dev/null

linux_hash=$(sha256sum "$linux_pcm" | cut -d' ' -f1)
windows_hash=$(sha256sum "$windows_pcm_unix" | cut -d' ' -f1)

echo
echo "linux   $linux_hash  $(stat -c%s "$linux_pcm") bytes"
echo "windows $windows_hash  $(stat -c%s "$windows_pcm_unix") bytes"
echo

if [ "$linux_hash" = "$windows_hash" ]; then
    echo "PARITY PASS: the two platforms produced identical PCM"
    exit 0
fi

python3 - "$linux_pcm" "$windows_pcm_unix" <<'PY'
import struct
import sys

with open(sys.argv[1], "rb") as handle:
    left = handle.read()
with open(sys.argv[2], "rb") as handle:
    right = handle.read()

if len(left) != len(right):
    print("PARITY FAIL: different lengths (%d vs %d)" % (len(left), len(right)))
    raise SystemExit(1)

count = len(left) // 4
a = struct.unpack("<%df" % count, left)
b = struct.unpack("<%df" % count, right)
worst = 0.0
index = -1
for position, (x, y) in enumerate(zip(a, b)):
    difference = abs(x - y)
    if difference > worst:
        worst, index = difference, position
print("PARITY FAIL: largest difference %.9g at sample %d" % (worst, index))
raise SystemExit(1)
PY
