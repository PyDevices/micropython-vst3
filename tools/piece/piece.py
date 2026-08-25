"""Resolve a piece name to its composition module and instrument directory.

soundtrack/ is example content, not infrastructure: treat it as
disposable (it might be renamed, restructured, or deleted independently
of this tooling). This is the one place that hardcodes its location.

Each piece lives in its own subdirectory of soundtrack/:

  soundtrack/<Piece>/composition.py
  soundtrack/<Piece>/instruments/*.py

Piece names are matched case-insensitively, so `--piece automata` finds
`Automata/`. Instruments are owned per piece on purpose: the scripts are
the patches, and the generated projects embed them byte-for-byte, so a
shared library would let a tweak made for a new piece silently change how
an old one renders. Starting a new piece means copying the closest
existing instrument and letting it diverge.

A composition module exposes: TITLE, SAMPLE_RATE, MASTER_GAIN_DB,
TEMPO_MAP (rows of (beat, bpm) or (beat, bpm, ts_num, ts_den)),
TOTAL_BEATS, SONG_SECONDS, RENDER_SECONDS, SECTIONS (name, start_beat,
end_beat), TRACKS, beats_to_seconds(), track_gain(), macro_value(),
active_track_count(), and optionally ACTIVE_LIMIT (None for no limit)
and CLIMAX_SECTION.
"""

import importlib.util
import sys
from pathlib import Path

SOUNDTRACK_DIR = Path(__file__).resolve().parent.parent.parent / "soundtrack"


def available_pieces():
    """{lowercase name: piece directory} for every piece present."""
    return {p.name.lower(): p for p in sorted(SOUNDTRACK_DIR.iterdir())
            if p.is_dir() and (p / "composition.py").is_file()}


def load_piece(name="perihelion"):
    """Return (composition_module, instruments_dir) for `name`."""
    pieces = available_pieces()
    piece_dir = pieces.get(name.lower())
    if piece_dir is None:
        raise SystemExit("unknown piece %r (have: %s)"
                         % (name, ", ".join(sorted(pieces)) or "none"))
    module_path = piece_dir / "composition.py"
    spec = importlib.util.spec_from_file_location(
        "composition_" + piece_dir.name.lower(), module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module, piece_dir / "instruments"


def piece_arg(argv):
    """Pop --piece <name> out of argv; returns (name, remaining_argv)."""
    name = "perihelion"
    rest = []
    skip = False
    for i, arg in enumerate(argv):
        if skip:
            skip = False
            continue
        if arg == "--piece":
            name = argv[i + 1]
            skip = True
        else:
            rest.append(arg)
    return name, rest


if __name__ == "__main__":
    # `piece.py --list` prints one piece name per line, for shell callers
    # that need to iterate every piece (see render-all.sh).
    import sys
    if sys.argv[1:2] == ["--list"]:
        for _name in available_pieces():
            print(_name)
    else:
        raise SystemExit("usage: piece.py --list")
