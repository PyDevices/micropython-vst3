#!/usr/bin/env bash
# Clone the sibling repos the builds need. For
# scripts/build-micropython-engine.sh: cmods (the MicroPython + usermod
# build system) and audioif (the synthio/audiocore DSP the engine links).
# For the plug-in build: audiocomponents (the audioinstruments and
# audioeffects packages src/plugin/CMakeLists.txt stages into the bundle).
# Idempotent - safe to rerun.
#
#   ./scripts/fetch-sibling-repos.sh
#
# All three are expected as siblings of this repo's own parent directory,
# matching build-micropython-engine.sh's and the plug-in CMake defaults;
# CMODS_DIR overrides where cmods goes (audioif has no override -
# build-micropython-engine.sh always looks for it at
# "$workspace_dir/audioif"; MPVST_COMPONENTS_LIB points the plug-in build
# at an audiocomponents lib/ elsewhere, but the clone here still lands
# beside the others).
#
# audiocomponents is private until it is flipped public (tracked in
# audiocomponents#2). Until then its clone fails for anyone without access
# to the org repo, and this script stops there - it is cloned last so cmods
# and audioif have already landed.
#
# Deliberately does NOT force-update an already-cloned sibling (no
# `git reset --hard`): all three are commonly hand-edited alongside this
# repo, and a clone that already exists may be sitting on local commits
# nobody has pushed yet. If it's already there, this just fetches and
# reports how far behind/ahead of origin/main it is, and leaves updating
# it to you.
set -euo pipefail

repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
workspace_dir=$(cd "$repo_dir/.." && pwd)
cmods_dir=${CMODS_DIR:-"$workspace_dir/cmods"}
audioif_dir="$workspace_dir/audioif"
components_dir="$workspace_dir/audiocomponents"

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
clone_or_report audiocomponents "https://github.com/PyDevices/audiocomponents.git" "$components_dir"

echo "cmods:           $cmods_dir"
echo "audioif:         $audioif_dir"
echo "audiocomponents: $components_dir"
