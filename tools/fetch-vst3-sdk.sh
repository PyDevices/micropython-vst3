#!/usr/bin/env bash
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
readonly SDK_DIR="$PROJECT_DIR/.deps/vst3sdk"
readonly SDK_REPOSITORY="https://github.com/steinbergmedia/vst3sdk.git"
readonly SDK_COMMIT="3cdf9ca5d1f5b1b21e0a86832aa4abe55607bd96"

mkdir -p "$PROJECT_DIR/.deps"

if [[ ! -d "$SDK_DIR/.git" ]]; then
    git clone --no-checkout "$SDK_REPOSITORY" "$SDK_DIR"
fi

git -C "$SDK_DIR" fetch --depth 1 origin "$SDK_COMMIT"
git -C "$SDK_DIR" checkout --detach --force "$SDK_COMMIT"
git -C "$SDK_DIR" submodule update --init --force --depth 1 \
    base cmake pluginterfaces public.sdk

echo "VST3 SDK ready at $SDK_DIR ($SDK_COMMIT)"

