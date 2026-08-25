#!/usr/bin/env bash
# Clone the sibling repos scripts/build-micropython-engine.sh needs: cmods
# (the MicroPython + usermod build system) and audioif (the synthio/
# audiocore DSP the engine links). Idempotent - safe to rerun.
#
#   ./scripts/fetch-sibling-repos.sh
#
# Both are expected as siblings of this repo's own parent directory,
# matching build-micropython-engine.sh's defaults; CMODS_DIR overrides
# where cmods goes (audioif has no override - build-micropython-engine.sh
# always looks for it at "$workspace_dir/audioif").
#
# Deliberately does NOT force-update an already-cloned sibling (no
# `git reset --hard`): both cmods and audioif are commonly hand-edited
# alongside this repo, and a clone that already exists may be sitting on
# local commits nobody has pushed yet. If it's already there, this just
# fetches and reports how far behind/ahead of origin/main it is, and
# leaves updating it to you.
set -euo pipefail

repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
workspace_dir=$(cd "$repo_dir/.." && pwd)
cmods_dir=${CMODS_DIR:-"$workspace_dir/cmods"}
audioif_dir="$workspace_dir/audioif"

clone_or_report() {
    local name="$1" url="$2" dir="$3"
    if [[ -d "$dir/.git" ]]; then
        git -C "$dir" fetch --quiet origin main
        local ahead behind
        ahead=$(git -C "$dir" rev-list --count origin/main..HEAD)
        behind=$(git -C "$dir" rev-list --count HEAD..origin/main)
        local dirty=""
        [[ -n "$(git -C "$dir" status --porcelain)" ]] && dirty=" (uncommitted changes)"
        echo "$name: already cloned at $dir - $ahead ahead / $behind behind origin/main$dirty"
    else
        echo "$name: cloning to $dir"
        git clone "$url" "$dir"
    fi
}

clone_or_report cmods "https://github.com/PyDevices/cmods.git" "$cmods_dir"
clone_or_report audioif "https://github.com/PyDevices/audioif.git" "$audioif_dir"

echo "cmods:   $cmods_dir"
echo "audioif: $audioif_dir"
