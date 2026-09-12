"""Render a Reaper project to a WAV.

    python bounce.py source/my_song.rpp
    python bounce.py source/my_song.rpp --mp3
    python bounce.py my_song.rpp --out /tmp/song.wav --timeout 240

Drives Reaper headless and comes back with a file. It checks nothing and
imports nothing, so rendering needs Reaper and a Python interpreter.

Checking is `tools/audio_qc.py`. It reports loudness and true peak, and it
will tell you when a render is not a render at all - digital black, a silent
head or holes in the middle usually mean a plug-in never loaded.

Runs natively on Windows, where Reaper lives; under WSL it translates paths
and drives the same executable.

Rendering uses `-renderproject` against a temporary copy of the project with
`RENDER_FILE` and `RENDER_CFG` written in, so nothing has to be edited to be
bounced and the format is stated rather than inherited. `--mp3` swaps the
format block: Reaper ships libmp3lame, so that needs no external encoder and
turns a 41 MiB render into 2.3.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
from pathlib import Path
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


#: What Reaper renders. `RENDER_CFG` is a base64 struct whose first four bytes
#: name the format; the rest is the format's own settings. These two were read
#: out of projects Reaper itself wrote, not constructed - a wrong guess renders
#: silently in the wrong format.
FORMATS = {
    #  'evaw' - 24-bit WAV
    "wav": "ZXZhdxgAAQ==",
    #  'l3pm' - 128 kbps joint-stereo MP3, encoded by the libmp3lame.dll that
    #  ships with Reaper. No external encoder involved.
    "mp3": "bDNwbYAAAAAAAAAAAgAAAP////8EAAAAgAAAAAAAAAA=",
}


def with_format(project: str, fmt: str, wav: str) -> str:
    """A copy of the project rendering `fmt` to `wav`.

    RENDER_CFG has to be written as a `<RENDER_CFG ... >` block. Reaper does
    not accept it as an inline token - it reports "Project tokens not
    recognized: RENDER_CFG" and falls back to whatever format it last used,
    which is how an inline one can look like it works.
    """
    cfg = FORMATS[fmt]
    copy = os.path.join(os.path.dirname(os.path.abspath(project)),
                        ".mpvst-bounce-" + os.path.basename(project))
    # Native form, unmangled. A drive path survives either way, but a WSL path
    # becomes \\wsl.localhost\... and Reaper reads the forward-slash spelling of
    # that as relative - it renders into the project folder instead.
    target = to_host(wav)
    text = open(project, encoding="utf-8", errors="ignore").read()
    lines, out, skipping = text.splitlines(), [], False
    # Insert only what the project does not already state, or Reaper sees two
    # RENDER_FILE lines and stops to tell you so.
    wrote_file = bool(re.search(r'^\s*RENDER_FILE\s+"', text, re.M))
    wrote_cfg = bool(re.search(r"^\s*<?RENDER_CFG", text, re.M))
    have_file, have_cfg = wrote_file, wrote_cfg
    for line in lines:
        stripped = line.strip()
        if skipping:
            if stripped == ">":
                skipping = False
            continue
        if stripped.startswith("<RENDER_CFG"):
            out.extend(["  <RENDER_CFG", "    %s" % cfg, "  >"])
            skipping = True
            continue
        if re.match(r"\s*RENDER_CFG\s", line):
            out.extend(["  <RENDER_CFG", "    %s" % cfg, "  >"])
            continue
        if re.match(r'\s*RENDER_FILE\s+"', line):
            out.append('  RENDER_FILE "%s"' % target)
            continue
        out.append(line)
        if stripped.startswith("<REAPER_PROJECT"):
            if not have_file:
                out.append('  RENDER_FILE "%s"' % target)
                have_file = True
            if not have_cfg:
                out.extend(["  <RENDER_CFG", "    %s" % cfg, "  >"])
                have_cfg = True
    Path(copy).write_text("\n".join(out) + "\n", encoding="utf-8")
    return copy


def render_target(project: str) -> str | None:
    """The output path the project names, if it names one."""
    with open(project, "r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            found = re.match(r'\s*RENDER_FILE\s+"(.+)"\s*$', line)
            if found and found.group(1).strip():
                return found.group(1)
    return None


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
    parser.add_argument("--mp3", action="store_true",
                        help="render MP3 instead of the project's own format")
    args = parser.parse_args()

    reaper = find_reaper()
    fmt = "mp3" if args.mp3 else "wav"

    wav = args.out
    if wav is None:
        wav = render_target(args.project)
        if wav is None:
            raise SystemExit(
                "%s names no RENDER_FILE, so Reaper has nowhere to render. "
                "Pass --out." % args.project)
        if fmt == "mp3":
            wav = os.path.splitext(wav)[0] + ".mp3"
    if under_wsl() and re.match(r"^[A-Za-z]:", wav):
        wav = subprocess.run(["wslpath", "-u", wav], capture_output=True,
                             text=True).stdout.strip()

    # The project is always rewritten, even when it names its own output, so
    # the format is stated rather than inherited. A project with no RENDER_CFG
    # renders in whatever format Reaper last used - a quiet way to get an MP3
    # named .wav.
    project = with_format(args.project, fmt, wav)
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
        if os.path.isfile(project):
            os.remove(project)


if __name__ == "__main__":
    raise SystemExit(main())
