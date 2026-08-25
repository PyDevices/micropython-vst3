# Windows generic-editor workflow

## Install and scan

1. Close the DAW.
2. Copy `MicroPythonVST3.vst3` to `%LOCALAPPDATA%\Programs\Common\VST3`
   for the current user, or `%COMMONPROGRAMFILES%\VST3` for all users.
3. Start the DAW and request a VST3 rescan.
4. Insert **MicroPython Instrument** on an instrument track and use the host's
   generic parameter editor.

The initial release has no custom LVGL editor. Its visible controls are
`Bypass`, `Reload Script`, and `Macro 01` through `Macro 16` (or labels supplied
by the script). `Engine Ready` and integer `Engine Error` are read-only status
controls; error 1 means script load failed and error 2 means rendering failed.

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
