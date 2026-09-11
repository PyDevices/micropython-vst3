#!/usr/bin/env bash
# Run the fetched makensis with the environment it needs.
#
#   ./scripts/nsis-env.sh [makensis arguments...]
#
# makensis finds its stubs through NSISDIR. The packaged binary expects them
# at /usr/share/nsis, which is exactly where they are NOT when the package is
# unpacked into .deps instead of installed - so every call goes through here
# rather than through a path that works only on the machine that built it.
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
readonly NSIS_DIR="$PROJECT_DIR/.deps/nsis"

makensis=${MAKENSIS:-"$NSIS_DIR/usr/bin/makensis"}
[[ -x "$makensis" ]] || {
    echo "error: no makensis at $makensis - run scripts/fetch-nsis.sh" >&2
    exit 1
}

NSISDIR="$NSIS_DIR/usr/share/nsis" exec "$makensis" "$@"
