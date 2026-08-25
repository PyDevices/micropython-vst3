#!/usr/bin/env bash
# Package the Linux VST3 bundle, mirroring tools/package-windows.sh.
set -euo pipefail

repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
build_dir=${1:-"$repo_dir/build-linux"}
bundle="$build_dir/VST3/Release/MicroPythonVST3.vst3"
dist_dir="$repo_dir/dist"
archive="$dist_dir/MicroPythonVST3-0.1.0-linux-x86_64.tar.gz"

test -f "$bundle/Contents/x86_64-linux/MicroPythonVST3.so"
test -f "$bundle/Contents/x86_64-linux/micropython-vst-engine"
test -f "$bundle/Contents/x86_64-linux/micropython_vst_bootstrap.py"
test -f "$bundle/Contents/x86_64-linux/default_instrument.py"

stage_dir=$(mktemp -d)
cleanup() {
    rm -rf -- "$stage_dir"
}
trap cleanup EXIT

mkdir -p "$stage_dir/MicroPythonVST3-0.1.0"
cp -a "$bundle" "$stage_dir/MicroPythonVST3-0.1.0/"
cp "$repo_dir/README.md" "$stage_dir/MicroPythonVST3-0.1.0/"
cp "$repo_dir/docs/linux-workflow.md" "$stage_dir/MicroPythonVST3-0.1.0/"
cp -a "$repo_dir/examples" "$stage_dir/MicroPythonVST3-0.1.0/"

# The engine and the shared object must stay executable through the archive.
chmod 755 "$stage_dir/MicroPythonVST3-0.1.0/MicroPythonVST3.vst3/Contents/x86_64-linux/micropython-vst-engine"
chmod 755 "$stage_dir/MicroPythonVST3-0.1.0/MicroPythonVST3.vst3/Contents/x86_64-linux/MicroPythonVST3.so"

mkdir -p "$dist_dir"
rm -f -- "$archive"
tar -czf "$archive" -C "$stage_dir" MicroPythonVST3-0.1.0
sha256sum "$archive" > "$archive.sha256"

echo "Created $archive"
