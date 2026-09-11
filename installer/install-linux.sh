#!/usr/bin/env bash
# Install (or remove) the MPVST plug-in for the current user.
#
#   ./install.sh              install into ~/.vst3
#   ./install.sh --dir DIR    install into DIR instead
#   ./install.sh --uninstall  remove it again
#
# ~/.vst3 is the per-user directory the VST3 specification names and every
# current Linux host scans, so this needs no root and touches nothing
# outside your home. A system-wide install is `--dir /usr/local/lib/vst3`
# run with the rights to write there.
set -euo pipefail

bundle_name="MPVST.vst3"
source_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
target_dir="$HOME/.vst3"
uninstall=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dir) target_dir=${2:?--dir needs a directory}; shift 2 ;;
        --uninstall) uninstall=1; shift ;;
        -h|--help) sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \?//'; exit 0 ;;
        *) echo "error: unknown argument '$1'" >&2; exit 2 ;;
    esac
done

installed="$target_dir/$bundle_name"

if [[ "$uninstall" == 1 ]]; then
    if [[ ! -d "$installed" ]]; then
        echo "nothing to remove at $installed"
        exit 0
    fi
    rm -rf -- "$installed"
    echo "removed $installed"
    exit 0
fi

[[ -d "$source_dir/$bundle_name" ]] || {
    echo "error: no $bundle_name beside this script - run it from the" \
         "unpacked archive, not from a copy of the script alone." >&2
    exit 1
}

# A host that has the plug-in loaded holds these open, and so does any
# sidecar engine it left behind; replacing a bundle underneath a running DAW
# is how you get a half-written one.
if pgrep -x mpvst-engine >/dev/null 2>&1; then
    echo "error: a mpvst-engine sidecar is still running. Close" \
         "your DAW (and kill any orphaned engine) before installing." >&2
    exit 1
fi

mkdir -p "$target_dir"
# Replaced whole, never merged: a bundle holding files from two versions is
# worse than one that is simply absent, because a host will load it.
rm -rf -- "$installed"
cp -a "$source_dir/$bundle_name" "$installed"
chmod 755 "$installed/Contents/x86_64-linux/mpvst-engine" \
          "$installed/Contents/x86_64-linux/MPVST.so"

# Finished should mean finished: moduleinfo.json is what the host reads to
# enumerate the plug-ins. It ships generated, and a failure here leaves that
# valid file in place - so it is reported, not fatal. Same command the README
# gives for rescanning after adding a script of your own.
if ! (cd "$installed/Contents/x86_64-linux" && ./mpvst-engine mpvst_scan_plugins.py >/dev/null); then
    echo "warning: the plug-in scan failed; the list that shipped in the" \
         "bundle is unchanged." >&2
fi

echo "installed $installed"
echo
echo "Start your host and rescan plug-ins."
# The hint has to name the directory when it is not the default, or someone
# who installed elsewhere is told to run a command that removes nothing.
if [[ "$target_dir" == "$HOME/.vst3" ]]; then
    echo "Remove it again with: $source_dir/install.sh --uninstall"
else
    echo "Remove it again with: $source_dir/install.sh --dir '$target_dir' --uninstall"
fi
