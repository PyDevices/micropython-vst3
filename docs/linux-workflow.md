# Linux generic-editor workflow

The Linux build is the same instrument as the Windows one: the same IPC
protocol, the same scripts, the same project state, and the same rendered PCM.
Only the installation paths and the sidecar executable differ.

## Install and scan

1. Close the DAW.
2. Unpack the release and copy `MicroPythonVST3.vst3` to `~/.vst3` for the
   current user, or `/usr/lib/vst3` for all users.
3. Start the DAW and request a VST3 rescan.
4. Insert **MicroPython Instrument** on an instrument track and use the host's
   generic parameter editor.

The bundle contains `Contents/x86_64-linux/`, holding the plug-in itself, the
`micropython-vst-engine` sidecar, the bootstrap, and the default instrument.
Both the sidecar and the shared object must keep their executable bit; the
release archive preserves it, but a copy through a tool that drops permissions
will leave the plug-in unable to start its engine.

## Controls

Identical to Windows: `Bypass`, `Reload Script`, `Macro 01` through `Macro 16`
under whatever labels the script declares, and the read-only `Engine Ready` and
`Engine Error` status parameters.

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
