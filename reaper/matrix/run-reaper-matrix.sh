#!/usr/bin/env bash
# Drive the DAW matrix in REAPER without GUI interaction.
#
#   ./reaper/matrix/run-reaper-matrix.sh [--platform windows|linux]
#
# REAPER runs reaper/matrix/matrix.lua as its startup script, exercises the
# Phase 6 exit criteria against the installed VST3 bundle, renders WAV files,
# and quits. verify_renders.py then checks the rendered PCM.
set -euo pipefail

platform=windows
while [[ $# -gt 0 ]]; do
    case "$1" in
        --platform) platform="$2"; shift 2 ;;
        *) echo "usage: $0 [--platform windows|linux]" >&2; exit 2 ;;
    esac
done

repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
matrix_dir="$repo_dir/reaper/matrix"
timeout_seconds=${MATRIX_TIMEOUT:-660}

# to_native prints a path the way REAPER's own process will see it, which is
# only a translation on Windows.
if [[ "$platform" == windows ]]; then
    # Queried, never assembled from a username: see scripts/lib/windows-paths.sh.
    source "$repo_dir/scripts/lib/windows-paths.sh"
    mpvst_load_windows_paths || exit 1
    reaper_exe=${REAPER_EXE:-$WIN_USERPROFILE/REAPER/reaper.exe}
    # Portable REAPER (reaper.ini beside reaper.exe) keeps its resource
    # directory there, not in AppData. See ../../reaper.sh.
    if [[ -n "${REAPER_RESOURCE:-}" ]]; then
        reaper_resource=$REAPER_RESOURCE
    elif [[ -f "$(dirname "$reaper_exe")/reaper.ini" ]]; then
        reaper_resource=$(dirname "$reaper_exe")
    else
        reaper_resource=$WIN_APPDATA/REAPER
    fi
    work_unix=${WORK_DIR:-$WIN_TEMP/mpvst-matrix}
    to_native() { wslpath -w "$1"; }
    sep='\'
else
    reaper_exe=${REAPER_EXE:-$HOME/opt/REAPER/reaper}
    reaper_resource=${REAPER_RESOURCE:-$HOME/.config/REAPER}
    work_unix=${WORK_DIR:-/tmp/mpvst-matrix}
    to_native() { printf '%s' "$1"; }
    sep='/'
fi

report_unix="$work_unix/report.txt"
test -x "$reaper_exe" || chmod +x "$reaper_exe"

rm -rf "$work_unix"
mkdir -p "$work_unix"
work_native=$(to_native "$work_unix")

# The instance loads script.py; the malformed step overwrites it and the
# recovery step restores it from good_backup.py.
cp "$matrix_dir/matrix_instrument.py" "$work_unix/script.py"
cp "$matrix_dir/matrix_instrument.py" "$work_unix/good_backup.py"
cp "$matrix_dir/matrix_instrument_edited.py" "$work_unix/edited_script.py"
cp "$matrix_dir/matrix_effect.py" "$work_unix/effect_script.py"
python3 "$matrix_dir/build_effect_project.py" \
    "$work_unix/effect_project.RPP" \
    "$matrix_dir/matrix_instrument.py" "$matrix_dir/matrix_effect.py"
cat > "$work_unix/bad_script.py" <<'PY'
import vstaudio

this is not valid python
PY

# REAPER reopens whatever project it had last, which fails once this working
# directory is recreated. Always hand it an explicit empty project instead.
cat > "$work_unix/empty.RPP" <<'RPP'
<REAPER_PROJECT 0.1 "7.79" 0
  RIPPLE 0
  TEMPO 120 4 4
>
RPP

mkdir -p "$reaper_resource/Scripts"
cp "$matrix_dir/matrix.lua" "$reaper_resource/Scripts/__startup.lua"

stop_reaper() {
    if [[ "$platform" == windows ]]; then
        powershell.exe -NoProfile -Command \
            "Get-Process reaper,micropython-vst-engine,micropython-vst-native-engine -EA SilentlyContinue | Stop-Process -Force -EA SilentlyContinue" \
            >/dev/null 2>&1 || true
    else
        pkill -x reaper >/dev/null 2>&1 || true
    fi
}

# A stale instance would swallow the launch and keep the old startup script.
stop_reaper
sleep 2

echo "Launching REAPER matrix on $platform (timeout ${timeout_seconds}s)..."
if [[ "$platform" == windows ]]; then
    launcher="$WIN_TEMP/mpvst_run_matrix.ps1"
    cat > "$launcher" <<PS1
\$env:MPVST_SCRIPT_PATH = "$work_native${sep}script.py"
\$env:MPVST_BAD_SCRIPT_PATH = "$work_native${sep}bad_script.py"
\$env:MPVST_EDITED_SCRIPT_PATH = "$work_native${sep}edited_script.py"
\$env:MPVST_EFFECT_SCRIPT_PATH = "$work_native${sep}effect_script.py"
\$env:MPVST_MATRIX_REPORT = "$work_native${sep}report.txt"
\$env:MPVST_MATRIX_WORKDIR = "$work_native"
\$env:MPVST_TEST_LOG = "$work_native${sep}script_log.txt"
Start-Process -FilePath "$(to_native "$reaper_exe")" -ArgumentList "-ignoreerrors","$work_native${sep}empty.RPP"
PS1
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(to_native "$launcher")" \
        >/dev/null 2>&1 || true
else
    MPVST_SCRIPT_PATH="$work_unix/script.py" \
    MPVST_BAD_SCRIPT_PATH="$work_unix/bad_script.py" \
    MPVST_EDITED_SCRIPT_PATH="$work_unix/edited_script.py" \
    MPVST_EFFECT_SCRIPT_PATH="$work_unix/effect_script.py" \
    MPVST_MATRIX_REPORT="$report_unix" \
    MPVST_MATRIX_WORKDIR="$work_unix" \
    MPVST_TEST_LOG="$work_unix/script_log.txt" \
        nohup "$reaper_exe" -ignoreerrors "$work_unix/empty.RPP" \
        >/dev/null 2>&1 &
fi

deadline=$(( $(date +%s) + timeout_seconds ))
while [ "$(date +%s)" -lt "$deadline" ]; do
    if [ -f "$report_unix" ] && grep -q '^DONE' "$report_unix" 2>/dev/null; then
        break
    fi
    sleep 5
done

stop_reaper

echo
echo "=== matrix report ==="
if [ -f "$report_unix" ]; then
    cat "$report_unix"
else
    echo "no report produced; REAPER may be holding a modal dialog"
fi

echo
echo "=== rendered files ==="
ls -la "$work_unix"/*.wav 2>/dev/null || echo "no renders produced"

echo
python3 "$matrix_dir/verify_renders.py" "$work_unix"
