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
import os
import sys
import tempfile
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
SOUNDTRACK_DIR = REPO_DIR / "soundtrack"

#: Where audioinstruments lives. Same workspace-sibling rule the engine
#: build and the plug-in's staging step use; the environment variable is
#: the escape hatch for a checkout somewhere else. MPVST_AUDIOIF_LIB is
#: the name this had while the packages lived in audioif, honoured for
#: one release when the new one is unset - the same alias, and the same
#: warning, as the plug-in's CMake.
_COMPONENTS_LIB_ALIAS = os.environ.get("MPVST_AUDIOIF_LIB")
if "MPVST_COMPONENTS_LIB" not in os.environ and _COMPONENTS_LIB_ALIAS:
    sys.stderr.write(
        "piece.py: MPVST_AUDIOIF_LIB is deprecated (the packages moved to "
        "audiocomponents); using it as MPVST_COMPONENTS_LIB\n")
COMPONENTS_LIB = Path(
    os.environ.get("MPVST_COMPONENTS_LIB")
    or _COMPONENTS_LIB_ALIAS
    or str(REPO_DIR.parent / "audiocomponents" / "lib"))

#: How a generated loader names the instrument module it runs. Anything
#: holding a script path and needing the instrument behind it reads the call
#: rather than guessing from the filename - and reads the call rather than a
#: comment, because mpvst markers live in moduleinfo.json and never in a .py.
MODULE_CALL = 'mpvst_adapter.run("'
_SHARED_INSTRUMENTS = None


def module_of(script_path):
    """The audioinstruments module a generated loader runs, or None.

    None is the answer for a hand-written instrument, which loads nothing and
    is the whole synthesizer itself. Only the head of the file is read: this
    is called for every track of every piece and a private instrument can be
    long.
    """
    with open(str(script_path)) as handle:
        # Generated shims keep marker comments and a short explanatory
        # docstring before the adapter call. Read the whole small header so
        # metadata such as PATCHES is resolved from the library module rather
        # than mistaking a generated loader for a private patch script.
        for _ in range(32):
            line = handle.readline()
            if not line:
                break
            at = line.find(MODULE_CALL)
            if at < 0:
                continue
            rest = line[at + len(MODULE_CALL):]
            end = rest.find('"')
            if end > 0:
                return rest[:end]
    return None


def instrument_source(script_path):
    """The file that actually declares an instrument's PATCHES.

    For a generated shim that is the audioinstruments module it loads; for
    a piece-private instrument it is the script itself.
    """
    name = module_of(script_path)
    if name is None:
        return Path(script_path)
    source = COMPONENTS_LIB.joinpath(*name.split(".")).with_suffix(".py")
    if not source.is_file():
        raise SystemExit(
            "%s loads %s, which is not at %s.\n"
            "Set MPVST_COMPONENTS_LIB, or run scripts/fetch-sibling-repos.sh."
            % (Path(script_path).name, name, source))
    return source


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
    if (not instruments.is_dir()
            or not any(instruments.glob("*.py"))):
        instruments = shared_instruments()
    return module, instruments


def _literal_metadata(path):
    """Read the static metadata needed by a synthesized library loader."""
    tree = ast.parse(path.read_text(), str(path))
    values = {}
    wanted = ("NAME", "DISPLAY_NAME", "MACRO_LABELS", "MACRO_MODES",
              "PATCHES")
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in wanted:
                values[target.id] = ast.literal_eval(node.value)
    return values


def shared_instruments():
    """Materialize loaders for the shared instrument library when requested.

    The plug-in stages audiocomponents' packages directly and discovers them
    from moduleinfo; it does not need a checked-in lib/instruments mirror.
    Project generation and the preview renderer still need a script file to
    embed or exec, so create the same tiny loader in a temporary directory.
    The loader carries the static declarations that a host can read without
    importing synthio, then delegates construction to audioinstruments.
    """
    global _SHARED_INSTRUMENTS
    if _SHARED_INSTRUMENTS is not None:
        return _SHARED_INSTRUMENTS
    package_dir = COMPONENTS_LIB / "audioinstruments"
    if not package_dir.is_dir():
        raise SystemExit(
            "shared instrument directory is missing: %s\n"
            "Set MPVST_COMPONENTS_LIB to audiocomponents' lib/ directory."
            % package_dir)
    output = Path(tempfile.mkdtemp(prefix="mpvst-instruments-"))
    for source in sorted(package_dir.glob("*.py")):
        if source.name.startswith("_") or source.name == "__init__.py":
            continue
        values = _literal_metadata(source)
        if "NAME" not in values:
            continue
        name = values["NAME"]
        lines = [
            "# mpvst-module: audioinstruments.%s" % source.stem,
            "NAME = %r" % name,
        ]
        for field in ("DISPLAY_NAME", "MACRO_LABELS", "MACRO_MODES",
                      "PATCHES"):
            if field in values:
                lines.append("%s = %r" % (field, values[field]))
        lines.extend([
            "",
            "import mpvst_adapter",
            "",
            "mpvst_adapter.run(\"audioinstruments.%s\")" % source.stem,
            "",
        ])
        (output / source.name).write_text("\n".join(lines))
    _SHARED_INSTRUMENTS = output
    return output


def patch_macros(script_path):
    """Patch 0's macro values for an instrument, as {index: value}.

    Every instrument must declare PATCHES; patch 0 (Program Change 0) is
    the sound its module-level defaults describe. A macro a composition
    does not set resolves here rather than to 0.5, because 0.5 is the
    middle of a range - not "off", and not what the instrument's author
    intended. Half-open noise, half-open poly-mod and a modulator parked
    on the 6th harmonic all came from resolving to 0.5.

    Patch values are stored as MIDI integers 0-127 - that is what a
    keyboard, a sequencer and a saved patch all speak - and returned here
    as the normalized floats plug-in state is written in.

    Read with ast rather than by importing: this runs under plain python3
    during project generation, where synthio and numpy are not available.
    A generated shim declares no patches of its own, so the module it
    loads is read instead. Use tools/derive_patches.py to produce or
    refresh a PATCHES block.
    """
    path = instrument_source(script_path)
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
        for value in values:
            if not isinstance(value, int) or not 0 <= value <= 127:
                raise SystemExit(
                    "%s: patch value %r is not a MIDI integer 0-127.\n"
                    "Refresh the block with tools/derive_patches.py --write."
                    % (path.name, value))
        return {i: v / 127.0 for i, v in enumerate(values)}, name
    raise SystemExit(
        "%s declares no PATCHES.\n"
        "Every instrument must define patch 0 - it is what an unset macro\n"
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
    if sys.argv[1:2] == ["--list"]:
        for _name in available_pieces():
            print(_name)
    else:
        raise SystemExit("usage: piece.py --list")
