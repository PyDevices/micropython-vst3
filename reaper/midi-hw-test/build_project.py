#!/usr/bin/env python3
"""Build a minimal REAPER project that sends a deterministic MIDI note
sequence straight to a hardware MIDI output device - no VST instrument
anywhere in the signal path. For bring-up testing a MIDI device against a
board-side listener: REAPER is the note source, the device is the thing
under test.

Platform-neutral: this writes a plain .RPP text file and touches nothing
Windows- or Linux-specific. `run-midi-hw-test.sh` is the platform layer
that resolves REAPER's install/resource paths and launches the process;
this script only needs a device index and channel, which
`probe_devices.lua` (run via `run-midi-hw-test.sh --list-devices`) reports
for whatever machine you're on.

Usage: build_project.py <device_index> <channel_1_based> <out.RPP>

The device index and channel are packed into the track's I_MIDIHWOUT
value exactly the way REAPER itself does - confirmed against REAPER
7.79's own compiled-in ReaScript API documentation string:
    I_MIDIHWOUT : int * : track midi hardware output index, <0=disabled,
    low 5 bits are which channel (0=all, 1-16), next 5 bits are output
    device index (0-31)
(`strings reaper.exe | grep I_MIDIHWOUT`). The project's plain-text
`MIDIOUT %d %d` chunk line takes that same packed value as its first
field; the second is the I_MIDIHWOUT_SLOT hint, left at -1 (unset).
"""
import sys
import uuid

PPQ = 960
BPM = 120.0
PITCHES = [60, 64, 67, 72]  # C4 E4 G4 C5 (scientific pitch notation, 60=C4)
NOTE_NAMES = ["C4", "E4", "G4", "C5"]
VELOCITY = 100
REPEATS = 20  # 20 * 4 quarter notes * 0.5s/quarter = 40.0s exactly at 120 BPM


def guid():
    return "{%s}" % str(uuid.uuid4()).upper()


def build(dev_index, channel, track_name="MIDI HW Test"):
    """Return the project text as a single string."""
    assert 1 <= channel <= 16, "channel must be 1-16"
    assert 0 <= dev_index <= 31, "device index must be 0-31 (5 bits)"
    hwout_value = channel | (dev_index << 5)

    notes = []  # (start_beat, dur_beat, pitch, vel)
    for rep in range(REPEATS):
        for i, pitch in enumerate(PITCHES):
            beat = rep * len(PITCHES) + i
            notes.append((beat, 1.0, pitch, VELOCITY))
    total_beats = REPEATS * len(PITCHES)
    total_seconds = total_beats * 60.0 / BPM

    events = []  # (tick, order, message); order 0=note-off sorts before 1=note-on
    for start, dur, pitch, vel in notes:
        on = int(round(start * PPQ))
        off = int(round((start + dur) * PPQ))
        events.append((on, 1, "90 %02x %02x" % (pitch, vel)))
        events.append((off, 0, "80 %02x 00" % pitch))
    events.sort()

    lines = [
        '<REAPER_PROJECT 0.1 "7.79" 0',
        "  RIPPLE 0",
        "  TEMPO %.6f 4 4" % BPM,
        "  SAMPLERATE 48000 0 0",
        "  <TRACK %s" % guid(),
        '    NAME "%s"' % track_name,
        "    TRACKHEIGHT 0 0 0 0 0 0",
        "    VOLPAN 1 0 1 -1 1",
        "    MUTESOLO 0 0 0",
        "    NCHAN 2",
        "    FX 0",
        "    TRACKID %s" % guid(),
        "    PERF 0",
        "    MIDIOUT %d -1" % hwout_value,
        "    MAINSEND 1 0",
        "    <ITEM",
        "      POSITION 0",
        "      SNAPOFFS 0",
        "      LENGTH %.9f" % total_seconds,
        "      LOOP 0",
        "      ALLTAKES 0",
        "      FADEIN 0 0 0 1 0 0 0",
        "      FADEOUT 0 0 0 1 0 0 0",
        "      MUTE 0 0",
        "      SEL 0",
        "      IGUID %s" % guid(),
        "      IID 1",
        '      NAME "%s"' % track_name,
        "      VOLPAN 1 0 1 -1",
        "      SOFFS 0 0",
        "      PLAYRATE 1 1 0 -1 0 0.0025",
        "      CHANMODE 0",
        "      GUID %s" % guid(),
        "      <SOURCE MIDI",
        "        HASDATA 1 %d QN" % PPQ,
        "        CCINTERP 32",
        "        POOLEDEVTS %s" % guid(),
    ]
    cursor = 0
    for tick, _order, message in events:
        lines.append("        E %d %s" % (tick - cursor, message))
        cursor = tick
    end_tick = int(round(total_beats * PPQ))
    lines.append("        E %d b0 7b 00" % max(0, end_tick - cursor))  # all notes off
    lines += [
        "        CCINTERP 32",
        "        CHASE_CC_TAKEOFFS 1",
        "        GUID %s" % guid(),
        "        IGNTEMPO 0 120 4 4",
        "        SRCCOLOR 2",
        "        EVTFILTER 0 -1 -1 -1 -1 0 0 0 0 -1 -1 -1 -1 0 -1 0 -1 -1",
        "      >",
        "    >",
        "  >",
        ">",
    ]
    return "\n".join(lines) + "\n", total_seconds, len(notes)


def main():
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    dev_index = int(sys.argv[1])
    channel = int(sys.argv[2])
    out_path = sys.argv[3]

    text, total_seconds, n_notes = build(dev_index, channel)
    with open(out_path, "w") as f:
        f.write(text)

    print("wrote %s" % out_path)
    print("MIDIOUT device index %d channel %d -> I_MIDIHWOUT packed value %d"
          % (dev_index, channel, channel | (dev_index << 5)))
    print("%d notes (%s repeated %d times), %.1f s total"
          % (n_notes, " ".join(NOTE_NAMES), REPEATS, total_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
