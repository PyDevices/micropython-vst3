# Linux workflow

The Linux build is the same instrument as the Windows one: the same IPC
protocol, the same scripts, the same project state, and the same rendered PCM.
Only the installation paths and the sidecar executable differ.

## Install and scan

1. Close the DAW.
2. Unpack the release and copy `MicroPythonVST3.vst3` to `~/.vst3` for the
   current user, or `/usr/lib/vst3` for all users.
3. Run the scanner once, from `Contents/x86_64-linux` inside the installed
   bundle, so the DAW can see the library:

       ./micropython-vst-engine scan_plugins.py --write

   It writes `Contents/Resources/moduleinfo.json`, which is both what the
   host reads to list the plug-ins and what the plug-in reads to know which
   ones it offers. The scanner needs nothing installed - it is the engine
   itself, reading what each library module declares about itself. Run it
   again after adding or editing a script.
4. Start the DAW and request a VST3 rescan.
5. Insert any of them - **TR-808**, **Minimoog**, **Tape Delay** - and open
   its editor, or use the host's generic parameter editor. **MicroPython
   Script Host** runs whatever script `MPVST_SCRIPT_PATH` points at, which
   is the loop for developing one that is not in the library yet.

The bundle contains `Contents/x86_64-linux/`, holding the plug-in itself, the
`micropython-vst-engine` sidecar, the bootstrap, and the default instrument.
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

Unchanged from Windows: MicroPython scripts run with the full capabilities of
the desktop user in a separate process per instance. They can reach files,
networking, FFI, and TLS. The separate process buys stability, not a sandbox.
Only load projects and scripts you trust.

## Uninstall

Close the DAW, remove the installed `MicroPythonVST3.vst3` bundle from `~/.vst3`
or `/usr/lib/vst3`, then rescan. Project files are untouched.
