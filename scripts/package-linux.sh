#!/usr/bin/env bash
# Package the Linux VST3 bundle, mirroring scripts/package-windows.sh.
set -euo pipefail

repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
build_dir=${1:-"$repo_dir/.build-linux"}
bundle="$build_dir/VST3/Release/MPVST.vst3"
dist_dir="$repo_dir/dist"
# VERSION at the repo root is the single source of truth; CMakeLists.txt
# reads the same file, so the binary and the archive around it cannot
# disagree about which version they are.
version=$(tr -d '[:space:]' < "$repo_dir/VERSION")
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || {
    echo "error: VERSION must hold a bare X.Y.Z, got '$version'" >&2
    exit 1
}
name="MPVST-$version"
archive="$dist_dir/$name-linux-x86_64.tar.gz"

test -f "$bundle/Contents/x86_64-linux/MPVST.so"
test -f "$bundle/Contents/x86_64-linux/mpvst-engine"
test -f "$bundle/Contents/x86_64-linux/mpvst_bootstrap.py"
test -f "$bundle/Contents/x86_64-linux/default_instrument.py"

stage_dir=$(mktemp -d)
cleanup() {
    rm -rf -- "$stage_dir"
}
trap cleanup EXIT

mkdir -p "$stage_dir/$name"
cp -a "$bundle" "$stage_dir/$name/"
cp "$repo_dir/docs/linux/README.md" "$stage_dir/$name/README.md"
cp "$repo_dir/LICENSE" "$stage_dir/$name/"
# Named install.sh in the archive: what someone looks for after unpacking is
# not a file named for the platform they already chose.
cp "$repo_dir/installer/install-linux.sh" "$stage_dir/$name/install.sh"
chmod 755 "$stage_dir/$name/install.sh"

# The engine and the shared object must stay executable through the archive.
chmod 755 "$stage_dir/$name/MPVST.vst3/Contents/x86_64-linux/mpvst-engine"
chmod 755 "$stage_dir/$name/MPVST.vst3/Contents/x86_64-linux/MPVST.so"

mkdir -p "$dist_dir"
rm -f -- "$archive"
tar -czf "$archive" -C "$stage_dir" "$name"
# Written with the bare filename, not the build machine's path: a
# sidecar that names /home/someone/... cannot be verified by anyone
# who downloads it, because sha256sum -c looks for that exact path.
(cd "$(dirname "$archive")" && sha256sum "$(basename "$archive")") > "$archive.sha256"

echo "Created $archive"
