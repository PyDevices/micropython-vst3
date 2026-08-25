#!/usr/bin/env bash
# Build a soundtrack piece's project and hand it to REAPER on Windows.
#
#   ./launch.sh            regenerate the project, open REAPER, and play it
#                          through the speakers (REAPER stays open)
#   ./launch.sh --render   headless verification render instead: bounce the
#                          whole piece offline, check every engine and the
#                          automation, and compare against the preview
#
# The project embeds every instrument script in plug-in state, so REAPER
# needs no environment beyond MPVST_HEAP_BYTES for the sidecars.
set -euo pipefail

mode=play
piece=perihelion
while [[ $# -gt 0 ]]; do
    case "$1" in
        --render) mode=render; shift ;;
        --play) mode=play; shift ;;
        --piece) piece="$2"; shift 2 ;;
        *) echo "usage: $0 [--play|--render] [--piece NAME]" >&2; exit 2 ;;
    esac
done

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
soundtrack_dir=$(cd "$script_dir/../../soundtrack" && pwd)
# Windows folder locations are queried, never assembled from a username:
# a profile need not live under C:\Users, and Roaming AppData is often
# redirected. REAPER_EXE / REAPER_RESOURCE / MPVST_VST3_DIR override.
source "$script_dir/../../scripts/lib/windows-paths.sh"
mpvst_load_windows_paths || exit 1
reaper_exe=${REAPER_EXE:-$WIN_USERPROFILE/REAPER/reaper.exe}
reaper_resource=${REAPER_RESOURCE:-$WIN_APPDATA/REAPER}
bundle=${MPVST_VST3_DIR:-$WIN_LOCALAPPDATA/Programs/Common/VST3}/MicroPythonVST3.vst3
heap_bytes=${MPVST_HEAP_BYTES:-33554432}

test -e "$reaper_exe" || { echo "error: REAPER not found at $reaper_exe" >&2; exit 1; }
test -x "$reaper_exe" || chmod +x "$reaper_exe"
test -d "$bundle" || { echo "error: MicroPythonVST3.vst3 not installed at $bundle" >&2; exit 1; }

read -r title render_seconds n_tracks n_instances n_envs <<< "$(python3 - <<PYEOF
import sys
sys.path.insert(0, "$script_dir")
from piece import load_piece
C, _ = load_piece("$piece")
units = [unit for track in C.TRACKS
         for unit in (track,) + tuple(track.get("effects", ())) ]
envs = sum(1 for unit in units
           for env in unit.get("macro_env", {}).values() if env)
print(C.TITLE, "%.1f" % C.RENDER_SECONDS, len(C.TRACKS), len(units), envs)
PYEOF
)"

stop_reaper() {
    # Force-killing REAPER orphans its sidecar engine processes, so stop
    # those explicitly as well.
    powershell.exe -NoProfile -Command \
        "Get-Process reaper,micropython-vst-engine,micropython-vst-native-engine -EA SilentlyContinue | Stop-Process -Force -EA SilentlyContinue" \
        >/dev/null 2>&1 || true
}

if [[ "$mode" == play ]]; then
    project_dir="$WIN_MUSIC/$title"
    mkdir -p "$project_dir"
    python3 "$script_dir/generate_project.py" --piece "$piece" "$project_dir/$title.RPP"
    project_native=$(wslpath -w "$project_dir/$title.RPP")

    echo "Stopping any running REAPER instance..."
    stop_reaper
    sleep 2

    mkdir -p "$reaper_resource/Scripts"
    cp "$script_dir/reaper/autoplay.lua" "$reaper_resource/Scripts/__startup.lua"

    launcher="$WIN_TEMP/mpvst_play_$piece.ps1"
    cat > "$launcher" <<PS1
\$env:MPVST_HEAP_BYTES = "$heap_bytes"
Start-Process -FilePath "$(wslpath -w "$reaper_exe")" -ArgumentList "-ignoreerrors","$project_native"
PS1
    echo "Launching REAPER with $title..."
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(wslpath -w "$launcher")" \
        >/dev/null 2>&1 || true

    # autoplay.lua deletes itself as its first act; make sure that happened
    # so no startup hook is ever left behind.
    for _ in $(seq 1 30); do
        [[ -f "$reaper_resource/Scripts/__startup.lua" ]] || break
        sleep 1
    done
    if [[ -f "$reaper_resource/Scripts/__startup.lua" ]]; then
        rm -f "$reaper_resource/Scripts/__startup.lua"
        echo "warning: REAPER did not run the startup script; removed it." >&2
        echo "Open $project_native in REAPER and press play." >&2
        exit 1
    fi
    echo "REAPER is up; playback starts about six seconds in (the sidecars"
    echo "get a moment to boot). The project stays open at:"
    echo "  $project_native"
    exit 0
fi

# --- headless verification render -------------------------------------------

work_unix="$WIN_TEMP/mpvst-$piece"
timeout_seconds=${SCORE_TIMEOUT:-2400}

rm -rf "$work_unix"
mkdir -p "$work_unix"
work_native=$(wslpath -w "$work_unix")

python3 "$script_dir/generate_project.py" --piece "$piece" "$work_unix/$title.RPP"

mkdir -p "$reaper_resource/Scripts"
cp "$script_dir/reaper/verify.lua" "$reaper_resource/Scripts/__startup.lua"

echo "Stopping any running REAPER instance..."
stop_reaper
sleep 2

launcher="$WIN_TEMP/mpvst_verify_$piece.ps1"
cat > "$launcher" <<PS1
\$env:MPVST_HEAP_BYTES = "$heap_bytes"
\$env:MPVST_SCORE_REPORT = "$work_native\\report.txt"
\$env:MPVST_SCORE_WORKDIR = "$work_native"
\$env:MPVST_SCORE_SECONDS = "$render_seconds"
\$env:MPVST_SCORE_BOUNCE = "${piece}_bounce"
\$env:MPVST_SCORE_TRACKS = "$n_tracks"
\$env:MPVST_SCORE_INSTANCES = "$n_instances"
\$env:MPVST_SCORE_MIN_ENVS = "$n_envs"
\$env:MPVST_SCORE_DEADLINE = "$timeout_seconds"
Start-Process -FilePath "$(wslpath -w "$reaper_exe")" -ArgumentList "-ignoreerrors","$work_native\\$title.RPP"
PS1
echo "Launching headless verification render (timeout ${timeout_seconds}s)..."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(wslpath -w "$launcher")" \
    >/dev/null 2>&1 || true

deadline=$(( $(date +%s) + timeout_seconds ))
while [ "$(date +%s)" -lt "$deadline" ]; do
    if [ -f "$work_unix/report.txt" ] && grep -q '^DONE' "$work_unix/report.txt" 2>/dev/null; then
        break
    fi
    sleep 10
done

stop_reaper
rm -f "$reaper_resource/Scripts/__startup.lua"

echo
echo "=== verification report ==="
cat "$work_unix/report.txt" 2>/dev/null || echo "no report produced"

bounce="$work_unix/${piece}_bounce.wav"
if [ -f "$bounce" ]; then
    mkdir -p "$soundtrack_dir/build"
    cp "$bounce" "$soundtrack_dir/build/$title.wav"
    echo
    echo "=== bounce vs preview ==="
    "$script_dir/../../../audioif/.venv/bin/python" "$script_dir/verify_song.py" \
        --piece "$piece" \
        "$soundtrack_dir/build/$title.wav" \
        "$soundtrack_dir/build/${piece}_preview.wav"
else
    echo "error: no bounce produced" >&2
    exit 1
fi
