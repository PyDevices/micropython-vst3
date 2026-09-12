# MPVST

Programmable VST3 instruments and audio effects backed by dedicated
MicroPython engine processes. One bundle ships a whole library: every
`audioinstruments` module and every `audioeffects` class appears in the
DAW's browser under its own name and category - **TR-808** under
Instrument|Drum, **Tape Delay** under Fx|Delay - alongside two generic
**MPVST Script Host** classes that run any script you point them at.

Windows and Linux both ship, each with an editor of its own: a panel built
from whatever the instance declares - a patch selector, a bypass switch, a
status light and a slider per macro - and your host's generic parameter
editor reaches everything either way. The same project renders identical
audio on both platforms.

Every instance runs its Python in a separate sidecar process, so a script
that loops forever or exhausts memory takes down its own sidecar and gets
restarted rather than taking the DAW with it. The audio callback itself
stays native and real-time safe.

## Install it

Nothing has to be built to use the plug-in - the archives carry everything,
including the sidecar engine. There is no published release yet; until there
is, `scripts/package-linux.sh` and `scripts/package-windows.sh` build the
same artifacts into the ignored `dist/`.

- **Windows:** run `MPVST-<version>-windows-x86_64-setup.exe`.
  It installs for the current user, so there is no UAC prompt. That also
  decides where the uninstaller shows up: Settings -> Apps -> Installed
  apps, not the old Control Panel "Programs and Features" list, which is
  machine-wide installs only. Close your DAW first: a host that has the
  plug-in loaded holds its files open.
- **Linux:** unpack `MPVST-<version>-linux-x86_64.tar.gz` and run
  the `install.sh` inside it. It copies the bundle to `~/.vst3`; `--dir`
  puts it somewhere else and `--uninstall` removes it.

Then rescan plug-ins in your host - and make it a real rescan, not a
restart. A host caches what it found last time against the bundle's
contents, and REAPER was observed holding entries from an earlier build
after an install (Preferences -> Plug-ins -> VST -> Re-scan clears it).
The bundle registers a named plug-in per library instrument and effect,
plus the two script hosts; `mpvst_scan_plugins.py --list` prints the
current set.

## Use it

[**Windows**](docs/windows/README.md) and [**Linux**](docs/linux/README.md)
each have a page covering what you just installed: where the bundle went,
the editor and its parameters, rescanning after you add a script of your
own, and how to point an instance at a file you are editing. The installer
puts the one for your platform beside the uninstaller, so it is also there
after you install.

## Known limitations

- No host-visible diagnostic string. Both editors show only the ready and
  error parameters; the bounded diagnostic text is available through the
  transport API.
- The editor is one generic panel. Per-script panels, a shared knob widget,
  meters, and resizable or zoomable editors are all deferred.
- State embeds one source file, not a dependency bundle. Imports must
  resolve in the sidecar's own MicroPython environment.
- `MPVST_SCRIPT_PATH` is process-wide, so two developer-file instances
  cannot follow different scripts - they re-read it on restart and on
  save. Projects that need per-instance scripts embed them in state
  instead, which `reaper/matrix/build_effect_project.py` demonstrates by
  synthesizing the chunks directly.
- The 2,080 hidden MIDI parameters are standards-compliant and
  validator-clean but unprofiled for scan and project-load overhead in
  real DAWs.
- The installers are not code signed, so Windows SmartScreen warns on
  first run and macOS is not a target at all.
- The Linux REAPER used for testing runs under WSLg with no audio device.
  Real-time playback on Linux hardware has not been exercised.
- REAPER is the only DAW tested.

## Going further

- [**Writing your own instruments and effects**](docs/writing-scripts.md) -
  what a script declares, how macros and patches reach it, what the
  library gives you to build on. Needs nothing built.
- [**Working on MPVST itself**](docs/development.md) - repository layout,
  prerequisites, building the plug-in and the sidecar engine, the test
  suite, the DAW harnesses, cutting a release.
- [**What the shipped engine cannot do**](docs/security.md) - no sockets,
  no SSL, no FFI, and why a plug-in that runs other people's code ships
  that way.
- [**Architecture**](docs/architecture/ipc-v1.md) - the shared-memory
  protocol between plug-in and sidecar, with
  [the editor's half](docs/architecture/ui-v1.md) alongside it.

## License

MIT, in [LICENSE](LICENSE) — the same terms as the rest of PyDevices.

That covers this repository's own source. The Steinberg VST3 SDK is **not**
vendored here: `scripts/fetch-vst3-sdk.sh` clones it into `.deps/`, which is
ignored. It carries its own dual license (GPLv3 or a proprietary Steinberg
agreement), and anyone distributing a **built** plug-in binary has to satisfy
one of those two for the SDK it links. Building from source for your own use
does not change anything here.
