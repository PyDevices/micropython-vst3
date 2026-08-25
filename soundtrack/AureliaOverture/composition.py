"""Aurelia Overture - a tonal concert overture for the shared library.

One musical language, one four-note idea, one dramatic curve.  The piece is
in D minor and common time throughout: a Grave invocation, a disciplined
sonata Allegro, an F-major cantabile, a four-entry fugato, a recapitulation,
and a measured coda.  Beethoven contributes motivic economy, Vivaldi the
motor rhythm, Bach the contrapuntal development, and Puccini the long-breathed
middle melody; none is quoted.

Every instrument comes directly from lib/instruments.  Every insert below is
only a small room-placement script around processors from lib/effects.
"""

TITLE = "Aurelia_Overture"
SAMPLE_RATE = 48000
MASTER_GAIN_DB = 0.0
ACTIVE_LIMIT = None
CLIMAX_SECTION = "V Recapitulation"
TAIL_SECONDS = 14.0
INSTRUMENTS_DIR = "../../lib/instruments"

# Six sections, all 4/4.  Beats are quarter notes.
M1, M2, M3, M4, M5, M6 = 0.0, 32.0, 224.0, 288.0, 416.0, 544.0
TOTAL_BEATS = 608.0

TEMPO_MAP = [
    (M1, 72.0, 4, 4),       # Grave
    (M2, 138.0, 4, 4),      # Allegro con fuoco
    (M3, 68.0, 4, 4),       # Cantabile
    (M4, 144.0, 4, 4),      # Fugato
    (M5, 138.0, 4, 4),      # Recapitulation
    (M6, 112.0, 4, 4),      # Maestoso
    (576.0, 96.0, 4, 4),
    (592.0, 80.0, 4, 4),
    (600.0, 64.0, 4, 4),
]

SECTIONS = [
    ("I Grave", M1, M2),
    ("II Allegro", M2, M3),
    ("III Cantabile", M3, M4),
    ("IV Fugato", M4, M5),
    ("V Recapitulation", M5, M6),
    ("VI Coda", M6, TOTAL_BEATS),
]


def beats_to_seconds(beat):
    seconds = 0.0
    for index, row in enumerate(TEMPO_MAP):
        start, bpm = row[0], row[1]
        end = TEMPO_MAP[index + 1][0] if index + 1 < len(TEMPO_MAP) else None
        if end is None or beat <= end:
            return seconds + max(0.0, beat - start) * 60.0 / bpm
        seconds += (end - start) * 60.0 / bpm
    return seconds


SONG_SECONDS = beats_to_seconds(TOTAL_BEATS)
RENDER_SECONDS = SONG_SECONDS + TAIL_SECONDS


def gravebar(bar, off=0.0):
    return M1 + (bar - 1) * 4.0 + off


def allegrobar(bar, off=0.0):
    return M2 + (bar - 1) * 4.0 + off


def ariabar(bar, off=0.0):
    return M3 + (bar - 1) * 4.0 + off


def fuguebar(bar, off=0.0):
    return M4 + (bar - 1) * 4.0 + off


def recapbar(bar, off=0.0):
    return M5 + (bar - 1) * 4.0 + off


def codabar(bar, off=0.0):
    return M6 + (bar - 1) * 4.0 + off


_SEMITONES = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
    "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8,
    "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11,
}


def P(name):
    return 12 * (int(name[-1]) + 1) + _SEMITONES[name[:-1]]


def add_chord(out, start, duration, names, velocity, roll=0.0):
    for index, name in enumerate(names):
        delay = index * roll
        out.append((start + delay, max(0.05, duration - delay), P(name),
                    max(0.05, velocity - index * 0.01)))


# Plain classical triads and inversions.  There are no extended/jazz chords.
CHORDS = {
    "Dm": ("D3", "A3", "D4", "F4"),
    "D":  ("D3", "A3", "D4", "F#4"),
    "F":  ("F3", "C4", "F4", "A4"),
    "Gm": ("G3", "D4", "G4", "Bb4"),
    "G":  ("G3", "D4", "G4", "B4"),
    "A":  ("A2", "E3", "A3", "C#4"),
    "Am": ("A2", "E3", "A3", "C4"),
    "Bb": ("Bb2", "F3", "Bb3", "D4"),
    "C":  ("C3", "G3", "C4", "E4"),
    "Edim": ("E3", "Bb3", "E4", "G4"),
    "Em": ("E3", "B3", "E4", "G4"),
    "Bm": ("B2", "F#3", "B3", "D4"),
    "F#m": ("F#3", "C#4", "F#4", "A4"),
}

ROOTS = {
    "Dm": "D2", "D": "D2", "F": "F2", "Gm": "G1", "G": "G1",
    "A": "A1", "Am": "A1", "Bb": "Bb1", "C": "C2",
    "Edim": "E2", "Em": "E2", "Bm": "B1", "F#m": "F#1",
}

ALLEGRO_HARMONY = (
    "Dm", "Bb", "Gm", "A", "Dm", "C", "Bb", "A",
    "Dm", "Bb", "Gm", "A", "Dm", "C", "Bb", "A",
    "Gm", "Dm", "A", "Dm", "Bb", "Gm", "Edim", "A",
    "F", "C", "Dm", "Am", "Bb", "F", "Gm", "C",
    "F", "C", "Bb", "A", "Dm", "Gm", "Edim", "A",
    "Dm", "C", "Bb", "A", "Gm", "Dm", "A", "A",
)

ARIA_HARMONY = (
    "F", "C", "Dm", "Am", "Bb", "F", "Gm", "C",
    "F", "C", "Dm", "A", "Bb", "Gm", "A", "Dm",
)

FUGUE_HARMONY = (
    "Dm", "A", "Dm", "A", "Am", "E", "Am", "A",
    "F", "C", "F", "A", "Dm", "Gm", "A", "A",
    "Dm", "A", "Gm", "Dm", "Bb", "Gm", "Edim", "A",
    "Dm", "C", "Bb", "A", "Gm", "Dm", "A", "A",
)

# E major is needed only as the dominant of the A-minor answer in the fugue.
CHORDS["E"] = ("E3", "B3", "E4", "G#4")
ROOTS["E"] = "E2"

RECAP_HARMONY = (
    "Dm", "Bb", "Gm", "A", "Dm", "C", "Bb", "A",
    "Dm", "Bb", "Gm", "A", "Dm", "C", "Bb", "A",
    "D", "A", "Bm", "F#m", "G", "D", "Em", "A",
    "D", "G", "D", "A", "Bm", "G", "A", "D",
)

CODA_HARMONY = (
    "Dm", "Bb", "Gm", "A", "Dm", "C", "Bb", "A",
    "Dm", "Gm", "A", "Dm", "Bb", "A", "D", "D",
)


# Shared-effect room placements ---------------------------------------------

def room_rack(name, preset, mix, extra=""):
    room_source = "width.output" if extra else "source"
    source = ("# mpvst-macro-labels: Room 01 | Room 02 | Room 03 | Room 04\n"
              "import vstaudio\n"
              "from effects import Reverb%s\n"
              "source = vstaudio.input()\n%s"
              "room = Reverb(%s, preset='%s', mix=%.3f)\n"
              "vstaudio.output(room.output)\n" %
              (", Chorus" if extra else "", extra, room_source, preset, mix))
    return {"name": name, "source": source, "macros": {}, "macro_env": {}}


FX_PERCUSSION = room_rack("Rear Hall", "hall", 0.24)
FX_BASS = room_rack("Bass Room", "room", 0.08)
FX_PIZZ = room_rack("Pizzicato Chamber", "chamber", 0.14)
FX_STRINGS = room_rack("String Hall", "hall", 0.22,
                       "width = Chorus(source, rate=0.23, depth_ms=2.4, voices=2, mix=0.10)\n")
FX_ORCHESTRA = room_rack("Orchestra Hall", "hall", 0.18)
FX_VIOLIN = room_rack("Soloist Hall", "hall", 0.20)
FX_FLUTE = room_rack("Woodwind Chamber", "chamber", 0.20)
FX_HORNS = room_rack("Horn Hall", "hall", 0.16)
FX_ORGAN = room_rack("Nave", "hall", 0.28)
FX_PIANO = room_rack("Piano Chamber", "chamber", 0.13)
FX_CHOIR = room_rack("Choir Nave", "hall", 0.26)


# Principal material ---------------------------------------------------------

# Eight-bar principal theme. The first four pitches (D-A-Bb-A) generate the
# bass figures, horn calls, fugue subject, and the aria's inverted answer.
PRINCIPAL_THEME = (
    (0, 0.0, 0.45, "D5"), (0, 0.5, 0.45, "A4"),
    (0, 1.0, 0.90, "Bb4"), (0, 2.0, 1.75, "A4"),
    (1, 0.0, 0.45, "F5"), (1, 0.5, 0.45, "C5"),
    (1, 1.0, 0.90, "D5"), (1, 2.0, 1.75, "C#5"),
    (2, 0.0, 0.45, "G5"), (2, 0.5, 0.45, "D5"),
    (2, 1.0, 0.90, "E5"), (2, 2.0, 0.85, "D5"),
    (2, 3.0, 0.72, "C#5"), (3, 0.0, 3.70, "D5"),
    (4, 0.0, 0.45, "A5"), (4, 0.5, 0.45, "E5"),
    (4, 1.0, 0.90, "F5"), (4, 2.0, 0.85, "E5"),
    (4, 3.0, 0.72, "D5"),
    (5, 0.0, 0.45, "Bb5"), (5, 0.5, 0.45, "F5"),
    (5, 1.0, 0.90, "G5"), (5, 2.0, 0.85, "F5"),
    (5, 3.0, 0.72, "E5"),
    (6, 0.0, 0.90, "D5"), (6, 1.0, 0.90, "F5"),
    (6, 2.0, 0.90, "A5"), (6, 3.0, 0.72, "C#6"),
    (7, 0.0, 3.70, "D6"),
)


SECOND_THEME = (
    (0, 0.0, 0.90, "A4"), (0, 1.0, 0.90, "C5"),
    (0, 2.0, 1.75, "F5"),
    (1, 0.0, 1.35, "E5"), (1, 1.5, 0.45, "D5"),
    (1, 2.0, 1.75, "C5"),
    (2, 0.0, 0.90, "D5"), (2, 1.0, 0.90, "F5"),
    (2, 2.0, 1.75, "A5"),
    (3, 0.0, 1.35, "G5"), (3, 1.5, 0.45, "F5"),
    (3, 2.0, 1.75, "E5"),
    (4, 0.0, 1.75, "D5"), (4, 2.0, 0.90, "C5"),
    (4, 3.0, 0.72, "Bb4"),
    (5, 0.0, 0.90, "A4"), (5, 1.0, 0.90, "C5"),
    (5, 2.0, 1.75, "F5"),
    (6, 0.0, 0.90, "G5"), (6, 1.0, 0.90, "F5"),
    (6, 2.0, 0.90, "D5"), (6, 3.0, 0.72, "B4"),
    (7, 0.0, 3.70, "C5"),
)


ARIA_MELODY = (
    (0, 0.0, 2.75, "C5"), (0, 3.0, 0.75, "A4"),
    (1, 0.0, 1.75, "G4"), (1, 2.0, 1.75, "E5"),
    (2, 0.0, 1.25, "F5"), (2, 1.5, 0.45, "E5"),
    (2, 2.0, 1.75, "D5"), (3, 0.0, 3.70, "C5"),
    (4, 0.0, 1.75, "D5"), (4, 2.0, 0.90, "F5"),
    (4, 3.0, 0.75, "A5"), (5, 0.0, 2.75, "G5"),
    (5, 3.0, 0.75, "F5"), (6, 0.0, 1.75, "E5"),
    (6, 2.0, 1.75, "D5"), (7, 0.0, 3.70, "C5"),
    (8, 0.0, 1.25, "A5"), (8, 1.5, 0.45, "G5"),
    (8, 2.0, 1.75, "F5"), (9, 0.0, 2.75, "E5"),
    (9, 3.0, 0.75, "C5"), (10, 0.0, 1.75, "D5"),
    (10, 2.0, 0.90, "F5"), (10, 3.0, 0.75, "E5"),
    (11, 0.0, 3.70, "C#5"),
    (12, 0.0, 1.75, "D5"), (12, 2.0, 1.75, "F5"),
    (13, 0.0, 2.75, "Bb5"), (13, 3.0, 0.75, "A5"),
    (14, 0.0, 0.90, "G5"), (14, 1.0, 0.90, "F5"),
    (14, 2.0, 0.90, "E5"), (14, 3.0, 0.75, "C#5"),
    (15, 0.0, 3.75, "D5"),
)


FUGUE_SUBJECT = (
    (0, 0.0, 0.45, 0), (0, 0.5, 0.45, 7),
    (0, 1.0, 0.90, 8), (0, 2.0, 1.75, 7),
    (1, 0.0, 0.45, 3), (1, 0.5, 0.45, 10),
    (1, 1.0, 0.90, 12), (1, 2.0, 1.75, 11),
    (2, 0.0, 0.45, 0), (2, 0.5, 0.45, 2),
    (2, 1.0, 0.45, 3), (2, 1.5, 0.45, 5),
    (2, 2.0, 0.90, 7), (2, 3.0, 0.75, 5),
    (3, 0.0, 0.90, 3), (3, 1.0, 0.90, 2),
    (3, 2.0, 1.75, 0),
)


def theme_at(bar_function, start_bar, velocity, transpose=0):
    return [(bar_function(start_bar + bar, off), duration,
             P(name) + transpose, velocity)
            for bar, off, duration, name in PRINCIPAL_THEME]


def second_theme_at(bar_function, start_bar, velocity, transpose=0):
    return [(bar_function(start_bar + bar, off), duration,
             P(name) + transpose, velocity)
            for bar, off, duration, name in SECOND_THEME]


def fugue_subject_at(bar_function, start_bar, root, velocity):
    return [(bar_function(start_bar + bar, off), duration, root + interval,
             velocity) for bar, off, duration, interval in FUGUE_SUBJECT]


# Percussion -----------------------------------------------------------------

KICK, TOM_L, TOM_M, TOM_H, CYMBAL = 36, 43, 47, 50, 49


def percussion_notes():
    out = []
    for bar in (1, 3, 5, 7):
        out.append((gravebar(bar), 0.35, KICK, 0.45 + 0.04 * bar))
    for off, pitch, vel in ((0.0, TOM_L, 0.45), (0.5, TOM_L, 0.5),
                            (1.0, TOM_M, 0.58), (1.5, TOM_M, 0.64),
                            (2.0, TOM_H, 0.72), (2.5, TOM_H, 0.8),
                            (3.0, KICK, 0.86), (3.0, CYMBAL, 0.7)):
        out.append((gravebar(8, off), 0.2, pitch, vel))

    # Structural punctuation only: never a drum-machine groove.
    for bar in range(1, 49):
        if bar in (1, 9, 17, 25, 33, 41):
            out.append((allegrobar(bar), 0.28, KICK, 0.72))
            out.append((allegrobar(bar), 0.35, CYMBAL, 0.42))
        if bar % 8 == 4:
            out.append((allegrobar(bar, 2.0), 0.22, TOM_L, 0.45))
            out.append((allegrobar(bar, 3.0), 0.22, TOM_M, 0.5))
        if bar in (8, 16, 24, 32, 40, 48):
            for index, pitch in enumerate((TOM_L, TOM_M, TOM_H, KICK)):
                out.append((allegrobar(bar, 3.0 + index * 0.25),
                            0.16, pitch, 0.52 + index * 0.08))

    for bar in range(13, 17):
        for eighth in range(8):
            out.append((ariabar(bar, eighth * 0.5), 0.16,
                        TOM_L if eighth < 4 else TOM_M,
                        0.24 + 0.035 * ((bar - 13) * 8 + eighth)))
    out.append((ariabar(16, 3.5), 0.3, CYMBAL, 0.5))

    for bar in (1, 5, 9, 13, 17, 21, 25, 29):
        out.append((fuguebar(bar), 0.24, KICK, 0.5 + 0.012 * bar))
    for bar in (16, 24, 32):
        for index, pitch in enumerate((TOM_L, TOM_M, TOM_H, KICK)):
            out.append((fuguebar(bar, 3.0 + index * 0.25), 0.15,
                        pitch, 0.55 + index * 0.07))

    for bar in range(1, 33):
        if bar in (1, 9, 17, 25):
            out.append((recapbar(bar), 0.3, KICK, 0.82))
            out.append((recapbar(bar), 0.35, CYMBAL, 0.58))
        if bar % 4 == 0:
            out.append((recapbar(bar, 2.0), 0.2, TOM_L, 0.55))
            out.append((recapbar(bar, 3.0), 0.2, TOM_M, 0.62))
        if bar in (8, 16, 24, 32):
            out.append((recapbar(bar, 3.5), 0.2, TOM_H, 0.72))
            out.append((recapbar(bar, 3.75), 0.2, KICK, 0.82))
    out.append((recapbar(32, 3.75), 0.35, CYMBAL, 0.8))

    for bar in (1, 5, 9, 13, 15, 16):
        out.append((codabar(bar), 0.32, KICK, 0.58 + 0.02 * bar))
    for off, pitch, vel in ((0.0, TOM_L, 0.62), (0.5, TOM_M, 0.7),
                            (1.0, TOM_H, 0.78), (2.0, KICK, 0.9),
                            (2.0, CYMBAL, 0.9)):
        out.append((codabar(16, off), 0.28, pitch, vel))
    return out


# Bass and inner motion ------------------------------------------------------

def bass_notes():
    out = []
    grave_roots = ("D1", "A1", "Bb1", "A1", "D1", "G1", "A1", "D1")
    for bar, root in enumerate(grave_roots, 1):
        out.append((gravebar(bar), 3.82, P(root), 0.46 + 0.025 * bar))

    for bar, harmony in enumerate(ALLEGRO_HARMONY, 1):
        root = P(ROOTS[harmony])
        pattern = (0, 7, 12, 7, 0, 7, 12, 7)
        if bar % 4 == 0:
            pattern = (0, 7, 0, 7, 12, 11, 9, 7)
        for eighth, interval in enumerate(pattern):
            out.append((allegrobar(bar, eighth * 0.5), 0.39,
                        root + interval, 0.5 + (0.08 if eighth == 0 else 0.0)))

    for bar, harmony in enumerate(ARIA_HARMONY, 1):
        root = P(ROOTS[harmony])
        out.append((ariabar(bar), 2.85, root, 0.38))
        out.append((ariabar(bar, 3.0), 0.72, root + 7, 0.3))

    for bar, harmony in enumerate(FUGUE_HARMONY, 1):
        root = P(ROOTS[harmony])
        for beat, interval in ((0.0, 0), (1.0, 7), (2.0, 12), (3.0, 7)):
            out.append((fuguebar(bar, beat), 0.78, root + interval,
                        0.48 + (0.07 if beat == 0 else 0.0)))

    for bar, harmony in enumerate(RECAP_HARMONY, 1):
        root = P(ROOTS[harmony])
        pattern = (0, 7, 12, 7, 0, 7, 12, 7)
        for eighth, interval in enumerate(pattern):
            out.append((recapbar(bar, eighth * 0.5), 0.39,
                        root + interval, 0.56 + (0.08 if eighth == 0 else 0.0)))

    for bar, harmony in enumerate(CODA_HARMONY[:-1], 1):
        root = P(ROOTS[harmony])
        out.append((codabar(bar), 3.82, root, 0.45 + 0.018 * bar))
    out.append((codabar(16), 10.0, P("D1"), 0.68))
    return out


def pizzicato_notes():
    out = []

    def arpeggiate(bar_function, bar, harmony, velocity, sixteenths=True):
        names = CHORDS[harmony]
        pitches = [P(name) + 12 for name in names]
        pattern = (0, 1, 2, 3, 2, 1, 0, 1, 2, 3, 2, 1, 0, 2, 1, 3)
        step = 0.25 if sixteenths else 0.5
        count = 16 if sixteenths else 8
        duration = 0.17 if sixteenths else 0.34
        for index in range(count):
            out.append((bar_function(bar, index * step), duration,
                        pitches[pattern[index]],
                        velocity + (0.06 if index in (0, 8) else 0.0)))

    for bar, harmony in enumerate(ALLEGRO_HARMONY, 1):
        arpeggiate(allegrobar, bar, harmony, 0.34 + 0.002 * bar)
    for bar, harmony in enumerate(ARIA_HARMONY, 1):
        arpeggiate(ariabar, bar, harmony, 0.26, sixteenths=False)

    # Subject/answer entries create actual independent fugue voices.
    out += fugue_subject_at(fuguebar, 5, P("A3"), 0.49)
    for bar, harmony in enumerate(FUGUE_HARMONY, 1):
        if 5 <= bar <= 8:
            continue
        arpeggiate(fuguebar, bar, harmony, 0.32 + 0.003 * bar)
    for bar, harmony in enumerate(RECAP_HARMONY, 1):
        arpeggiate(recapbar, bar, harmony, 0.38 + 0.002 * bar)
    for bar, harmony in enumerate(CODA_HARMONY[:12], 1):
        arpeggiate(codabar, bar, harmony, 0.26, sixteenths=False)
    return out


# Harmonic ensemble ----------------------------------------------------------

def strings_notes():
    out = []
    grave = ("Dm", "A", "Bb", "A", "Dm", "Gm", "A", "Dm")
    for bar, harmony in enumerate(grave, 1):
        add_chord(out, gravebar(bar), 3.82, CHORDS[harmony],
                  0.28 + 0.02 * bar, roll=0.025)
    for bar, harmony in enumerate(ALLEGRO_HARMONY, 1):
        add_chord(out, allegrobar(bar), 3.82, CHORDS[harmony],
                  0.31 + 0.0018 * bar)
    for bar, harmony in enumerate(ARIA_HARMONY, 1):
        add_chord(out, ariabar(bar), 3.86, CHORDS[harmony],
                  0.38 + 0.006 * bar, roll=0.03)
    for bar, harmony in enumerate(FUGUE_HARMONY, 1):
        add_chord(out, fuguebar(bar), 3.82, CHORDS[harmony],
                  0.27 + 0.003 * bar)
    for bar, harmony in enumerate(RECAP_HARMONY, 1):
        add_chord(out, recapbar(bar), 3.84, CHORDS[harmony],
                  0.36 + 0.004 * bar)
    for bar, harmony in enumerate(CODA_HARMONY[:-1], 1):
        add_chord(out, codabar(bar), 3.84, CHORDS[harmony],
                  0.36 + 0.006 * min(bar, 12), roll=0.02)
    add_chord(out, codabar(16), 10.0, ("D2", "A2", "D3", "F#3", "A3"), 0.68)
    return out


def orchestra_notes():
    out = []
    # Broad lower body enters only at pillars; it does not duplicate every bar.
    for bar, harmony in ((1, "Dm"), (3, "Bb"), (5, "Dm"), (7, "A")):
        add_chord(out, gravebar(bar), 7.75, CHORDS[harmony], 0.3, roll=0.02)
    for start in range(1, 49, 4):
        harmony = ALLEGRO_HARMONY[start - 1]
        add_chord(out, allegrobar(start), 15.75, CHORDS[harmony],
                  0.28 + 0.004 * start)
    for start in range(1, 17, 2):
        harmony = ARIA_HARMONY[start - 1]
        add_chord(out, ariabar(start), 7.78, CHORDS[harmony], 0.34)
    for start in range(1, 33, 4):
        harmony = FUGUE_HARMONY[start - 1]
        add_chord(out, fuguebar(start), 15.75, CHORDS[harmony],
                  0.27 + 0.01 * (start // 4))
    for start in range(1, 33, 4):
        harmony = RECAP_HARMONY[start - 1]
        add_chord(out, recapbar(start), 15.78, CHORDS[harmony],
                  0.37 + 0.012 * (start // 4))
    for start in (1, 5, 9, 13):
        harmony = CODA_HARMONY[start - 1]
        duration = 11.75 if start == 13 else 15.75
        add_chord(out, codabar(start), duration, CHORDS[harmony], 0.36)
    add_chord(out, codabar(16), 10.0, ("D2", "A2", "D3", "F#3"), 0.62)
    return out


def piano_notes():
    out = []
    # Grave tolling chords.
    for bar, harmony in enumerate(("Dm", "A", "Bb", "A", "Dm", "Gm", "A", "Dm"), 1):
        names = CHORDS[harmony]
        add_chord(out, gravebar(bar), 1.45, names[1:], 0.32, roll=0.06)
        add_chord(out, gravebar(bar, 2.0), 1.45, names[1:], 0.27)

    for bar, harmony in enumerate(ALLEGRO_HARMONY, 1):
        names = CHORDS[harmony]
        add_chord(out, allegrobar(bar), 0.72, names[1:], 0.36)
        add_chord(out, allegrobar(bar, 2.0), 0.72, names[1:], 0.3)
        if bar % 4 == 0:
            add_chord(out, allegrobar(bar, 3.0), 0.65, names[1:], 0.34)

    # Cantabile accompaniment: transparent broken triads in eighths.
    for bar, harmony in enumerate(ARIA_HARMONY, 1):
        pitches = [P(name) + 12 for name in CHORDS[harmony]]
        pattern = (0, 1, 2, 3, 2, 1, 2, 3)
        for eighth, index in enumerate(pattern):
            out.append((ariabar(bar, eighth * 0.5), 0.36, pitches[index],
                        0.25 + (0.04 if eighth == 0 else 0.0)))

    for bar, harmony in enumerate(FUGUE_HARMONY, 1):
        names = CHORDS[harmony]
        add_chord(out, fuguebar(bar), 0.62, names[1:], 0.3)
        add_chord(out, fuguebar(bar, 2.0), 0.62, names[1:], 0.27)
    for bar, harmony in enumerate(RECAP_HARMONY, 1):
        names = CHORDS[harmony]
        add_chord(out, recapbar(bar), 0.72, names[1:], 0.4)
        add_chord(out, recapbar(bar, 2.0), 0.72, names[1:], 0.34)
    for bar, harmony in enumerate(CODA_HARMONY[:-1], 1):
        names = CHORDS[harmony]
        add_chord(out, codabar(bar), 1.35, names[1:], 0.3 + 0.01 * bar,
                  roll=0.04)
        if bar <= 12:
            add_chord(out, codabar(bar, 2.0), 1.3, names[1:], 0.26)
    add_chord(out, codabar(16), 9.5, ("D3", "A3", "D4", "F#4", "A4"), 0.62,
              roll=0.03)
    return out


# Melodic voices -------------------------------------------------------------

def violin_notes():
    out = []
    # The idea is revealed one fragment at a time in the Grave.
    out += [(gravebar(2), 0.7, P("D5"), 0.38),
            (gravebar(2, 1.0), 0.7, P("A4"), 0.36),
            (gravebar(2, 2.0), 1.7, P("Bb4"), 0.4),
            (gravebar(4), 0.7, P("F5"), 0.42),
            (gravebar(4, 1.0), 0.7, P("C5"), 0.4),
            (gravebar(4, 2.0), 1.7, P("C#5"), 0.44),
            (gravebar(6), 3.7, P("A5"), 0.48),
            (gravebar(8), 3.7, P("D6"), 0.58)]

    out += theme_at(allegrobar, 1, 0.58)
    out += theme_at(allegrobar, 9, 0.63)
    # Sequential transition, always derived from D-A-Bb-A.
    sequence = (("G5", "D5", "Eb5", "D5"),
                ("F5", "C5", "D5", "C5"),
                ("E5", "B4", "C5", "B4"),
                ("D5", "A4", "Bb4", "A4"))
    for bar in range(17, 25):
        notes = sequence[(bar - 17) % 4]
        for beat, name in enumerate(notes):
            out.append((allegrobar(bar, beat), 0.78, P(name),
                        0.55 + 0.015 * (bar - 17)))
    out += second_theme_at(allegrobar, 25, 0.56)
    out += second_theme_at(allegrobar, 33, 0.61)
    out += theme_at(allegrobar, 41, 0.68, -12)

    out += [(ariabar(1 + bar, off), duration, P(name), 0.62)
            for bar, off, duration, name in ARIA_MELODY]

    # Fourth fugue entry, above the three established voices.
    out += fugue_subject_at(fuguebar, 13, P("D5"), 0.58)
    for bar in range(17, 33):
        scale = ("D5", "E5", "F5", "G5", "A5", "Bb5", "C#6", "D6")
        degrees = (0, 2, 4, 3, 5, 4, 6, 7)
        for eighth, degree in enumerate(degrees):
            out.append((fuguebar(bar, eighth * 0.5), 0.36,
                        P(scale[(degree + bar) % 8]),
                        0.42 + 0.01 * (bar - 17)))

    out += theme_at(recapbar, 1, 0.7)
    out += theme_at(recapbar, 9, 0.76)
    # The secondary idea returns in D major (down a minor third from F).
    out += second_theme_at(recapbar, 17, 0.68, -3)
    out += second_theme_at(recapbar, 25, 0.74, -3)

    # Coda recalls both themes, then holds the major third over the final D.
    out += theme_at(codabar, 1, 0.56, -12)
    for bar, name in enumerate(("D5", "F5", "E5", "D5"), 9):
        out.append((codabar(bar), 3.7, P(name), 0.43))
    out += [(codabar(13), 1.75, P("Bb4"), 0.48),
            (codabar(13, 2.0), 1.75, P("A4"), 0.5),
            (codabar(14), 3.7, P("C#5"), 0.54),
            (codabar(15), 3.7, P("D5"), 0.6),
            (codabar(16), 9.5, P("F#5"), 0.68)]
    return out


def flute_notes():
    out = []
    out += [(gravebar(3, 1.0), 1.5, P("F5"), 0.3),
            (gravebar(5, 1.0), 1.5, P("G5"), 0.32),
            (gravebar(7, 1.0), 1.5, P("C#6"), 0.36)]
    # Contrary-motion answers leave the principal theme unobscured.
    for start in (1, 9):
        answers = ((1, 2.0, 1.5, "F5"), (3, 2.0, 1.5, "A5"),
                   (5, 2.0, 1.5, "D6"), (7, 2.0, 1.5, "A5"))
        for bar, off, dur, name in answers:
            out.append((allegrobar(start + bar, off), dur, P(name), 0.36))
    out += second_theme_at(allegrobar, 25, 0.42, 12)
    out += second_theme_at(allegrobar, 33, 0.45, 12)

    # Aria answers occupy the breaths in the violin line.
    aria_answers = ((2, 3.0, 0.75, "A5"), (3, 2.0, 1.5, "G5"),
                    (6, 3.0, 0.75, "F5"), (7, 2.0, 1.5, "E5"),
                    (10, 3.0, 0.75, "A5"), (11, 2.0, 1.5, "G5"),
                    (14, 3.0, 0.75, "E5"), (15, 2.0, 1.5, "D5"))
    for bar, off, dur, name in aria_answers:
        out.append((ariabar(bar, off), dur, P(name), 0.4))

    out += fugue_subject_at(fuguebar, 9, P("F4"), 0.47)
    for bar in range(17, 33, 2):
        out.append((fuguebar(bar), 1.7, P("A5" if bar % 4 == 1 else "G5"), 0.38))
        out.append((fuguebar(bar, 2.0), 1.7,
                    P("F5" if bar % 4 == 1 else "E5"), 0.36))

    for start in (1, 9):
        for bar, off, dur, name in ((1, 2.0, 1.5, "F5"),
                                    (3, 2.0, 1.5, "A5"),
                                    (5, 2.0, 1.5, "D6"),
                                    (7, 2.0, 1.5, "A5")):
            out.append((recapbar(start + bar, off), dur, P(name), 0.46))
    out += second_theme_at(recapbar, 17, 0.48, 9)
    out += [(codabar(9), 2.7, P("A5"), 0.34),
            (codabar(10), 2.7, P("G5"), 0.32),
            (codabar(11), 2.7, P("F5"), 0.3),
            (codabar(12), 2.7, P("E5"), 0.28),
            (codabar(16), 9.0, P("D6"), 0.48)]
    return out


def horn_notes():
    out = []
    # The fate rhythm is stated as triadic horn calls.
    for bar, harmony, vel in ((1, "Dm", 0.38), (3, "Bb", 0.42),
                              (5, "Gm", 0.46), (7, "A", 0.54)):
        names = CHORDS[harmony]
        add_chord(out, gravebar(bar), 0.7, names[1:], vel)
        add_chord(out, gravebar(bar, 1.0), 0.7, names[1:], vel - 0.04)
        add_chord(out, gravebar(bar, 2.0), 1.7, names[1:], vel + 0.03)
    for bar, harmony in enumerate(ALLEGRO_HARMONY, 1):
        if bar <= 8 or 25 <= bar <= 32:
            continue
        names = CHORDS[harmony]
        if bar % 2 == 1:
            add_chord(out, allegrobar(bar), 0.72, names[1:], 0.42)
        if bar % 4 == 0:
            add_chord(out, allegrobar(bar, 3.0), 0.72, names[1:], 0.48)
    for bar in (8, 12, 16):
        harmony = ARIA_HARMONY[bar - 1]
        add_chord(out, ariabar(bar), 3.75, CHORDS[harmony][1:], 0.3 + 0.02 * bar)
    for bar, harmony in enumerate(FUGUE_HARMONY, 1):
        if bar >= 17 and bar % 2 == 1:
            add_chord(out, fuguebar(bar), 0.7, CHORDS[harmony][1:],
                      0.4 + 0.008 * bar)
    for bar, harmony in enumerate(RECAP_HARMONY, 1):
        names = CHORDS[harmony]
        if bar % 2 == 1 or bar >= 25:
            add_chord(out, recapbar(bar), 0.74, names[1:],
                      0.5 + 0.008 * bar)
        if bar % 4 == 0:
            add_chord(out, recapbar(bar, 3.0), 0.72, names[1:], 0.58)
    for bar, harmony in enumerate(CODA_HARMONY[:-1], 1):
        if bar <= 8 or bar >= 13:
            add_chord(out, codabar(bar), 1.6, CHORDS[harmony][1:],
                      0.42 + 0.012 * bar)
    add_chord(out, codabar(16), 9.5, ("D3", "A3", "D4", "F#4"), 0.72)
    return out


def organ_notes():
    out = []
    grave = ("Dm", "A", "Bb", "A", "Dm", "Gm", "A", "Dm")
    for bar, harmony in enumerate(grave, 1):
        add_chord(out, gravebar(bar), 3.86, CHORDS[harmony],
                  0.3 + 0.025 * bar)
    # First fugue entry and a transparent harmonic floor beneath later entries.
    out += fugue_subject_at(fuguebar, 1, P("D3"), 0.5)
    for bar, harmony in enumerate(FUGUE_HARMONY, 1):
        if bar <= 4:
            continue
        if bar % 2 == 1:
            add_chord(out, fuguebar(bar), 7.78, CHORDS[harmony],
                      0.24 + 0.004 * bar)
    for bar in range(25, 33):
        harmony = RECAP_HARMONY[bar - 1]
        add_chord(out, recapbar(bar), 3.82, CHORDS[harmony],
                  0.28 + 0.018 * (bar - 25))
    for bar, harmony in enumerate(CODA_HARMONY[:-1], 1):
        add_chord(out, codabar(bar), 3.86, CHORDS[harmony],
                  0.32 + 0.012 * bar)
    add_chord(out, codabar(16), 10.0, ("D2", "A2", "D3", "F#3", "A3"), 0.68)
    return out


def choir_notes():
    out = []
    # Human color is withheld until the tonal turn to D major.
    for bar in range(17, 33):
        harmony = RECAP_HARMONY[bar - 1]
        add_chord(out, recapbar(bar), 3.84, CHORDS[harmony],
                  0.25 + 0.018 * (bar - 17), roll=0.018)
    for bar in range(1, 9):
        harmony = CODA_HARMONY[bar - 1]
        add_chord(out, codabar(bar), 3.86, CHORDS[harmony],
                  0.32 + 0.015 * bar)
    for bar in range(13, 16):
        harmony = CODA_HARMONY[bar - 1]
        add_chord(out, codabar(bar), 3.88, CHORDS[harmony],
                  0.4 + 0.045 * (bar - 13))
    add_chord(out, codabar(16), 10.0, ("D3", "A3", "D4", "F#4"), 0.68)
    return out


# Track table ----------------------------------------------------------------

TRACKS = [
    {"name": "Timpani and Cymbal", "script": "simmons_sdsv.py", "gain_db": -4.0,
     "pan": 0.0, "notes": percussion_notes(),
     "macros": {0: 0.6, 1: 0.28, 2: 0.25, 3: 0.18, 4: 0.66,
                5: 0.32, 6: 0.14, 7: 0.58, 8: 0.28, 9: 0.38,
                10: 0.5, 11: 0.12, 12: 0.72, 13: 0.38, 14: 0.2,
                15: 0.72},
     "vol": [(M1, 0.7), (M2, 0.86), (M3, 0.5), (M4, 0.78),
             (M5, 1.0), (M6, 0.9)],
     "macro_env": {0: [(M1, 0.48), (gravebar(8), 0.65), (M2, 0.58),
                       (M3, 0.4), (ariabar(13), 0.62), (M4, 0.55),
                       (M5, 0.7), (M6, 0.62), (codabar(16), 0.82)],
                   4: [(M1, 0.72), (M2, 0.5), (M5, 0.76)],
                   12: [(M1, 0.62), (M4, 0.55), (M5, 0.78)]},
     "effects": [FX_PERCUSSION]},
    {"name": "Contrabasses", "script": "taurus.py", "gain_db": -7.0,
     "pan": 0.0, "notes": bass_notes(),
     "macros": {0: 0.48, 1: 0.08, 2: 0.0, 3: 0.4, 4: 0.2,
                5: 0.34, 6: 0.08, 7: 0.08, 8: 0.32, 9: 0.52,
                10: 0.18},
     "vol": [(M1, 0.78), (M2, 0.9), (M3, 0.66), (M4, 0.82),
             (M5, 1.0), (M6, 0.82)],
     "macro_env": {3: [(M1, 0.28), (M2, 0.46), (M3, 0.3),
                       (M4, 0.42), (M5, 0.52), (M6, 0.34)],
                   5: [(M1, 0.22), (M2, 0.42), (M3, 0.25),
                       (M5, 0.48)],
                   9: [(M1, 0.72), (M2, 0.42), (M3, 0.78),
                       (M4, 0.5), (M6, 0.7)]},
     "effects": [FX_BASS]},
    {"name": "Pizzicato Strings", "script": "karplus.py", "gain_db": 1.0,
     "pan": -0.12, "notes": pizzicato_notes(),
     "macros": {0: 0.5, 1: 0.46, 2: 0.58, 3: 0.48, 4: 0.46,
                5: 0.26},
     "vol": [(M2, 0.78), (M3, 0.56), (M4, 1.6), (M5, 0.96),
             (M6, 0.48)],
     "macro_env": {1: [(M2, 0.5), (M3, 0.72), (M4, 0.42),
                       (M5, 0.48), (M6, 0.7)],
                   2: [(M2, 0.52), (M3, 0.72), (M4, 0.58),
                       (M5, 0.62)],
                   4: [(M2, 0.52), (M3, 0.32), (M4, 0.48),
                       (M5, 0.56)]},
     "effects": [FX_PIZZ]},
    {"name": "String Orchestra", "script": "solina.py", "gain_db": 2.0,
     "pan": -0.08, "notes": strings_notes(),
     "macros": {0: 0.46, 1: 0.62, 2: 0.55, 3: 0.48, 4: 0.42,
                5: 0.18, 6: 0.52, 7: 0.32},
     "vol": [(M1, 0.62), (M2, 0.84), (M3, 1.0), (M4, 0.72),
             (M5, 1.08), (M6, 0.86)],
     "macro_env": {1: [(M1, 0.42), (M2, 0.68), (M3, 0.58),
                       (M4, 0.64), (M5, 0.78)],
                   3: [(M1, 0.68), (M2, 0.42), (M3, 0.58),
                       (M5, 0.52)],
                   5: [(M1, 0.38), (M2, 0.12), (M3, 0.32),
                       (M4, 0.16), (M6, 0.42)],
                   7: [(M1, 0.22), (gravebar(8), 0.48), (M2, 0.38),
                       (M3, 0.62), (M4, 0.42), (M5, 0.72),
                       (recapbar(25), 0.9), (M6, 0.58)]},
     "effects": [FX_STRINGS]},
    {"name": "Orchestral Body", "script": "k2600.py", "gain_db": -8.0,
     "pan": 0.04, "notes": orchestra_notes(),
     "macros": {0: 0.42, 1: 0.68, 2: 0.18, 3: 0.04, 4: 0.52,
                5: 0.0, 6: 0.54, 7: 0.2, 8: 0.22, 9: 0.42,
                10: 0.72, 11: 0.48, 12: 0.08, 13: 0.32, 14: 0.12},
     "vol": [(M1, 0.58), (M2, 0.76), (M3, 0.82), (M4, 0.72),
             (M5, 1.0), (M6, 0.86)],
     "macro_env": {1: [(M1, 0.52), (M2, 0.72), (M3, 0.6),
                       (M4, 0.68), (M5, 0.8)],
                   4: [(M1, 0.62), (M2, 0.48), (M3, 0.38),
                       (M5, 0.58)],
                   6: [(M1, 0.38), (M2, 0.58), (M3, 0.46),
                       (M4, 0.54), (M5, 0.68)],
                   8: [(M1, 0.32), (M2, 0.14), (M3, 0.28),
                       (M4, 0.18), (M6, 0.36)]},
     "effects": [FX_ORCHESTRA]},
    {"name": "Solo Violin", "script": "cs80.py", "gain_db": -7.0,
     "pan": -0.1, "notes": violin_notes(),
     "macros": {0: 0.5, 1: 0.5, 2: 0.26, 3: 0.03, 4: 0.12,
                5: 0.06, 6: 0.42, 7: 0.44, 8: 0.08, 9: 0.3,
                10: 0.68, 11: 0.34, 12: 0.1, 13: 0.26, 14: 0.34,
                15: 0.52},
     "vol": [(M1, 0.68), (M2, 0.92), (M3, 1.08), (M4, 0.68),
             (M5, 1.0), (M6, 0.82)],
     "macro_env": {1: [(M1, 0.3), (M2, 0.56), (M3, 0.48),
                       (ariabar(9), 0.62), (M4, 0.54), (M5, 0.66),
                       (recapbar(25), 0.76), (M6, 0.46)],
                   5: [(M1, 0.02), (M2, 0.08), (M3, 0.04),
                       (M4, 0.1), (M5, 0.06)],
                   6: [(M1, 0.3), (M2, 0.48), (M3, 0.56),
                       (M4, 0.42), (M5, 0.62)],
                   11: [(M1, 0.42), (M2, 0.24), (M3, 0.5),
                        (M4, 0.22), (M6, 0.58)],
                   15: [(M1, 0.38), (M2, 0.58), (M3, 0.5),
                        (M4, 0.62), (M5, 0.72)]},
     "effects": [FX_VIOLIN]},
    {"name": "Solo Flute", "script": "emulator2.py", "gain_db": -8.0,
     "pan": 0.12, "notes": flute_notes(),
     "macros": {0: 0.48, 1: 0.22, 2: 0.58, 3: 0.08, 4: 0.28,
                5: 0.68, 6: 0.28, 7: 0.48, 8: 0.1, 9: 0.22},
     "vol": [(M1, 0.5), (M2, 0.78), (M3, 0.88), (M4, 1.2),
             (M5, 0.9), (M6, 0.62)],
     "macro_env": {1: [(M1, 0.34), (M2, 0.18), (M3, 0.24),
                       (M4, 0.16), (M6, 0.3)],
                   2: [(M1, 0.42), (M2, 0.62), (M3, 0.52),
                       (M4, 0.68), (M5, 0.72)],
                   8: [(M1, 0.04), (M2, 0.08), (M3, 0.16),
                       (M4, 0.1), (M6, 0.18)]},
     "effects": [FX_FLUTE]},
    {"name": "Horns", "script": "obxa.py", "gain_db": -7.0,
     "pan": 0.08, "notes": horn_notes(),
     "macros": {0: 0.48, 1: 0.28, 2: 0.48, 3: 0.22, 4: 0.56,
                5: 0.14, 6: 0.38, 7: 0.08, 8: 0.58, 9: 0.24},
     "vol": [(M1, 0.68), (M2, 0.84), (M3, 0.58), (M4, 0.72),
             (M5, 1.0), (M6, 0.88)],
     "macro_env": {1: [(M1, 0.18), (M2, 0.32), (M3, 0.2),
                       (M4, 0.36), (M5, 0.48)],
                   2: [(M1, 0.34), (M2, 0.54), (M3, 0.38),
                       (M4, 0.58), (M5, 0.7)],
                   4: [(M1, 0.38), (M2, 0.6), (M3, 0.34),
                       (M4, 0.62), (M5, 0.76)],
                   5: [(M1, 0.28), (M2, 0.1), (M3, 0.32),
                       (M4, 0.08), (M5, 0.05)]},
     "effects": [FX_HORNS]},
    {"name": "Pipe Organ", "script": "b3.py", "gain_db": -4.0,
     "pan": 0.0, "notes": organ_notes(),
     "macros": {0: 0.42, 1: 0.58, 2: 0.76, 3: 0.52, 4: 0.36,
                5: 0.18, 6: 0.48, 7: 0.02, 8: 0.0, 9: 0.08},
     "vol": [(M1, 0.8), (M2, 0.0), (M4, 1.4), (M5, 0.2),
             (recapbar(25), 0.62), (M6, 0.88)],
     "macro_env": {1: [(M1, 0.52), (M4, 0.42), (fuguebar(17), 0.68),
                       (M5, 0.36), (M6, 0.72)],
                   3: [(M1, 0.42), (M4, 0.5), (fuguebar(25), 0.7),
                       (M6, 0.62)],
                   5: [(M1, 0.12), (M4, 0.32), (fuguebar(25), 0.48),
                       (M6, 0.28)]},
     "effects": [FX_ORGAN]},
    {"name": "Concert Piano", "script": "cp70.py", "gain_db": -8.0,
     "pan": -0.04, "notes": piano_notes(),
     "macros": {0: 0.48, 1: 0.48, 2: 0.62, 3: 0.18, 4: 0.0,
                5: 0.08, 6: 0.52, 7: 0.56},
     "vol": [(M1, 0.56), (M2, 0.8), (M3, 0.86), (M4, 0.72),
             (M5, 0.9), (M6, 0.68)],
     "macro_env": {1: [(M1, 0.34), (M2, 0.58), (M3, 0.38),
                       (M4, 0.52), (M5, 0.64), (M6, 0.4)],
                   2: [(M1, 0.68), (M2, 0.52), (M3, 0.74),
                       (M4, 0.56), (M6, 0.8)],
                   7: [(M1, 0.38), (M2, 0.62), (M3, 0.48),
                       (M4, 0.66), (M5, 0.72)]},
     "effects": [FX_PIANO]},
    {"name": "Choir", "script": "vp330.py", "gain_db": -3.0,
     "pan": 0.06, "notes": choir_notes(),
     "macros": {0: 0.42, 1: 0.46, 2: 0.58, 3: 0.38, 4: 0.32,
                5: 0.62, 6: 0.5, 7: 0.42, 8: 0.08, 9: 0.52,
                10: 0.28},
     "vol": [(M5, 0.52), (recapbar(25), 0.88), (M6, 0.72),
             (codabar(13), 1.0)],
     "macro_env": {1: [(M5, 0.34), (recapbar(25), 0.58),
                       (M6, 0.48), (codabar(13), 0.68)],
                   2: [(M5, 0.42), (recapbar(25), 0.72),
                       (M6, 0.58), (codabar(13), 0.8)],
                   4: [(M5, 0.42), (M6, 0.3), (codabar(13), 0.5)],
                   9: [(M5, 0.42), (recapbar(25), 0.68),
                       (codabar(13), 0.78)]},
     "effects": [FX_CHOIR]},
]


def _db(value):
    return 10.0 ** (value / 20.0)


def _linear(points, beat, default):
    if not points:
        return default
    if beat <= points[0][0]:
        return points[0][1]
    for index in range(len(points) - 1):
        beat0, value0 = points[index]
        beat1, value1 = points[index + 1]
        if beat <= beat1:
            fraction = ((beat - beat0) / (beat1 - beat0)
                        if beat1 > beat0 else 1.0)
            return value0 + (value1 - value0) * fraction
    return points[-1][1]


def track_gain(track, beat):
    return _db(track["gain_db"]) * _linear(track["vol"], beat, 1.0)


def macro_value(unit, index, beat):
    env = unit.get("macro_env", {}).get(index)
    if env:
        return _linear(env, beat, unit.get("macros", {}).get(index, 0.5))
    return unit.get("macros", {}).get(index, 0.5)


def active_track_count(beat):
    count = 0
    for track in TRACKS:
        if any(start <= beat < start + duration
               for start, duration, _pitch, _velocity in track["notes"]):
            count += 1
    return count
