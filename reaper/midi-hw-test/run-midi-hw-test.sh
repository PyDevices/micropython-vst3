#!/usr/bin/env bash
# Drive a real REAPER instance so it plays a deterministic MIDI note
# sequence out a hardware MIDI output device, for a board-side listener to
# verify reception. This is realtime playback, not a render: hardware MIDI
# out only moves during Play, and REAPER's offline-render path (everything
# else in reaper/) never touches it.
#
#   ./run-midi-hw-test.sh --list-devices [--platform windows|linux]
#       Enumerate the MIDI input/output devices this REAPER install sees,
#       and confirm the transport advances in real wall-clock time under
#       Play. Prints device indices; run this first to find the number
#       --device wants. Never configures hardware MIDI output on a track,
#       never presses a note - completely silent.
#
#   ./run-midi-hw-test.sh --device N [--channel C] [--platform windows|linux]
#       Build the test project routed to output device N channel C
#       (default 1), launch REAPER, and hold - the launch itself starts
#       playback about MPVST_MIDIHW_DELAY seconds later (default 3) and
#       runs for the project's length (40s for the default C4 E4 G4 C5
#       sequence) plus a one-second tail, then stops the transport and
#       leaves REAPER open. THIS SENDS REAL MIDI - only run it once the
#       board-side listener is ready.
#
# Only this script and scripts/windows-paths.sh differ by platform; the
# project generator (build_project.py) and both startup hooks
# (probe_devices.lua, play.lua) are plain Python/Lua with no OS-specific
# calls, so the device index from --list-devices is the only thing that
# usually changes machine to machine.
#
# Known trap, found standing this up (2026-08-31): REAPER scans every MIDI
# device it knows about before it creates its window or runs
# Scripts/__startup.lua, on *any* launch that touches the MIDI subsystem at
# all - including plain --list-devices enumeration, with no track ever
# configured for hardware output. Normally near-instant. It hung for many
# minutes at a time while a MIDI device on the bus was live and running a
# firmware program that echoes/harmonizes whatever it receives on both
# directions; a plain enumeration pass earlier the same session, before
# that firmware was running, returned instantly. Ruled out first, in this
# order, before landing on the device: the project file's MIDIOUT chunk
# encoding (packed I_MIDIHWOUT value vs. plain device/channel fields - both
# hung identically), which device a track referenced (the real USB target
# and an unrelated always-present virtual synth both hung identically),
# and the audio-driver mode (reaper.ini [audioconfig] mode=0 through 8 all
# hung identically). If a device on the bus is behaving like this, that is
# a finding about the device, not this script - stop and report it rather
# than sweeping REAPER settings looking for a fix.
#
# `stop_reaper` below verifies the kill with `tasklist.exe`, not
# `Get-Process` (the latter kept reporting a process gone while
# `tasklist`/`Get-CimInstance` still saw it alive for several more
# minutes - see workspace-craft.md), and escalates to
# `Process.Kill()+WaitForExit` if a plain `Stop-Process -Force` doesn't
# clear it within the loop below.
set -euo pipefail

platform=windows
device=
channel=1
mode=play
while [[ $# -gt 0 ]]; do
    case "$1" in
        --platform) platform="$2"; shift 2 ;;
        --device) device="$2"; shift 2 ;;
        --channel) channel="$2"; shift 2 ;;
        --list-devices) mode=list; shift ;;
        *) echo "usage: $0 [--list-devices | --device N [--channel C]] [--platform windows|linux]" >&2
           exit 2 ;;
    esac
done

repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
test_dir="$repo_dir/reaper/midi-hw-test"
timeout_seconds=${MPVST_MIDIHW_TIMEOUT:-90}

# --- platform-specific launch/config layer ---------------------------------
# Everything above this block, and everything in build_project.py /
# probe_devices.lua / play.lua, is the same on any OS REAPER runs on. Only
# path resolution and process invocation differ.
declare -a ENV_VARS=()

if [[ "$platform" == windows ]]; then
    # Queried, never assembled from a username: see ../../scripts/windows-paths.sh.
    source "$repo_dir/scripts/windows-paths.sh"
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
    work_unix=${WORK_DIR:-$WIN_TEMP/mpvst-midihw-test}
    to_native() { wslpath -w "$1"; }

    launch() {
        local launcher="$WIN_TEMP/mpvst_midihw_launch.ps1"
        {
            for kv in "${ENV_VARS[@]+"${ENV_VARS[@]}"}"; do
                printf '$env:%s = "%s"\n' "${kv%%=*}" "${kv#*=}"
            done
            printf 'Start-Process -FilePath "%s" -ArgumentList "-ignoreerrors","%s"\n' \
                "$(to_native "$reaper_exe")" "$1"
        } > "$launcher"
        powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(to_native "$launcher")" \
            >/dev/null 2>&1 || true
    }

    reaper_running() {
        tasklist.exe /FI "IMAGENAME eq reaper.exe" 2>/dev/null | grep -qi reaper.exe
    }

    stop_reaper() {
        powershell.exe -NoProfile -Command \
            "Get-Process reaper,micropython-vst-engine -EA SilentlyContinue | Stop-Process -Force -EA SilentlyContinue" \
            >/dev/null 2>&1 || true
        for _ in $(seq 1 10); do
            reaper_running || return 0
            sleep 2
        done
        # A plain Stop-Process can report success while tasklist still
        # sees the process (observed 2026-08-31); escalate per-PID.
        for pid in $(tasklist.exe /FI "IMAGENAME eq reaper.exe" /FO CSV /NH 2>/dev/null \
                     | tr -d '\r' | awk -F'","' '{gsub(/"/,"",$2); print $2}'); do
            powershell.exe -NoProfile -Command \
                "try { \$p=[System.Diagnostics.Process]::GetProcessById($pid); \$p.Kill(); \$p.WaitForExit(15000) | Out-Null } catch {}" \
                >/dev/null 2>&1 || true
        done
    }
else
    reaper_exe=${REAPER_EXE:-$HOME/opt/REAPER/reaper}
    reaper_resource=${REAPER_RESOURCE:-$HOME/.config/REAPER}
    work_unix=${WORK_DIR:-/tmp/mpvst-midihw-test}
    to_native() { printf '%s' "$1"; }

    launch() {
        env "${ENV_VARS[@]+"${ENV_VARS[@]}"}" \
            nohup "$reaper_exe" -ignoreerrors "$1" >/dev/null 2>&1 &
    }
    reaper_running() { pgrep -x reaper >/dev/null 2>&1; }
    stop_reaper() { pkill -x reaper >/dev/null 2>&1 || true; sleep 2; }
fi
# --- end platform-specific layer --------------------------------------------

test -e "$reaper_exe" || { echo "error: REAPER not found at $reaper_exe" >&2; exit 1; }
test -x "$reaper_exe" || chmod +x "$reaper_exe"

# Never rm -rf this directory: REAPER records whatever project it opens as
# "last project" (reaper.ini lastproject=/projecttab*=/[Recent]) more or
# less immediately, independent of a clean exit, and reopens it on the
# next launch that doesn't name a project of its own (a human double-
# clicking the REAPER icon, say). Deleting the file out from under that
# reference - which an earlier rm -rf here did - throws a stacked
# "There was an error opening the project" modal on every subsequent bare
# launch: a self-inflicted cousin of the modal-last-project trap this
# whole repo works around with -ignoreerrors. Only ever create or
# overwrite files in this directory; never remove the directory itself or
# the specific files REAPER might have opened last.
mkdir -p "$work_unix"
work_native=$(to_native "$work_unix")

cat > "$work_unix/empty.RPP" <<'RPP'
<REAPER_PROJECT 0.1 "7.79" 0
  RIPPLE 0
  TEMPO 120 4 4
>
RPP

echo "Stopping any running REAPER instance..."
stop_reaper
mkdir -p "$reaper_resource/Scripts"

if [[ "$mode" == list ]]; then
    report_unix="$work_unix/probe_report.txt"
    cp "$test_dir/probe_devices.lua" "$reaper_resource/Scripts/__startup.lua"
    ENV_VARS+=("MPVST_PROBE_REPORT=$(to_native "$report_unix")")
    launch "$(to_native "$work_unix/empty.RPP")"

    deadline=$(( $(date +%s) + timeout_seconds ))
    while [ "$(date +%s)" -lt "$deadline" ]; do
        [ -f "$report_unix" ] && grep -q '^DONE' "$report_unix" 2>/dev/null && break
        sleep 2
    done
    stop_reaper
    [[ -f "$reaper_resource/Scripts/__startup.lua" ]] && rm -f "$reaper_resource/Scripts/__startup.lua"

    echo
    echo "=== devices ==="
    cat "$report_unix" 2>/dev/null || echo "no report produced - see the hang note in this script's header"
    exit 0
fi

[[ -n "$device" ]] || {
    echo "error: --device N required (run --list-devices first to find it)" >&2
    exit 2
}

project_unix="$work_unix/MidiHwTest.RPP"
python3 "$test_dir/build_project.py" "$device" "$channel" "$project_unix"
project_native=$(to_native "$project_unix")

cp "$test_dir/play.lua" "$reaper_resource/Scripts/__startup.lua"
delay=${MPVST_MIDIHW_DELAY:-3}
ENV_VARS+=("MPVST_MIDIHW_DELAY=$delay")

echo "Launching REAPER with $project_native..."
launch "$project_native"

# play.lua deletes itself as its first act; make sure that happened so no
# startup hook is ever left behind, and so we know REAPER actually ran it
# (a hung device scan - see the header note - never gets this far).
for _ in $(seq 1 "$timeout_seconds"); do
    [[ -f "$reaper_resource/Scripts/__startup.lua" ]] || break
    sleep 1
done
if [[ -f "$reaper_resource/Scripts/__startup.lua" ]]; then
    rm -f "$reaper_resource/Scripts/__startup.lua"
    echo "error: REAPER did not run the startup script within ${timeout_seconds}s." >&2
    echo "       If REAPER's window is showing 'Scanning MIDI output devices'," >&2
    echo "       that is the known hang in this script's header note, not a" >&2
    echo "       launch failure - kill REAPER and see whether the target" >&2
    echo "       device answers the scan before retrying." >&2
    exit 1
fi

echo "REAPER is up; first note at approximately ${delay}s after this point," >&2
echo "the sequence runs for the project's own length (40s for the default" >&2
echo "note pattern), then the transport stops on its own. Project:" >&2
echo "  $project_native"
