"""Resolve a piece name to its composition module and instrument directory.

Each piece is a composition module plus a directory of instrument scripts:

  perihelion   score/composition.py        score/instruments/
  <other>      score/<other>/composition.py  score/<other>/instruments/

A composition module exposes: TITLE, SAMPLE_RATE, MASTER_GAIN_DB,
TEMPO_MAP (rows of (beat, bpm) or (beat, bpm, ts_num, ts_den)),
TOTAL_BEATS, SONG_SECONDS, RENDER_SECONDS, SECTIONS (name, start_beat,
end_beat), TRACKS, beats_to_seconds(), track_gain(), macro_value(),
active_track_count(), and optionally ACTIVE_LIMIT (None for no limit).
"""

import importlib.util
import sys
from pathlib import Path

SCORE_DIR = Path(__file__).resolve().parent


def load_piece(name="perihelion"):
    """Return (composition_module, instruments_dir) for `name`."""
    if name == "perihelion":
        module_path = SCORE_DIR / "composition.py"
        instruments = SCORE_DIR / "instruments"
    else:
        module_path = SCORE_DIR / name / "composition.py"
        instruments = SCORE_DIR / name / "instruments"
    if not module_path.is_file():
        raise SystemExit("unknown piece %r (no %s)" % (name, module_path))
    spec = importlib.util.spec_from_file_location(
        "composition_" + name, module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module, instruments


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
