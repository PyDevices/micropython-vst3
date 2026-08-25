#!/usr/bin/env bash
# Download and portable-install the pinned REAPER build used by
# tools/daw-matrix/ and tools/piece/launch.sh. Idempotent - skips if the
# expected binary already exists.
#
#   ./scripts/install-reaper-portable.sh [--platform linux|windows]
#
# Defaults to installing for both linux and windows when run under WSL
# (both are reachable from here); pass --platform to install just one.
# REAPER_EXE / REAPER_RESOURCE (same env vars tools/daw-matrix/ and
# tools/piece/launch.sh read) override the install location.
set -euo pipefail

REAPER_VERSION=779

repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cache_dir="$repo_dir/.deps/reaper-installers"
mkdir -p "$cache_dir"

platform=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --platform) platform="$2"; shift 2 ;;
        *) echo "usage: $0 [--platform linux|windows]" >&2; exit 2 ;;
    esac
done

have_wsl_windows() {
    [[ -d /mnt/c/Users ]] && command -v powershell.exe >/dev/null 2>&1
}

windows_username() {
    powershell.exe -NoProfile -Command '[Environment]::UserName' 2>/dev/null | tr -d '\r\n'
}

install_linux() {
    local exe="${REAPER_EXE:-$HOME/opt/REAPER/reaper}"
    local install_root
    install_root=$(dirname "$(dirname "$exe")")  # <install_root>/REAPER/reaper
    if [[ -x "$exe" ]]; then
        echo "linux: already installed at $exe"
        return 0
    fi

    local tarball="$cache_dir/reaper${REAPER_VERSION}_linux_x86_64.tar.xz"
    if [[ ! -f "$tarball" ]]; then
        echo "linux: downloading REAPER $REAPER_VERSION"
        curl -sL "https://www.reaper.fm/files/7.x/reaper${REAPER_VERSION}_linux_x86_64.tar.xz" \
            -o "$tarball"
    fi

    local extract_dir="$cache_dir/reaper${REAPER_VERSION}_linux_x86_64"
    rm -rf "$extract_dir"
    tar -xJf "$tarball" -C "$cache_dir"

    mkdir -p "$install_root"
    "$extract_dir/install-reaper.sh" --install "$install_root" --quiet

    if [[ ! -x "$exe" ]]; then
        echo "error: linux install did not produce $exe" >&2
        return 1
    fi
    echo "linux: installed at $exe"
}

install_windows() {
    if ! have_wsl_windows; then
        echo "windows: no Windows host reachable from here (not running under WSL), skipping"
        return 0
    fi
    # REAPER_EXE for the Windows side is a WSL path (/mnt/c/...). $USER is
    # the WSL Linux username, not the Windows one, so ask Windows directly
    # rather than guessing or hardcoding one.
    local win_user
    win_user=$(windows_username)
    if [[ -z "$win_user" ]]; then
        echo "windows: could not determine the Windows username via powershell.exe; set REAPER_EXE explicitly" >&2
        return 1
    fi
    local exe="${REAPER_EXE:-/mnt/c/Users/$win_user/REAPER/reaper.exe}"
    if [[ -x "$exe" ]]; then
        echo "windows: already installed at $exe"
        return 0
    fi
    local install_dir
    install_dir=$(dirname "$exe")
    mkdir -p "$install_dir"

    local installer="$cache_dir/reaper${REAPER_VERSION}_x64-install.exe"
    if [[ ! -f "$installer" ]]; then
        echo "windows: downloading REAPER $REAPER_VERSION"
        if ! curl -sL -A "Mozilla/5.0" -e "https://reaper.fm" \
            -o "$installer" \
            "https://www.reaper.fm/files/7.x/reaper${REAPER_VERSION}_x64-install.exe"; then
            rm -f "$installer"
            echo "windows: download failed. Manual fallback:" >&2
            echo "  1. Download https://www.reaper.fm/files/7.x/reaper${REAPER_VERSION}_x64-install.exe" >&2
            echo "  2. Run it with: /S /D=$(wslpath -w "$install_dir")" >&2
            return 1
        fi
    fi

    # /S = silent (no install wizard), /D=<dir> must be the last argument,
    # unquoted, and a native Windows path. The installer places reaper.exe
    # directly in <dir> (no nested REAPER/ subfolder, unlike the Linux
    # tarball). /S suppresses the wizard but NOT the UAC elevation prompt -
    # this installer requests admin regardless of target directory, even a
    # plain Temp folder - so this step is not fully unattended: a human at
    # the keyboard has to approve one UAC dialog.
    echo "windows: launching installer - approve the UAC prompt if one appears"
    local win_dir
    win_dir=$(wslpath -w "$install_dir")
    "$installer" /S "/D=$win_dir"

    if [[ ! -x "$exe" ]]; then
        echo "error: windows install did not produce $exe" >&2
        return 1
    fi
    echo "windows: installed at $exe"
}

case "$platform" in
    linux) install_linux ;;
    windows) install_windows ;;
    "")
        install_linux
        install_windows
        ;;
    *) echo "usage: $0 [--platform linux|windows]" >&2; exit 2 ;;
esac
