#!/usr/bin/env python3
"""Generate the DAW matrix's instrument-into-effect project.

Both instances get their scripts embedded in synthesized VST3 state, the
way a user's saved project carries them, so the test has no dependence on
the process-wide MPVST_SCRIPT_PATH developer file. That dependence is not
testable with two different scripts in one host: each instance re-reads
the shared file whenever the host restarts it, and refreshes its state
from it on save.

Usage: build_effect_project.py <out.RPP> <instrument.py> <effect.py>
"""

import base64
import struct
import sys
import uuid


def guid():
    return "{%s}" % str(uuid.uuid4()).upper()


def component_state(script, macros):
    comp = struct.pack("<ii", 2, 0)
    for index in range(16):
        comp += struct.pack("<f", macros.get(index, 0.5))
    comp += struct.pack("<ii", 4, len(script))
    return comp + script


def chunk_lines(header_words, script, macros):
    """REAPER's wrapper: header line, component data, 6-zero footer.

    header_words is the per-class word list with the data-size field left
    as None (third word from the end).
    """
    comp = component_state(script, macros)
    data = struct.pack("<II", len(comp), 1) + comp + b"\0" * 8
    words = [len(data) if w is None else w for w in header_words]
    header = struct.pack("<%dI" % len(words), *words)
    lines = [base64.b64encode(header).decode()]
    encoded = base64.b64encode(data).decode()
    lines += [encoded[i:i + 128] for i in range(0, len(encoded), 128)]
    lines.append(base64.b64encode(b"\0" * 6).decode())
    return lines


# Byte-exact header layouts captured from projects REAPER itself saved.
INSTRUMENT_HEADER = [0x35700DF5, 0xFEED5EEE, 0x0,
                     0x2, 0x1, 0x0, 0x2, 0x0,
                     None, 0x1, 0xFFFF]
EFFECT_HEADER = [0x5996706A, 0xFEED5EEE,
                 0x2, 0x1, 0x0, 0x2, 0x0,
                 0x2, 0x1, 0x0, 0x2, 0x0,
                 None, 0x1, 0xFFFF]

INSTRUMENT_VST = ('<VST "VST3i: MicroPython Instrument (PyDevices)" '
                  'MicroPythonVST3.vst3 0 "" '
                  '896536053{60A40168727C4E7DAAF808B790961DAA} ""')
EFFECT_VST = ('<VST "VST3: MicroPython Effect (PyDevices)" '
              'MicroPythonVST3.vst3 0 "" '
              '1503031402{910677E28594410985AD7A76CA68106C} ""')


def fx_block(vst_line, header_words, script, macros):
    lines = ["      " + vst_line]
    for line in chunk_lines(header_words, script, macros):
        lines.append("        " + line)
    lines += ["      >",
              "      FLOATPOS 0 0 0 0",
              "      FXID %s" % guid(),
              "      WAK 0 0"]
    return lines


def main():
    out, instrument_path, effect_path = sys.argv[1], sys.argv[2], sys.argv[3]
    instrument = open(instrument_path, "rb").read()
    effect = open(effect_path, "rb").read()

    lines = ['<REAPER_PROJECT 0.1 "7.79" 0',
             "  RIPPLE 0",
             "  TEMPO 120 4 4",
             "  SAMPLERATE 48000 0 0",
             "  <TRACK %s" % guid(),
             '    NAME "effect chain"',
             "    VOLPAN 1 0 1 -1 1",
             "    NCHAN 2",
             "    FX 1",
             "    TRACKID %s" % guid(),
             "    MAINSEND 1 0",
             "    <FXCHAIN",
             "      SHOW 0",
             "      LASTSEL 0",
             "      DOCKED 0",
             "      BYPASS 0 0 0"]
    # Macro 01 at zero keeps the gate at exactly 0.125.
    lines += fx_block(INSTRUMENT_VST, INSTRUMENT_HEADER, instrument, {0: 0.0})
    lines.append("      BYPASS 0 0 0")
    lines += fx_block(EFFECT_VST, EFFECT_HEADER, effect, {})
    lines += ["    >",
              "    <ITEM",
              "      POSITION 0",
              "      LENGTH 3",
              "      LOOP 0",
              "      IGUID %s" % guid(),
              "      IID 1",
              '      NAME "note"',
              "      GUID %s" % guid(),
              "      <SOURCE MIDI",
              "        HASDATA 1 960 QN",
              "        E 1920 90 3c 64",
              "        E 1920 80 3c 00",
              "        E 1920 b0 7b 00",
              "        GUID %s" % guid(),
              "        IGNTEMPO 0 120 4 4",
              "      >",
              "    >",
              "  >",
              ">"]
    with open(out, "w") as handle:
        handle.write("\n".join(lines) + "\n")
    print("wrote %s (instrument %d bytes, effect %d bytes)"
          % (out, len(instrument), len(effect)))


if __name__ == "__main__":
    main()
