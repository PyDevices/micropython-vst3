#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
build_dir=${1:-/mnt/c/Users/bradb/AppData/Local/Temp/micropython-vst3-build}
bundle="$build_dir/VST3/Release/MicroPythonVST3.vst3"
dist_dir="$repo_dir/dist"
archive="$dist_dir/MicroPythonVST3-0.2.0-windows-x86_64.zip"

test -f "$bundle/Contents/x86_64-win/MicroPythonVST3.vst3"
test -f "$bundle/Contents/x86_64-win/micropython-vst-engine.exe"
test -f "$bundle/Contents/x86_64-win/micropython_vst_bootstrap.py"
test -f "$bundle/Contents/x86_64-win/default_instrument.py"

stage_dir=$(mktemp -d)
cleanup() {
    rm -rf -- "$stage_dir"
}
trap cleanup EXIT

mkdir -p "$stage_dir/MicroPythonVST3-0.2.0"
cp -a "$bundle" "$stage_dir/MicroPythonVST3-0.2.0/"
cp "$repo_dir/README.md" "$stage_dir/MicroPythonVST3-0.2.0/"
cp "$repo_dir/docs/windows-workflow.md" "$stage_dir/MicroPythonVST3-0.2.0/"
cp -a "$repo_dir/examples" "$stage_dir/MicroPythonVST3-0.2.0/"

mkdir -p "$dist_dir"
rm -f -- "$archive"
(cd "$stage_dir" && cmake -E tar cf "$archive" --format=zip MicroPythonVST3-0.2.0)
sha256sum "$archive" > "$archive.sha256"
echo "Created $archive"
