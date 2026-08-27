# Windows generic-editor workflow

## Install and scan

1. Close the DAW.
2. Copy `MicroPythonVST3.vst3` to `%LOCALAPPDATA%\Programs\Common\VST3`
   for the current user, or `%COMMONPROGRAMFILES%\VST3` for all users.
3. Run the scanner once, from `Contents\\x86_64-win` inside the installed
   bundle, so the DAW can see the library:

       micropython-vst-engine.exe scan_plugins.py --write

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

The plug-in has an editor of its own: a patch selector, a Reload button, a
Bypass switch, an engine-status light, and a slider per macro, labelled with
whatever names the script declares. Click a control to focus it, then scroll
or swipe - sideways adjusts the focused control, up and down moves between
them. A drag or a burst of scrolling is recorded as one automation edit.

The same parameters are all there in the host's generic editor: `Bypass`,
`Reload Script`, `Patch`, and `Macro 01` through `Macro 16` (or the script's
labels). `Engine Ready` and integer `Engine Error` are read-only status
controls; error 1 means script load failed and error 2 means rendering failed.
A script that leaves the panel unable to build shows "Editor unavailable" and
keeps playing.

## Develop a script

Set `MPVST_SCRIPT_PATH` to an absolute `.py` file before starting the DAW. Each
new plug-in instance reads that source. To reload an existing instance, toggle
`Reload Script` off and then on. Syntax and runtime errors silence the graph but
leave the sidecar alive so a corrected script can be reloaded.
The host output uses a short fade-out, pipeline hold, and fade-in around reload
to avoid a discontinuity at the graph boundary.

Macro labels are optional metadata and do not alter automation IDs:

```python
# mpvst-macro-labels: Gain | Tone | Attack | Release
```

When the DAW saves a project, state v2 embeds the script source, macro values,
and engine pipeline setting. The project therefore reopens after the original
development file is moved or deleted. Embedded source is limited to 1 MiB.

## Security model

MicroPython scripts run with unrestricted desktop-process capabilities in a
separate process for each plug-in instance. They can access files, networking,
FFI, sockets, and TLS with the permissions of the DAW user. Only load projects
and scripts you trust. This is process isolation for stability, not a security
sandbox.

## Uninstall

Close the DAW, remove the installed `MicroPythonVST3.vst3` bundle, then rescan
VST3 plug-ins. Project files remain untouched.
