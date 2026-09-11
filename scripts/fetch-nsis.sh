#!/usr/bin/env bash
# Fetch makensis, which builds the Windows installer.
#
#   ./scripts/fetch-nsis.sh
#
# NSIS cross-builds a Windows installer from Linux, so the release path needs
# no Windows toolchain and no hosted CI - the same posture as the rest of this
# repository, where the build runs here and the artifacts are made here.
#
# It lands in .deps/nsis rather than on the machine, because installing a
# toolchain system-wide needs root and this script deliberately needs none:
# it downloads the same two Ubuntu packages apt would and unpacks them into
# the dependency directory beside the VST3 SDK. Removing .deps removes it.
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
readonly NSIS_DIR="$PROJECT_DIR/.deps/nsis"

if [[ -x "$NSIS_DIR/usr/bin/makensis" ]]; then
    echo "NSIS already at $NSIS_DIR ($("$SCRIPT_DIR/nsis-env.sh" -VERSION))"
    exit 0
fi

command -v apt-get >/dev/null 2>&1 || {
    echo "error: apt-get is not available, so this script cannot fetch NSIS." \
         "Install makensis by hand and point MAKENSIS at it." >&2
    exit 1
}

download_dir=$(mktemp -d)
cleanup() { rm -rf -- "$download_dir"; }
trap cleanup EXIT

# nsis is the compiler; nsis-common carries the stubs and the Include tree it
# writes installers out of. makensis without the second one builds nothing.
( cd "$download_dir" && apt-get download nsis nsis-common )

mkdir -p "$NSIS_DIR"
for package in "$download_dir"/*.deb; do
    dpkg -x "$package" "$NSIS_DIR"
done

[[ -x "$NSIS_DIR/usr/bin/makensis" ]] || {
    echo "error: no makensis under $NSIS_DIR after unpacking" >&2
    exit 1
}

echo "NSIS ready at $NSIS_DIR ($("$SCRIPT_DIR/nsis-env.sh" -VERSION))"
