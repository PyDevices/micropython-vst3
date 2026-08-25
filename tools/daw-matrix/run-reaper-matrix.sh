#!/usr/bin/env bash
# Drive the Windows DAW matrix in REAPER from WSL without GUI interaction.
#
# REAPER runs tools/daw-matrix/matrix.lua as its startup script, exercises the
# Phase 6 exit criteria against the installed VST3 bundle, renders WAV files,
# and quits. verify_renders.py then checks the rendered PCM.
set -euo pipefail

repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
matrix_dir="$repo_dir/tools/daw-matrix"

reaper_exe=${REAPER_EXE:-/mnt/c/Users/bradb/REAPER/reaper.exe}
reaper_resource=${REAPER_RESOURCE:-/mnt/c/Users/bradb/AppData/Roaming/REAPER}
win_temp=${WIN_TEMP:-/mnt/c/Users/bradb/AppData/Local/Temp}
work_unix="$win_temp/mpvst-matrix"
work_win='C:\Users\bradb\AppData\Local\Temp\mpvst-matrix'
report_unix="$work_unix/report.txt"
report_win="$work_win\\report.txt"
timeout_seconds=${MATRIX_TIMEOUT:-660}

test -x "$reaper_exe" || chmod +x "$reaper_exe"

rm -rf "$work_unix"
mkdir -p "$work_unix"

# The instance loads script.py; the malformed-script step overwrites it and the
# recovery step restores it from good_backup.py.
cp "$matrix_dir/matrix_instrument.py" "$work_unix/script.py"
cp "$matrix_dir/matrix_instrument.py" "$work_unix/good_backup.py"
cp "$matrix_dir/matrix_instrument_edited.py" "$work_unix/edited_script.py"
cat > "$work_unix/bad_script.py" <<'PY'
import vstaudio

this is not valid python
PY

# REAPER reopens whatever project it had last, which fails once this working
# directory is recreated. Always hand it an explicit empty project instead.
cat > "$work_unix/empty.RPP" <<'RPP'
<REAPER_PROJECT 0.1 "7.79/x64" 0
  RIPPLE 0
  TEMPO 120 4 4
>
RPP

mkdir -p "$reaper_resource/Scripts"
cp "$matrix_dir/matrix.lua" "$reaper_resource/Scripts/__startup.lua"

# A stale instance would swallow the launch and keep the old startup script.
powershell.exe -NoProfile -Command \
    "Get-Process reaper -EA SilentlyContinue | Stop-Process -Force -EA SilentlyContinue" \
    >/dev/null 2>&1 || true
sleep 2

launcher="$win_temp/mpvst_run_matrix.ps1"
cat > "$launcher" <<PS1
\$env:MPVST_SCRIPT_PATH = "$work_win\\script.py"
\$env:MPVST_BAD_SCRIPT_PATH = "$work_win\\bad_script.py"
\$env:MPVST_EDITED_SCRIPT_PATH = "$work_win\\edited_script.py"
\$env:MPVST_MATRIX_REPORT = "$report_win"
\$env:MPVST_MATRIX_WORKDIR = "$work_win"
\$env:MPVST_TEST_LOG = "$work_win\\script_log.txt"
\$p = Start-Process -FilePath "$(wslpath -w "$reaper_exe")" -ArgumentList "-ignoreerrors","$work_win\\empty.RPP" -PassThru
Write-Output ("pid=" + \$p.Id)
PS1

echo "Launching REAPER matrix (timeout ${timeout_seconds}s)..."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(wslpath -w "$launcher")" >/dev/null 2>&1 || true

deadline=$(( $(date +%s) + timeout_seconds ))
while [ "$(date +%s)" -lt "$deadline" ]; do
    if [ -f "$report_unix" ] && grep -q '^DONE' "$report_unix" 2>/dev/null; then
        break
    fi
    sleep 5
done

# REAPER quits itself; make sure nothing is left running before verification.
powershell.exe -NoProfile -Command \
    "Get-Process reaper -EA SilentlyContinue | ForEach-Object { \$_.CloseMainWindow() } | Out-Null; Start-Sleep -Seconds 5; Get-Process reaper -EA SilentlyContinue | Stop-Process -Force -EA SilentlyContinue" \
    >/dev/null 2>&1 || true

echo
echo "=== matrix report ==="
if [ -f "$report_unix" ]; then
    cat "$report_unix"
else
    echo "no report produced; REAPER may be holding a modal dialog:"
    powershell.exe -NoProfile -Command \
        "Get-Process reaper -EA SilentlyContinue | ForEach-Object { \$_.MainWindowTitle }" \
        2>/dev/null || true
fi

echo
echo "=== rendered files ==="
ls -la "$work_unix"/*.wav 2>/dev/null || echo "no renders produced"

echo
python3 "$matrix_dir/verify_renders.py" "$work_unix"
