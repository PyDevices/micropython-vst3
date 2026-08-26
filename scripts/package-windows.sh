#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "$repo_dir/scripts/lib/windows-paths.sh"
mpvst_load_windows_paths || exit 1
build_dir=${1:-$WIN_TEMP/micropython-vst3-build}
bundle="$build_dir/VST3/Release/MicroPythonVST3.vst3"
dist_dir="$repo_dir/dist"
# VERSION at the repo root is the single source of truth; CMakeLists.txt
# reads the same file, so the binary and the archive around it cannot
# disagree about which version they are.
version=$(tr -d '[:space:]' < "$repo_dir/VERSION")
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || {
    echo "error: VERSION must hold a bare X.Y.Z, got '$version'" >&2
    exit 1
}
name="MicroPythonVST3-$version"
archive="$dist_dir/$name-windows-x86_64.zip"

test -f "$bundle/Contents/x86_64-win/MicroPythonVST3.vst3"
test -f "$bundle/Contents/x86_64-win/micropython-vst-engine.exe"
test -f "$bundle/Contents/x86_64-win/micropython_vst_bootstrap.py"
test -f "$bundle/Contents/x86_64-win/default_instrument.py"

stage_dir=$(mktemp -d)
cleanup() {
    rm -rf -- "$stage_dir"
}
trap cleanup EXIT

mkdir -p "$stage_dir/$name"
cp -a "$bundle" "$stage_dir/$name/"
cp "$repo_dir/README.md" "$stage_dir/$name/"
cp "$repo_dir/docs/windows-workflow.md" "$stage_dir/$name/"
cp -a "$repo_dir/examples" "$stage_dir/$name/"

mkdir -p "$dist_dir"
rm -f -- "$archive"
(cd "$stage_dir" && cmake -E tar cf "$archive" --format=zip "$name")
sha256sum "$archive" > "$archive.sha256"
echo "Created $archive"
