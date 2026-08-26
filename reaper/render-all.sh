#!/usr/bin/env bash
# Produce every soundtrack deliverable end to end, with no interaction:
# the offline CPython preview, the REAPER bounce through the real
# plug-in, and the section-by-section comparison of the two.
#
#   ./reaper/render-all.sh                   every piece
#   ./reaper/render-all.sh --piece automata  just one
#
# Needs the plug-in installed for the current platform first:
#   ./scripts/install-plugin-windows.sh
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_dir=$(cd "$script_dir/.." && pwd)
composition_dir="$repo_dir/tools"
soundtrack_dir="$repo_dir/soundtrack"
# render_preview.py and verify_song.py need numpy plus the audioif
# wheel - this repo's own .venv (pydevices-audioif from TestPyPI) if
# it's been set up, else the sibling audioif checkout's.
if [[ -x "$repo_dir/.venv/bin/python" ]]; then
    venv_python="$repo_dir/.venv/bin/python"
else
    venv_python="$repo_dir/../audioif/.venv/bin/python"
fi

pieces=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --piece) pieces+=("$2"); shift 2 ;;
        *) echo "usage: $0 [--piece NAME]..." >&2; exit 2 ;;
    esac
done

[[ -x "$venv_python" ]] || {
    echo "error: no audioif venv python at $venv_python" >&2
    exit 1
}

if [[ ${#pieces[@]} -eq 0 ]]; then
    # Every directory under soundtrack/ holding a composition.py.
    while IFS= read -r name; do
        pieces+=("$name")
    done < <("$venv_python" "$composition_dir/piece.py" --list)
fi

for piece in "${pieces[@]}"; do
    echo
    echo "################ $piece ################"
    echo "--- offline preview ---"
    "$venv_python" "$composition_dir/render_preview.py" --piece "$piece"

    echo "--- REAPER bounce + verification ---"
    "$repo_dir/reaper.sh" --render --piece "$piece"
done

echo
echo "done. deliverables in $soundtrack_dir/build:"
ls -la "$soundtrack_dir/build"/*.wav
