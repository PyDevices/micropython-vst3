"""Shimmer Lab - four ways to make the Perihelion shimmer musical.

A listening fixture, not a piece of music. The Perihelion track called "Air
Shimmer" is band-passed noise with a rising center: a reverse-cymbal, which
is a sound effect that arrives on a downbeat rather than something that sits
in a chord. This exists to audition alternatives side by side.

Every variant plays the *same two chords over the same sixteen bars* -
eight of D minor, then eight of B flat - stacked on four tracks rather than
laid end to end. All four playing at once sounds terrible and is not the
point: it means one loop region covers every take, so switching between
them is a solo button rather than a seek. That is how an A/B actually gets
done at a desk.

  A  Air Swell        what Perihelion had
  B  Tuned Air        the same noise engine, band on the note
  C  Choir Shimmer    VP-330 choir through an octave-up hall
  D  String Shimmer   Solina strings through the same

A and B are the cheap answers: same family, one keeps the piece's identity.
C and D replace the instrument outright and use the real trick - a copy an
octave up fed into a long reverb, which is what "shimmer" names.

The gains here are deliberately NOT Perihelion's. There the shimmer sits 50
to 60 dB down and you have to solo it and turn everything up to hear it at
all; here every variant is loud enough to judge on its own terms, and all
four are level-matched to -35.0 dBFS section RMS so the loudest one
does not win by being loudest. Decide what it should sound like first, then
decide how far back it goes.
"""

TITLE = "Shimmer_Lab"
SAMPLE_RATE = 48000
MASTER_GAIN_DB = -6.0
ACTIVE_LIMIT = 4
CLIMAX_SECTION = "B Flat"
BEATS_PER_BAR = 4
TOTAL_BARS = 16
TAIL_SECONDS = 12.0

# One slow tempo throughout: nothing here is rhythmic, and a swell wants
# room. Sixteen bars at 66 bpm is just under a minute, which loops well.
TEMPO_MAP = [(0.0, 66.0)]

TOTAL_BEATS = float(TOTAL_BARS * BEATS_PER_BAR)


def beats_to_seconds(beat):
    seconds = 0.0
    for index, (start, bpm) in enumerate(TEMPO_MAP):
        end = TEMPO_MAP[index + 1][0] if index + 1 < len(TEMPO_MAP) else None
        if end is None or beat <= end:
            return seconds + max(0.0, beat - start) * 60.0 / bpm
        seconds += (end - start) * 60.0 / bpm
    return seconds


SONG_SECONDS = beats_to_seconds(TOTAL_BEATS)
RENDER_SECONDS = SONG_SECONDS + TAIL_SECONDS


def bar(n, beat=0.0):
    return (n - 1) * BEATS_PER_BAR + beat


Bb2, D3, F3, A3, Bb3, D4, F4, A4, D5 = 46, 50, 53, 57, 58, 62, 65, 69, 74

#: Eight bars of D minor, then eight of B flat. Both voiced so the top note
#: moves by a step and nothing else does - the least interesting harmony
#: that is still harmony, which is what a fair comparison wants.
DM = (D3, F3, A3, D4)
BB = (Bb2, D3, F3, Bb3)


def variant_notes(velocity=0.7):
    """The two chords, each held for most of its eight bars.

    Every variant gets the same call: they overlap in time on purpose, so
    one loop region covers all four and soloing is the only gesture needed
    to compare them.

    Notes stop a bar short of the change so the release and the reverb tail
    have somewhere to go; a swell cut off by the next chord tells you
    nothing about how it decays.
    """
    out = []
    for offset, chord in ((0, DM), (8, BB)):
        start = bar(1 + offset)
        for pitch in chord:
            out.append((start, 7.0 * BEATS_PER_BAR, pitch, velocity))
    return out


# --- Racks -------------------------------------------------------------------

def _read_effect(name):
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
    with open(path) as handle:
        return handle.read()


#: Perihelion's own rack, at Perihelion's own macro values, so variant A is
#: the thing being replaced and not an approximation of it.
FX_SPACE = {
    "name": "Air Space",
    "source": _read_effect("fx_space.py"),
    "macros": {0: 0.3, 1: 0.15, 2: 0.7},
    "macro_env": {},
}

#: The same rack opened up, for the tuned variant: the noise now carries
#: pitch, so there is no reason to keep the low-pass sitting on top of it.
FX_SPACE_OPEN = {
    "name": "Air Space Open",
    "source": _read_effect("fx_space.py"),
    "macros": {0: 0.45, 1: 0.25, 2: 0.92},
    "macro_env": {},
}

#: Shimmer / Echo / Space / Tone.
FX_SHIMMER = {
    "name": "Shimmer Hall",
    "source": _read_effect("fx_shimmer.py"),
    "macros": {0: 0.55, 1: 0.45, 2: 0.6, 3: 0.62},
    "macro_env": {},
}

FX_SHIMMER_WIDE = {
    "name": "Shimmer Hall Wide",
    "source": _read_effect("fx_shimmer.py"),
    "macros": {0: 0.7, 1: 0.55, 2: 0.75, 3: 0.5},
    "macro_env": {},
}


# --- Track table -------------------------------------------------------------

TRACKS = [
    {
        # Exactly Perihelion's settings, only louder and on its own.
        "name": "A Air Swell", "script": "shimmer.py", "gain_db": -9.3,
        "pan": 0.1, "notes": variant_notes(),
        "macros": {0: 0.55, 1: 0.7},
        "vol": [(bar(1), 1.0)],
        "macro_env": {},
        "effects": [FX_SPACE],
    },
    {
        # Same noise engine, band tracking the note, focused enough to sing.
        "name": "B Tuned Air", "script": "tuned_air.py", "gain_db": -8.8,
        "pan": -0.1, "notes": variant_notes(),
        "macros": {0: 0.5, 1: 0.7, 2: 0.72, 3: 0.6},
        "vol": [(bar(1), 1.0)],
        "macro_env": {},
        "effects": [FX_SPACE_OPEN],
    },
    {
        "name": "C Choir Shimmer", "script": "vp330.py", "gain_db": -2.2,
        "pan": 0.05, "notes": variant_notes(velocity=0.8),
        # Volume, male choir, female choir, chorus depth, attack, release,
        # formant, vibrato rate, vibrato depth, brilliance, bass, tune.
        # Bass at zero on purpose. The VP-330's bass layer doubles an
        # octave down, which measured as the loudest thing in the variant -
        # 87 Hz under a chord whose lowest note is 147. A shimmer is the air
        # above a mix, not another thing competing with the bass in it.
        "macros": {0: 0.95, 1: 0.3, 2: 0.85, 3: 0.6, 4: 0.55, 5: 0.7,
                   6: 0.5, 7: 0.35, 8: 0.25, 9: 0.65, 10: 0.0, 11: 0.5},
        "vol": [(bar(1), 1.0)],
        "macro_env": {},
        "effects": [FX_SHIMMER],
    },
    {
        "name": "D String Shimmer", "script": "solina.py", "gain_db": -5.3,
        "pan": -0.05, "notes": variant_notes(velocity=0.6),
        # Volume, violin, viola, cello, chorus depth, attack, release,
        # crescendo, tune.
        "macros": {0: 0.68, 1: 0.7, 2: 0.5, 3: 0.35, 4: 0.75, 5: 0.6,
                   6: 0.7, 7: 0.4, 8: 0.5},
        "vol": [(bar(1), 1.0)],
        "macro_env": {},
        "effects": [FX_SHIMMER_WIDE],
    },
]


def _db(x):
    return 10.0 ** (x / 20.0)


def track_gain(track, beat):
    base = _db(track["gain_db"])
    points = track["vol"]
    if not points:
        return base
    if beat <= points[0][0]:
        return base * points[0][1]
    for i in range(len(points) - 1):
        b0, m0 = points[i]
        b1, m1 = points[i + 1]
        if beat <= b1:
            f = (beat - b0) / (b1 - b0) if b1 > b0 else 1.0
            return base * (m0 + (m1 - m0) * f)
    return base * points[-1][1]


def macro_value(track, index, beat):
    env = track["macro_env"].get(index)
    if not env:
        return track["macros"].get(index, 0.5)
    if beat <= env[0][0]:
        return env[0][1]
    for i in range(len(env) - 1):
        b0, v0 = env[i]
        b1, v1 = env[i + 1]
        if beat <= b1:
            f = (beat - b0) / (b1 - b0) if b1 > b0 else 1.0
            return v0 + (v1 - v0) * f
    return env[-1][1]


def active_track_count(beat):
    count = 0
    for track in TRACKS:
        for start, dur, _pitch, _vel in track["notes"]:
            if start <= beat < start + dur:
                count += 1
                break
    return count


#: The two chords, not the four takes - the takes are tracks now, and the
#: per-track section RMS table is where they get compared.
SECTIONS = [
    ("A D Minor", bar(1), bar(9)),
    ("B Flat", bar(9), bar(17)),
]
