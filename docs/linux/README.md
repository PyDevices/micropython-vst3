# MPVST on Linux

The Linux build is the same instrument as the Windows one: the same IPC
protocol, the same scripts, the same project state, and the same rendered PCM.
Only the installation paths and the sidecar executable differ.

## Start playing

`./install.sh` from the unpacked archive put the bundle in `~/.vst3`
(`--dir DIR` puts it elsewhere) and ran the plug-in scan for you. Every path
below is relative to the installed bundle, so `Contents/x86_64-linux` means
`~/.vst3/MPVST.vst3/Contents/x86_64-linux`.

Start the DAW and request a VST3 rescan. Then insert any of them - **TR-808**,
**Minimoog**, **Tape Delay** - and open its editor, or use the host's generic
parameter editor. **MPVST Script Host** runs whatever script
`MPVST_SCRIPT_PATH` points at, which is the loop for developing one that is
not in the library yet.

## Rescan after adding a script of your own

The list of plug-ins is not compiled in: it is
`Contents/Resources/moduleinfo.json`, which is both what the host reads to
enumerate them and what the plug-in reads to know which ones it offers. The
installer generated it for you, so there is nothing to do until you add,
remove or edit a script of your own. When you do, rerun the scanner from
`Contents/x86_64-linux`:

    ./mpvst-engine mpvst_scan_plugins.py

then rescan VST3 plug-ins in the DAW. The scanner needs nothing installed - it
is the engine itself, reading what each library module declares about itself.
`--list` prints what it found instead of writing the file.

## Installing by hand instead

Close the DAW, copy `MPVST.vst3` into `~/.vst3` (or `/usr/lib/vst3` for all
users), run the scanner command above once, then start the DAW and rescan.

The bundle contains `Contents/x86_64-linux/`, holding the plug-in itself, the
`mpvst-engine` sidecar, the bootstrap, and the default instrument.
Both the sidecar and the shared object must keep their executable bit; the
release archive preserves it, but a copy through a tool that drops permissions
will leave the plug-in unable to start its engine.

## Controls

Identical to Windows, including the plug-in's own editor: a patch selector, a
Reload button, a Bypass switch, a status light, and a slider per macro under
whatever labels the script declares. Click a control to focus it, then scroll
or swipe - sideways adjusts it, up and down moves between controls.

The editor is a plain X11 child window driven by the host's own run loop, so a
host that provides no `IRunLoop` gets no editor and the generic parameter
editor still works: `Bypass`, `Reload Script`, `Patch`, `Macro 01` through
`Macro 16`, and the read-only `Engine Ready` and `Engine Error` status
parameters.

## Develop a script

Set `MPVST_SCRIPT_PATH` to an absolute `.py` file before starting the DAW. Each
new instance reads that file, and toggling `Reload Script` off and on re-reads
it, so an edit reaches a running instance without reopening the project. Saving
the project embeds the source as it is on disk at that moment, after which the
project reopens the same way even if the original file moves or changes.

```bash
export MPVST_SCRIPT_PATH=$HOME/instruments/my_synth.py
reaper &
```

## Constraining the sidecar

`MPVST_HEAP_BYTES` caps the MicroPython heap for every instance started
afterwards, so a script that allocates without bound fails inside its own
sidecar rather than growing until it disturbs the DAW:

```bash
export MPVST_HEAP_BYTES=16777216
```

## Security model

Unchanged from Windows: a script runs in its own process with the file-system
permissions of the DAW user, and the shipped engine is built without sockets,
TLS and FFI, so a script cannot open a network connection or call into
arbitrary native code - but it can read and write your files. Process
isolation plus a narrowed interpreter, not a sandbox. Only load projects and
scripts you trust.

## Uninstall

Close the DAW, then `./install.sh --uninstall` from the unpacked archive
(add the same `--dir DIR` you installed with). Removing the `MPVST.vst3`
bundle by hand works too. Project files are untouched either way.
