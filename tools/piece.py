"""Resolve a piece name to its composition module and instrument directory.

soundtrack/ is example content, not infrastructure: treat it as
disposable (it might be renamed, restructured, or deleted independently
of this tooling). This is the one place that hardcodes its location.

Each piece lives in its own subdirectory of soundtrack/:

  soundtrack/<Piece>/composition.py
  soundtrack/<Piece>/instruments/*.py

A composition may set INSTRUMENTS_DIR to a path relative to its piece
directory.  That lets new pieces opt into the shared lib/instruments
library while historical pieces keep their frozen private patches.

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
and CLIMAX_SECTION. A track may also carry an effects list; each entry embeds
one MicroPython Effect script after the instrument and uses the same macros /
macro_env shape as an instrument.
"""

import ast
import importlib.util
import sys
from pathlib import Path

SOUNDTRACK_DIR = Path(__file__).resolve().parent.parent / "soundtrack"


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
    instruments = getattr(module, "INSTRUMENTS_DIR", "instruments")
    instruments = Path(instruments)
    if not instruments.is_absolute():
        instruments = (piece_dir / instruments).resolve()
    return module, instruments


def patch_macros(script_path):
    """Patch 1's macro values for an instrument, as {index: value}.

    Every instrument must declare PATCHES; Patch 1 (Program Change 0) is
    the sound its module-level defaults describe. A macro a composition
    does not set resolves here rather than to 0.5, because 0.5 is the
    middle of a range - not "off", and not what the instrument's author
    intended. Half-open noise, half-open poly-mod and a modulator parked
    on the 6th harmonic all came from resolving to 0.5.

    Read with ast rather than by importing: this runs under plain python3
    during project generation, where synthio and numpy are not available.
    Use tools/derive_patches.py to produce or refresh a PATCHES block.
    """
    path = Path(script_path)
    try:
        tree = ast.parse(path.read_text(), str(path))
    except SyntaxError as exc:
        raise SystemExit("%s: cannot parse: %s" % (path.name, exc))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "PATCHES"
                   for t in node.targets):
            continue
        try:
            patches = ast.literal_eval(node.value)
            name, values = patches[0]
        except Exception:                                  # noqa: BLE001
            raise SystemExit(
                "%s: PATCHES is not a literal {index: (name, values)} map"
                % path.name)
        return {i: float(v) for i, v in enumerate(values)}, name
    raise SystemExit(
        "%s declares no PATCHES.\n"
        "Every instrument must define Patch 1 - it is what an unset macro\n"
        "resolves to, and without it every unset macro falls back to 0.5,\n"
        "which is the middle of a range rather than the intended sound.\n"
        "Generate one with:  tools/derive_patches.py --write %s"
        % (path.name, path.name))


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
