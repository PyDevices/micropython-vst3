"""Render a Reaper project to a WAV.

    python bounce.py source/my_song.rpp
    python bounce.py my_song.rpp --out /tmp/song.wav --timeout 240

Drives Reaper headless and comes back with a file. It checks nothing and
imports nothing, so rendering needs Reaper and a Python interpreter.

Checking is `tools/audio_qc.py`. It reports loudness and true peak, and it
will tell you when a render is not a render at all - digital black, a silent
head or holes in the middle usually mean a plug-in never loaded.

Runs natively on Windows, where Reaper lives; under WSL it translates paths
and drives the same executable.

Rendering uses `-renderproject`, which takes its output path and format from
the project itself. Projects that do not name one - ours do not - get a
temporary copy with `RENDER_FILE` set, so nothing has to be edited to be
bounced.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import time

def under_wsl() -> bool:
    try:
        with open("/proc/version") as handle:
            return "microsoft" in handle.read().lower()
    except OSError:
        return False


def to_host(path: str) -> str:
    """A path Reaper will understand, whichever side we are running from."""
    if not under_wsl():
        return path
    return subprocess.run(["wslpath", "-w", os.path.abspath(path)],
                          capture_output=True, text=True,
                          check=True).stdout.strip()


def find_reaper() -> str:
    explicit = os.environ.get("REAPER_EXE")
    if explicit:
        return explicit
    candidates = []
    if under_wsl():
        profile = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             "[Environment]::GetFolderPath('UserProfile')"],
            capture_output=True, text=True).stdout.strip().rstrip("\\")
        if profile:
            candidates.append(subprocess.run(
                ["wslpath", "-u", profile + "\\REAPER\\reaper.exe"],
                capture_output=True, text=True).stdout.strip())
    candidates += [
        os.path.expanduser("~/REAPER/reaper.exe"),
        r"C:\Program Files\REAPER (x64)\reaper.exe",
        "/usr/bin/reaper", "/opt/REAPER/reaper",
    ]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    raise SystemExit("Reaper not found. Set REAPER_EXE to its full path.")


def render_target(project: str) -> str | None:
    """The output path the project names, if it names one."""
    with open(project, "r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            found = re.match(r'\s*RENDER_FILE\s+"(.+)"\s*$', line)
            if found and found.group(1).strip():
                return found.group(1)
    return None


def with_render_file(project: str, wav: str, workdir: str) -> str:
    """A copy of the project that renders to `wav`.

    Written beside the original, not in a temp directory: Reaper resolves a
    project's relative paths against the folder the project is in, so a copy
    somewhere else is a different project.
    """
    del workdir
    copy = os.path.join(os.path.dirname(os.path.abspath(project)),
                        ".mpvst-bounce-" + os.path.basename(project))
    target = to_host(wav).replace("\\", "/")
    wrote = False
    with open(project, "r", encoding="utf-8", errors="ignore") as src, \
            open(copy, "w", encoding="utf-8") as dst:
        for line in src:
            if re.match(r'\s*RENDER_FILE\s+"', line):
                dst.write('  RENDER_FILE "%s"\n' % target)
                wrote = True
            else:
                dst.write(line)
                # RENDER_FILE belongs in the project header, so if the project
                # has none, add it on the line after <REAPER_PROJECT.
                if not wrote and line.lstrip().startswith("<REAPER_PROJECT"):
                    dst.write('  RENDER_FILE "%s"\n' % target)
                    wrote = True
    return copy


def render(project: str, wav: str, reaper: str, timeout: int) -> None:
    if os.path.isfile(wav):
        os.remove(wav)
    os.makedirs(os.path.dirname(os.path.abspath(wav)), exist_ok=True)
    command = [reaper, "-nosplash", "-newinst", "-renderproject",
               to_host(project)]
    print(" ".join(command))
    try:
        subprocess.run(command, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise SystemExit("Reaper did not finish within %ds" % timeout)
    for _ in range(40):                       # the file lands after the exit
        if os.path.isfile(wav) and os.path.getsize(wav) > 1000:
            return
        time.sleep(0.25)
    raise SystemExit("No WAV at %s - the render produced nothing." % wav)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project", help=".RPP to render")
    parser.add_argument("--out", help="WAV to write (default: the project's "
                                      "own RENDER_FILE)")
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()

    reaper = find_reaper()
    project, wav, workdir = args.project, args.out, None
    if wav is None:
        wav = render_target(project)
        if wav is None:
            raise SystemExit(
                "%s names no RENDER_FILE, so Reaper has nowhere to render. "
                "Pass --out." % project)
        if under_wsl() and re.match(r"^[A-Za-z]:", wav):
            wav = subprocess.run(["wslpath", "-u", wav], capture_output=True,
                                 text=True).stdout.strip()
    else:
        project = with_render_file(project, wav, None)
        workdir = project              # a single file to remove, not a tree
    try:
        render(project, wav, reaper, args.timeout)
        print("wrote %s" % wav)
        # Printed rather than run: rendering needs nothing but Reaper.
        checker = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "..", "tools", "audio_qc.py")
        if os.path.isfile(checker):
            print("  check it with: python %s %s"
                  % (os.path.relpath(checker), wav))
        else:
            print("  to check it, see tools/audio_qc.py in the MPVST repo")
        return 0
    finally:
        if workdir and os.path.isfile(workdir):
            os.remove(workdir)


if __name__ == "__main__":
    raise SystemExit(main())
