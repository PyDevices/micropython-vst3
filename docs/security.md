# What the shipped engine cannot do

Compositions, instruments, and racks are Python code, and some of it —
`mpvst_scan_plugins.py` reading module declarations — runs at plugin-scan time,
before you consciously play anything. Because people share pieces, the shipped
sidecar engine is built without **sockets, SSL or FFI**, so that a piece you
downloaded cannot reach the network whatever it contains. A hostile script
has no exfiltration
channel and no route to arbitrary native code; its blast radius is the
file I/O the engine legitimately needs for its own library.

This is a safe default, not a sandbox. You can rebuild the engine with
networking or FFI enabled and drop it into the bundle — at that point the
capability was your informed choice as the builder, which is exactly the
line this default draws: nothing a downloaded piece can switch on by
itself. Do not redistribute bundles containing a widened engine without
saying so.

The engine is built without those three at the source: the Windows build
skips the networking and FFI overlays, the Linux build compiles them out.
`scripts/build-micropython-engine.sh` is where that happens, and the
`vst3-engine` profile in `micropython-pydevices` is the record of it.
