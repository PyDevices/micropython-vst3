#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "$repo_dir/scripts/windows-paths.sh"
mpvst_load_windows_paths || exit 1
build_dir=${1:-$WIN_TEMP/mpvst-build}
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
archive="$dist_dir/$name-windows-x86_64.zip"

test -f "$bundle/Contents/x86_64-win/MPVST.vst3"
test -f "$bundle/Contents/x86_64-win/mpvst-engine.exe"
test -f "$bundle/Contents/x86_64-win/mpvst_bootstrap.py"
test -f "$bundle/Contents/x86_64-win/default_instrument.py"

stage_dir=$(mktemp -d)
cleanup() {
    rm -rf -- "$stage_dir"
}
trap cleanup EXIT

mkdir -p "$stage_dir/$name"
cp -a "$bundle" "$stage_dir/$name/"
cp "$repo_dir/docs/windows/README.md" "$stage_dir/$name/README.md"
cp "$repo_dir/LICENSE" "$stage_dir/$name/"

mkdir -p "$dist_dir"
rm -f -- "$archive"
(cd "$stage_dir" && cmake -E tar cf "$archive" --format=zip "$name")
# Written with the bare filename, not the build machine's path: a
# sidecar that names /home/someone/... cannot be verified by anyone
# who downloads it, because sha256sum -c looks for that exact path.
(cd "$(dirname "$archive")" && sha256sum "$(basename "$archive")") > "$archive.sha256"
echo "Created $archive"

# The installer is built from the same staging tree the archive was just
# made from, so the two cannot ship different bytes. It is skipped rather
# than fatal when NSIS is absent: the archive is a complete delivery on its
# own for anyone who would rather copy the bundle in by hand.
installer="$dist_dir/$name-windows-x86_64-setup.exe"
if [[ -x "$repo_dir/.deps/nsis/usr/bin/makensis" || -n "${MAKENSIS:-}" ]]; then
    rm -f -- "$installer"
    "$repo_dir/scripts/nsis-env.sh" \
        -DMPVST_VERSION="$version" \
        -DMPVST_STAGE="$stage_dir/$name" \
        -DMPVST_OUTFILE="$installer" \
        "$repo_dir/installer/windows.nsi" >/dev/null \
        || { echo "error: makensis failed" >&2; exit 1; }
    (cd "$(dirname "$installer")" && sha256sum "$(basename "$installer")") > "$installer.sha256"
    echo "Created $installer"
else
    echo "NSIS not fetched (scripts/fetch-nsis.sh); skipping the installer"
fi
