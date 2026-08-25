#!/usr/bin/env python3
"""Generate a piece's REAPER project.

Writes a complete .RPP where every track holds one MicroPython
Instrument instance whose script is embedded directly in synthesized VST3
state (the same byte layout REAPER itself saves), so the project opens with
no environment variables and no build passes. MIDI, the tempo map, volume
envelopes, and macro automation envelopes all come from composition.py.

Usage: generate_project.py [--piece NAME] [out.RPP]
"""

import base64
import struct
import sys
import uuid
from pathlib import Path

SCORE = Path(__file__).resolve().parent
sys.path.insert(0, str(SCORE))
from piece import load_piece, piece_arg  # noqa: E402

PIECE, ARGV = piece_arg(sys.argv[1:])
C, INSTRUMENTS = load_piece(PIECE)

PPQ = 960
VST_LINE = ('<VST "VST3i: MicroPython Instrument (PyDevices)" '
            'MicroPythonVST3.vst3 0 "" '
            '896536053{60A40168727C4E7DAAF808B790961DAA} ""')

# First macro's index among the visible parameters:
# 0 Bypass, 1 Reload Script, 2 Engine Ready, 3 Engine Error, 4.. macros.
FIRST_MACRO_PARAM = 4


def guid():
    return "{%s}" % str(uuid.uuid4()).upper()


def vst_chunk_lines(script_source, macros):
    """REAPER's base64 wrapper around our component state."""
    comp = struct.pack("<ii", 2, 0)                      # version, bypass
    for index in range(16):
        comp += struct.pack("<f", macros.get(index, 0.5))
    comp += struct.pack("<ii", 4, len(script_source))    # pipeline, bytes
    comp += script_source

    data = struct.pack("<II", len(comp), 1) + comp + b"\0" * 8
    header = struct.pack(
        "<11I", 0x35700DF5, 0xFEED5EEE, 0, 2, 1, 0, 2, 0, len(data), 1,
        0x0000FFFF)
    footer = b"\0" * 6

    lines = [base64.b64encode(header).decode()]
    encoded = base64.b64encode(data).decode()
    lines += [encoded[i:i + 128] for i in range(0, len(encoded), 128)]
    lines.append(base64.b64encode(footer).decode())
    return lines


def midi_events(notes):
    """Sorted (tick, order, bytes) with note-offs before note-ons."""
    events = []
    for start, dur, pitch, vel in notes:
        v = max(1, min(127, round(vel * 127)))
        on = int(round(start * PPQ))
        off = int(round((start + dur) * PPQ))
        if off <= on:
            off = on + 1
        events.append((on, 1, "90 %02x %02x" % (pitch, v)))
        events.append((off, 0, "80 %02x 00" % pitch))
    events.sort()
    return events


def check_no_same_pitch_overlap(track):
    spans = {}
    for start, dur, pitch, _vel in sorted(track["notes"]):
        end = start + dur
        last = spans.get(pitch)
        if last is not None and start < last - 1e-9:
            raise SystemExit(
                "%s: overlapping notes on pitch %d at beat %.2f"
                % (track["name"], pitch, start))
        spans[pitch] = end


def envelope_block(kind, header_extra, points):
    lines = ["    <%s%s" % (kind, header_extra)]
    lines += ["      EGUID %s" % guid(),
              "      ACT 1 -1",
              "      VIS 1 1 1",
              "      LANEHEIGHT 0 0",
              "      ARM 0",
              "      DEFSHAPE 0 -1 -1"]
    for time_s, value, shape in points:
        lines.append("      PT %.9f %.9f %d" % (time_s, value, shape))
    lines.append("    >")
    return lines


def track_block(track):
    check_no_same_pitch_overlap(track)
    script = (INSTRUMENTS / track["script"]).read_bytes()
    macros = {i: C.macro_value(track, i, 0.0) for i in range(16)}
    for i, v in track["macros"].items():
        macros.setdefault(i, v)

    item_len = C.beats_to_seconds(C.TOTAL_BEATS)
    lines = ["  <TRACK %s" % guid(),
             '    NAME "%s"' % track["name"],
             "    TRACKHEIGHT 0 0 0 0 0 0",
             "    VOLPAN 1 %.6f 1 -1 1" % track["pan"],
             "    MUTESOLO 0 0 0",
             "    NCHAN 2",
             "    FX 1",
             "    TRACKID %s" % guid(),
             "    PERF 0",
             "    MIDIOUT -1 -1",
             "    MAINSEND 1 0"]

    # Volume envelope carries the mix gain and the musical swells.
    vol_points = [(C.beats_to_seconds(beat),
                   (10.0 ** (track["gain_db"] / 20.0)) * mult, 0)
                  for beat, mult in track["vol"]]
    if not vol_points:
        vol_points = [(0.0, 10.0 ** (track["gain_db"] / 20.0), 0)]
    lines += envelope_block("VOLENV2", "", vol_points)

    lines.append("    <FXCHAIN")
    lines.append("      SHOW 0")
    lines.append("      LASTSEL 0")
    lines.append("      DOCKED 0")
    lines.append("      BYPASS 0 0 0")
    lines.append("      " + VST_LINE)
    for chunk_line in vst_chunk_lines(script, macros):
        lines.append("        " + chunk_line)
    lines.append("      >")
    lines.append("      FLOATPOS 0 0 0 0")
    lines.append("      FXID %s" % guid())
    for index in sorted(track["macro_env"]):
        env = track["macro_env"][index]
        points = [(C.beats_to_seconds(beat), value, 0)
                  for beat, value in env]
        lines += ["  " + l for l in envelope_block(
            "PARMENV", " %d 0 1 0.5" % (FIRST_MACRO_PARAM + index), points)]
    lines.append("      WAK 0 0")
    lines.append("    >")

    # One MIDI item spanning the song.
    lines += ["    <ITEM",
              "      POSITION 0",
              "      SNAPOFFS 0",
              "      LENGTH %.9f" % item_len,
              "      LOOP 0",
              "      ALLTAKES 0",
              "      FADEIN 0 0 0 1 0 0 0",
              "      FADEOUT 0 0 0 1 0 0 0",
              "      MUTE 0 0",
              "      SEL 0",
              "      IGUID %s" % guid(),
              "      IID 1",
              '      NAME "%s"' % track["name"],
              "      VOLPAN 1 0 1 -1",
              "      SOFFS 0 0",
              "      PLAYRATE 1 1 0 -1 0 0.0025",
              "      CHANMODE 0",
              "      GUID %s" % guid(),
              "      <SOURCE MIDI",
              "        HASDATA 1 %d QN" % PPQ,
              "        CCINTERP 32",
              "        POOLEDEVTS %s" % guid()]
    cursor = 0
    for tick, _order, message in midi_events(track["notes"]):
        lines.append("        E %d %s" % (tick - cursor, message))
        cursor = tick
    end_tick = int(round(C.TOTAL_BEATS * PPQ))
    lines.append("        E %d b0 7b 00" % max(0, end_tick - cursor))
    lines += ["        CCINTERP 32",
              "        CHASE_CC_TAKEOFFS 1",
              "        GUID %s" % guid(),
              "        IGNTEMPO 0 120 4 4",
              "        SRCCOLOR 2",
              "        EVTFILTER 0 -1 -1 -1 -1 0 0 0 0 -1 -1 -1 -1 0 -1 0"
              " -1 -1",
              "      >",
              "    >",
              "  >"]
    return lines


def tempo_block():
    lines = ["  <TEMPOENVEX",
             "    EGUID %s" % guid(),
             "    ACT 1 -1",
             "    VIS 1 0 1",
             "    LANEHEIGHT 0 0",
             "    ARM 0",
             "    DEFSHAPE 1 -1 -1"]
    for row in C.TEMPO_MAP:
        beat, bpm = row[0], row[1]
        if len(row) >= 4:
            # time-signature field: (denominator << 16) | numerator
            sig = (row[3] << 16) | row[2]
            lines.append("    PT %.9f %.6f 1 %d" % (C.beats_to_seconds(beat),
                                                    bpm, sig))
        else:
            lines.append("    PT %.9f %.6f 1" % (C.beats_to_seconds(beat),
                                                 bpm))
    lines.append("  >")
    return lines


def main():
    out = (Path(ARGV[0]) if ARGV
           else SCORE / "build" / (C.TITLE + ".RPP"))
    out.parent.mkdir(parents=True, exist_ok=True)

    master_vol = 10.0 ** (C.MASTER_GAIN_DB / 20.0)
    lines = ['<REAPER_PROJECT 0.1 "7.79" 0',
             "  RIPPLE 0",
             "  GROUPOVERRIDE 0 0 0",
             "  AUTOXFADE 129",
             "  TEMPO %.6f %d %d" % (C.TEMPO_MAP[0][1],
                 C.TEMPO_MAP[0][2] if len(C.TEMPO_MAP[0]) >= 4 else 4,
                 C.TEMPO_MAP[0][3] if len(C.TEMPO_MAP[0]) >= 4 else 4),
             "  SAMPLERATE %d 0 0" % C.SAMPLE_RATE,
             "  MASTER_VOLUME %.9f 0 -1 -1 1" % master_vol,
             "  MASTER_NCH 2 2"]
    lines += tempo_block()
    for track in C.TRACKS:
        lines += track_block(track)
    lines.append(">")

    out.write_text("\n".join(lines) + "\n")
    total_notes = sum(len(t["notes"]) for t in C.TRACKS)
    print("wrote %s (%d tracks, %d notes, %.1f s song, %.1f s with tail)"
          % (out, len(C.TRACKS), total_notes, C.SONG_SECONDS,
             C.RENDER_SECONDS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
