"""Perihelion - a hybrid orchestral/synth score for the MicroPython VST3.

Single source of truth for the piece: the tempo map, every note, the track
gains and pans, the volume swells, and the macro automation that gives the
synths their Moog-style motion. Both the offline preview renderer and the
REAPER project generator read this module.

Times are in beats (4/4, one bar = 4 beats, bar 1 starts at beat 0).
Velocities and macro values are 0..1.

Form, in D minor:
  A  "Adrift"      bars  1-12  @76   sub drone, breathing pad, glass halo,
                                     the four-note signal motif in bells
  B  "Ignition"    bars 13-28  @78   Moog ostinato ignites over a D pedal,
                                     low strings, pulse arp joins halfway
  C  "Approach"    bars 29-44  @80/82  theme in high strings, horns and
                                     timpani build, riser into the climax
  D  "Perihelion"  bars 45-60  @84   full brass theme, countermelody,
                                     impacts, lead doubles the theme
  E  "Afterglow"   bars 61-74  @76..64  choir, pads and bells resolve to
                                     D major, long tail
"""

TITLE = "Perihelion"
SAMPLE_RATE = 48000
MASTER_GAIN_DB = -2.0
ACTIVE_LIMIT = 8
CLIMAX_SECTION = "D Perihelion"
BEATS_PER_BAR = 4
TOTAL_BARS = 74
TAIL_SECONDS = 10.0

# (starting beat, bpm) - piecewise constant, points are section boundaries.
TEMPO_MAP = [
    (0.0, 76.0),     # A
    (48.0, 78.0),    # B  (bar 13)
    (112.0, 80.0),   # C  (bar 29)
    (144.0, 82.0),   # C second half (bar 37)
    (176.0, 84.0),   # D  (bar 45)
    (240.0, 76.0),   # E  (bar 61)
    (256.0, 72.0),   # bar 65
    (272.0, 68.0),   # bar 69
    (284.0, 64.0),   # bar 72
]

TOTAL_BEATS = float(TOTAL_BARS * BEATS_PER_BAR)


def beats_to_seconds(beat):
    """Exact beat->seconds through the piecewise-constant tempo map."""
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
    """Beat position of `beat` within 1-indexed bar `n`."""
    return (n - 1) * BEATS_PER_BAR + beat


# Pitch helpers ---------------------------------------------------------------

D1, A1, Bb1, C2, D2, F2, G2, A2, Bb2, C3, D3, E3, F3, G3, A3, Bb3 = (
    26, 33, 34, 36, 38, 41, 43, 45, 46, 48, 50, 52, 53, 55, 57, 58)
CS4 = 61
C4, D4, E4, F4, FS4, G4, A4, Bb4, C5, D5, E5, F5, FS5, G5, A5, C6 = (
    60, 62, 64, 65, 66, 67, 69, 70, 72, 74, 76, 77, 78, 79, 81, 84)


def notes_from(spec):
    """spec: list of (start_beat, duration_beats, pitch_or_list, velocity)."""
    out = []
    for start, dur, pitch, vel in spec:
        if isinstance(pitch, (list, tuple)):
            for p in pitch:
                out.append((start, dur, p, vel))
        else:
            out.append((start, dur, pitch, vel))
    return out


# --- Sub drone ---------------------------------------------------------------

def sub_drone_notes():
    return notes_from([
        (bar(1), bar(13) - bar(1) - 0.5, D1, 0.7),
        (bar(5), bar(13) - bar(5) - 0.5, D2, 0.5),
        # afterglow pedal through to the final chord
        (bar(61), bar(75) - bar(61) - 1.0, D1, 0.6),
    ])


# --- Moog bass ostinato ------------------------------------------------------

# Eighth-note spin: root, root, +7, root, +12, +10, +7, root.
OSTINATO_STEPS = (0, 0, 7, 0, 12, 10, 7, 0)


def ostinato_bar(start_beat, root, vel):
    out = []
    for i, step in enumerate(OSTINATO_STEPS):
        accent = 0.12 if i == 0 else (0.06 if i == 4 else 0.0)
        out.append((start_beat + i * 0.5, 0.45, root + step,
                    min(1.0, vel + accent)))
    return out


def moog_bass_notes():
    out = []
    # B: two-bar harmonic rhythm  D D Bb Bb F F C C  (D pedal feel kept by
    # returning to D roots every other pattern)
    roots_b = [D2, D2, Bb1, Bb1, F2, F2, C2, C2,
               D2, D2, Bb1, Bb1, F2, F2, C2, C2]
    for i, root in enumerate(roots_b):
        out += ostinato_bar(bar(13 + i), root, 0.6)
    # C first half: one chord per bar  Dm Bb F C x2
    roots_c1 = [D2, Bb1, F2, C2, D2, Bb1, F2, C2]
    for i, root in enumerate(roots_c1):
        out += ostinato_bar(bar(29 + i), root, 0.66)
    # C second half: Gm Gm Bb Bb A A A A - dominant tension
    roots_c2 = [G2, G2, Bb1, Bb1, A1, A1, A1, A1]
    for i, root in enumerate(roots_c2):
        out += ostinato_bar(bar(37 + i), root, 0.7 + 0.02 * i)
    # D: Dm Bb F C x4 at full tilt
    roots_d = [D2, Bb1, F2, C2] * 4
    for i, root in enumerate(roots_d):
        out += ostinato_bar(bar(45 + i), root, 0.82)
    return out


# --- Warm pad ----------------------------------------------------------------

def pad_warm_notes():
    return notes_from([
        # A: slow two-bar chords, Dm - Bb - Dm - Bb - Dm - Dm(add9)
        (bar(1), 8, [D3, A3, F4], 0.5),
        (bar(3), 8, [Bb2, F3, D4], 0.5),
        (bar(5), 8, [D3, A3, F4], 0.55),
        (bar(7), 8, [Bb2, F3, D4], 0.55),
        (bar(9), 8, [D3, A3, F4], 0.5),
        (bar(11), 8, [D3, A3, E4], 0.5),
        # B: roots and fifths breathing under the ostinato
        (bar(13), 8, [D3, A3], 0.45),
        (bar(15), 8, [Bb2, F3], 0.45),
        (bar(17), 8, [F3, C4], 0.45),
        (bar(19), 8, [C3, G3], 0.45),
        (bar(21), 8, [D3, A3], 0.48),
        (bar(23), 8, [Bb2, F3], 0.48),
        (bar(25), 8, [F3, C4], 0.5),
        (bar(27), 8, [C3, G3], 0.5),
        # E: the resolution progression  Bbmaj7 F/A Gm7 Dm x2
        (bar(61), 4, [Bb2, F3, D4, A4], 0.55),
        (bar(62), 4, [A2, F3, C4], 0.5),
        (bar(63), 4, [G2, F3, Bb3, D4], 0.5),
        (bar(64), 4, [D3, A3, F4], 0.5),
        (bar(65), 4, [Bb2, F3, D4, A4], 0.52),
        (bar(66), 4, [A2, F3, C4], 0.48),
        (bar(67), 4, [G2, F3, Bb3, D4], 0.48),
        (bar(68), 4, [D3, A3, F4], 0.48),
        # final approach: Gm - Asus - A - D major held
        (bar(69), 4, [G2, D3, Bb3], 0.5),
        (bar(70), 4, [A2, D3, E4], 0.5),
        (bar(71), 4, [A2, CS4, E4], 0.52),
        (bar(72), 12, [D3, A3, FS4], 0.55),
    ])


# --- Glass pad ---------------------------------------------------------------

def pad_glass_notes():
    return notes_from([
        (bar(2), 6, [D5, A5], 0.5),
        (bar(4), 6, [C5, G5], 0.45),
        (bar(6), 6, [D5, A5], 0.5),
        (bar(8), 6, [E5, A5], 0.45),
        (bar(10), 10, [D5, A5], 0.5),
        # E: return, brightening to the Picardy third
        (bar(63), 6, [D5, A5], 0.42),
        (bar(66), 6, [C5, A5], 0.4),
        (bar(69), 5, [Bb4, D5], 0.42),
        (bar(72), 12, [FS5, A5], 0.5),
    ])


# --- Low strings -------------------------------------------------------------

def strings_low_notes():
    out = notes_from([
        # B (from bar 17): long roots and fifths
        (bar(17), 8, [F2, C3], 0.5),
        (bar(19), 8, [C3, G3], 0.5),
        (bar(21), 8, [D2, A2], 0.55),
        (bar(23), 8, [Bb2, F3], 0.55),
        (bar(25), 8, [F2, C3], 0.58),
        (bar(27), 8, [C3, G3], 0.6),
        # C first half: one chord per bar under the theme
        (bar(29), 4, [D2, A2], 0.6),
        (bar(30), 4, [Bb2, F3], 0.6),
        (bar(31), 4, [F2, C3], 0.6),
        (bar(32), 4, [C3, G3], 0.6),
        (bar(33), 4, [D2, A2], 0.62),
        (bar(34), 4, [Bb2, F3], 0.62),
        (bar(35), 4, [F2, C3], 0.64),
        (bar(36), 4, [C3, G3], 0.66),
    ])
    # C second half: marcato eighth pulses, rising intensity
    roots = [(G2, D3), (G2, D3), (Bb2, F3), (Bb2, F3),
             (A2, E3), (A2, E3), (A2, E3), (A2, E3)]
    for b in range(8):
        vel = 0.6 + 0.03 * b
        lo, hi = roots[b]
        for i in range(8):
            out.append((bar(37 + b) + i * 0.5, 0.4, lo, vel))
            if i % 2 == 0:
                out.append((bar(37 + b) + i * 0.5, 0.4, hi, vel - 0.05))
    # D: driving eighths on the roots
    roots_d = [D2, Bb1, F2, C2] * 4
    for b, root in enumerate(roots_d):
        for i in range(8):
            vel = 0.78 + (0.08 if i == 0 else 0.0)
            out.append((bar(45 + b) + i * 0.5, 0.4, root, vel))
    # E: two soft suspensions
    out += notes_from([
        (bar(61), 16, [Bb2, F3], 0.42),
        (bar(65), 12, [D3, A3], 0.4),
    ])
    return out


# --- Theme -------------------------------------------------------------------

def theme_phrase(start, octave_shift=0, vel=0.7, vel_last=None):
    """The four-bar Perihelion theme over Dm - Bb - F - C."""
    s = octave_shift
    v2 = vel_last if vel_last is not None else vel
    return notes_from([
        (start + 0.0, 2.0, D4 + s, vel),
        (start + 2.0, 1.0, F4 + s, vel),
        (start + 3.0, 1.0, G4 + s, vel + 0.05),
        (start + 4.0, 3.0, A4 + s, vel + 0.08),
        (start + 7.0, 1.0, G4 + s, vel),
        (start + 8.0, 2.0, F4 + s, vel),
        (start + 10.0, 1.0, A4 + s, vel + 0.05),
        (start + 11.0, 1.0, G4 + s, vel),
        (start + 12.0, 2.5, E4 + s, v2),
        (start + 14.5, 1.5, D4 + s, v2),
    ])


# --- High strings ------------------------------------------------------------

def strings_high_notes():
    out = []
    # C: theme, twice; the second statement lifts its tail
    out += theme_phrase(bar(29), 0, 0.6)
    out += theme_phrase(bar(33), 0, 0.68)[:-2]
    out += notes_from([
        (bar(36, 0.0), 2.0, A4, 0.72),
        (bar(36, 2.0), 2.0, D5, 0.75),
    ])
    # D: soaring countermelody in whole notes above the brass
    counter = [A4, Bb4, C5, G4, A4, Bb4, A4, G4,
               A4, D5, C5, G4, A4, Bb4, C5, D5]
    for i, p in enumerate(counter):
        out.append((bar(45 + i), 3.9, p, 0.66 + 0.02 * (i % 4)))
    # E: one long suspended line coming down to rest
    out += notes_from([
        (bar(61), 8, A4, 0.45),
        (bar(63), 8, Bb4, 0.42),
        (bar(65), 8, A4, 0.4),
        (bar(67), 8, F4, 0.38),
    ])
    return out


# --- Horns -------------------------------------------------------------------

def horns_notes():
    out = notes_from([
        # C second half: swelling chords under the build
        (bar(37), 8, [G3, D4], 0.55),
        (bar(39), 8, [Bb3, F4], 0.6),
        (bar(41), 8, [A3, D4], 0.65),
        (bar(43), 8, [A3, E4], 0.72),
    ])
    # D: rhythmic stabs on the downbeats, thirds added on odd bars
    chords = [(D3, A3), (Bb2, F3), (F3, C4), (C3, G3)] * 4
    for b, (lo, hi) in enumerate(chords):
        vel = 0.8 if b % 4 == 0 else 0.72
        out.append((bar(45 + b), 1.5, lo, vel))
        out.append((bar(45 + b), 1.5, hi, vel))
        if b % 2 == 1:
            out.append((bar(45 + b) + 2.0, 1.5, lo, vel - 0.08))
            out.append((bar(45 + b) + 2.0, 1.5, hi, vel - 0.08))
    return out


# --- High brass --------------------------------------------------------------

def brass_high_notes():
    out = []
    out += theme_phrase(bar(45), 0, 0.8)
    out += theme_phrase(bar(49), 0, 0.85)
    out += theme_phrase(bar(53), 0, 0.88)
    # final statement: hold the peak instead of resolving down
    out += theme_phrase(bar(57), 0, 0.92)[:-2]
    out += notes_from([
        (bar(60, 0.0), 4.0, A4, 0.95),
    ])
    return out


# --- Choir -------------------------------------------------------------------

def choir_notes():
    return notes_from([
        (bar(65), 4, [Bb3, D4, F4], 0.5),
        (bar(66), 4, [A3, C4, F4], 0.48),
        (bar(67), 4, [Bb3, D4, G4], 0.5),
        (bar(68), 4, [A3, D4, F4], 0.5),
        (bar(69), 4, [Bb3, D4, G4], 0.52),
        (bar(70), 4, [A3, D4, E4], 0.52),
        (bar(71), 4, [A3, 61, E4], 0.55),
        (bar(72), 12, [D4, FS4, A4], 0.6),
    ])


# --- Lead --------------------------------------------------------------------

def lead_notes():
    out = []
    # D second half: double the theme an octave up
    out += theme_phrase(bar(53), 12, 0.6)
    out += theme_phrase(bar(57), 12, 0.62)[:-2]
    out += notes_from([
        (bar(60, 0.0), 4.0, A5, 0.66),
        # E: distant echoes of the motif
        (bar(69), 3.0, D5, 0.4),
        (bar(70), 2.5, C5, 0.36),
        (bar(71), 4.0, A4, 0.34),
    ])
    return out


# --- Arp ---------------------------------------------------------------------

ARP_STEPS = (0, 7, 12, 19, 24, 19, 12, 7)


def arp_bar(start_beat, root, vel):
    out = []
    for i in range(16):
        step = ARP_STEPS[i % 8]
        out.append((start_beat + i * 0.25, 0.22, root + step,
                    vel + (0.06 if i % 8 == 0 else 0.0)))
    return out


def arp_notes():
    out = []
    roots_b = [D3, D3, Bb2, Bb2, F3, F3, C3, C3]
    for i, root in enumerate(roots_b):
        out += arp_bar(bar(21 + i), root, 0.5)
    roots_c = [D3, Bb2, F3, C3, D3, Bb2, F3, C3,
               G2, G2, Bb2, Bb2, A2, A2, A2, A2]
    for i, root in enumerate(roots_c):
        out += arp_bar(bar(29 + i), root, 0.55)
    roots_d = [D3, Bb2, F3, C3] * 2
    for i, root in enumerate(roots_d):
        out += arp_bar(bar(45 + i), root, 0.6)
    return out


# --- Timpani -----------------------------------------------------------------

def timpani_notes():
    out = []
    # C second half: quarter pulses, growing (the roll takes over the back
    # half of bar 44)
    for b in range(8):
        for q in range(4):
            if b == 7 and q >= 2:
                continue
            out.append((bar(37 + b) + q, 0.8, D2, 0.42 + 0.04 * b))
    # roll into the climax across the last half of bar 44
    for i in range(8):
        out.append((bar(44, 2.0) + i * 0.25, 0.2, D2, 0.5 + 0.06 * i))
    # D: strong pattern - 1, 3, and the and-of-4 pickup
    for b in range(16):
        root = D2 if b % 4 in (0, 3) else (Bb1 if b % 4 == 1 else F2)
        out.append((bar(45 + b), 0.9, root, 0.9))
        out.append((bar(45 + b) + 2.0, 0.9, root, 0.7))
        out.append((bar(45 + b) + 3.5, 0.4, A1, 0.6))
    # final resolution stroke
    out.append((bar(72), 3.0, D2, 0.7))
    return out


# --- Hits --------------------------------------------------------------------

def hits_notes():
    return notes_from([
        (bar(13), 3.0, D2, 0.85),
        (bar(29), 3.0, D2, 0.9),
        (bar(45), 3.5, D2, 1.0),
        (bar(53), 3.5, D2, 0.95),
        (bar(61), 3.0, Bb2, 0.45),
    ])


# --- Shimmer -----------------------------------------------------------------

def shimmer_notes():
    return notes_from([
        (bar(5), 6.0, C4, 0.4),
        (bar(11), 7.5, C4, 0.55),
        (bar(27), 7.5, C4, 0.6),
        (bar(43), 7.5, C4, 0.7),
        (bar(59), 7.5, C4, 0.5),
        (bar(71), 4.0, C4, 0.4),
    ])


# --- Bells -------------------------------------------------------------------

def bells_motif(start, vel):
    return [
        (start + 0.0, 1.5, D5, vel),
        (start + 1.5, 1.0, A5, vel - 0.06),
        (start + 3.0, 1.5, C6, vel),
        (start + 5.5, 2.0, A5, vel - 0.1),
    ]


def bells_notes():
    out = []
    out += bells_motif(bar(3), 0.55)
    out += bells_motif(bar(7), 0.6)
    out += bells_motif(bar(11), 0.5)
    # B: sparser answers over the ostinato
    out += [
        (bar(17), 1.5, D5, 0.5), (bar(17, 2.0), 2.0, F5, 0.45),
        (bar(25), 1.5, E5, 0.5), (bar(25, 2.0), 2.0, G5, 0.45),
    ]
    # E: the motif restated in augmentation, settling onto F#
    out += [
        (bar(63), 3.0, D5, 0.5),
        (bar(64), 2.0, A5, 0.45),
        (bar(65), 3.0, C6, 0.48),
        (bar(67), 3.0, A5, 0.42),
        (bar(69), 3.0, D5, 0.45),
        (bar(70), 3.0, C5, 0.4),
        (bar(72), 6.0, FS5, 0.5),
        (bar(73), 5.0, A5, 0.42),
    ]
    return out


# --- Riser -------------------------------------------------------------------

def riser_notes():
    return notes_from([
        (bar(27), 8.0, D3, 0.5),      # into Approach
        (bar(43), 8.0, D3, 0.7),      # into Perihelion
    ])


# --- Track table -------------------------------------------------------------
#
# macros: initial value per macro index (unlisted macros stay at 0.5)
# vol:    (beat, multiplier) points, linear, on top of gain_db
# macro_env: {macro_index: [(beat, value), ...]} - linear PARMENV automation

def _db(x):
    return 10.0 ** (x / 20.0)


TRACKS = [
    {
        "name": "Sub Drone", "script": "sub_drone.py", "gain_db": -6.5,
        "pan": 0.0, "notes": sub_drone_notes(),
        "macros": {0: 0.45, 1: 0.3},
        "vol": [(bar(1), 0.6), (bar(5), 0.9), (bar(12), 1.0),
                (bar(61), 0.8), (bar(72), 0.75), (bar(74, 4.0), 0.5)],
        "macro_env": {0: [(bar(1), 0.3), (bar(9), 0.5), (bar(61), 0.45)]},
    },
    {
        "name": "Moog Bass", "script": "moog_bass.py", "gain_db": -6.5,
        "pan": 0.0, "notes": moog_bass_notes(),
        "macros": {0: 0.3, 1: 0.45, 2: 0.4},
        "vol": [(bar(13), 0.85), (bar(29), 0.95), (bar(45), 1.05),
                (bar(60, 3.0), 1.0)],
        "macro_env": {
            # The Moog move: slow four-bar cutoff waves that open section by
            # section, then a fast closing dive at the end of the climax.
            0: [(bar(13), 0.24), (bar(17), 0.45), (bar(21), 0.3),
                (bar(25), 0.5), (bar(29), 0.38), (bar(33), 0.62),
                (bar(37), 0.5), (bar(41), 0.72), (bar(44), 0.78),
                (bar(45), 0.55), (bar(49), 0.85), (bar(53), 0.65),
                (bar(57), 0.9), (bar(60), 0.92), (bar(60, 3.5), 0.3)],
            1: [(bar(13), 0.42), (bar(29), 0.52), (bar(37), 0.6),
                (bar(45), 0.62), (bar(57), 0.5)],
            2: [(bar(13), 0.4), (bar(29), 0.55), (bar(45), 0.7)],
        },
    },
    {
        "name": "Warm Pad", "script": "pad_warm.py", "gain_db": -3.5,
        "pan": 0.0, "notes": pad_warm_notes(),
        "macros": {0: 0.2, 1: 0.5, 2: 0.6},
        "vol": [(bar(1), 0.4), (bar(5), 0.7), (bar(9), 0.85),
                (bar(13), 0.75), (bar(28, 4.0), 0.75), (bar(61), 0.72),
                (bar(69), 0.68), (bar(72), 0.7), (bar(74, 4.0), 0.5)],
        "macro_env": {
            # the intro is one long filter sunrise
            0: [(bar(1), 0.12), (bar(9), 0.42), (bar(12), 0.5),
                (bar(13), 0.35), (bar(28), 0.45), (bar(61), 0.45),
                (bar(70), 0.32), (bar(74), 0.24)],
        },
    },
    {
        "name": "Glass Pad", "script": "pad_glass.py", "gain_db": -8.0,
        "pan": 0.1, "notes": pad_glass_notes(),
        "macros": {0: 0.35, 1: 0.6},
        "vol": [(bar(1), 0.58), (bar(10), 0.8), (bar(63), 0.7),
                (bar(72), 0.85)],
        "macro_env": {0: [(bar(2), 0.25), (bar(10), 0.55), (bar(63), 0.35),
                          (bar(72), 0.6)]},
    },
    {
        "name": "Low Strings", "script": "strings_low.py", "gain_db": -4.5,
        "pan": -0.15, "notes": strings_low_notes(),
        "macros": {0: 0.4, 1: 0.4},
        "vol": [(bar(17), 0.95), (bar(29), 0.95), (bar(37), 0.95),
                (bar(44), 1.05), (bar(45), 1.05), (bar(61), 0.7)],
        "macro_env": {0: [(bar(17), 0.35), (bar(37), 0.5), (bar(44), 0.62),
                          (bar(45), 0.68), (bar(61), 0.3)]},
    },
    {
        "name": "High Strings", "script": "strings_high.py", "gain_db": -7.5,
        "pan": 0.15, "notes": strings_high_notes(),
        "macros": {0: 0.45, 1: 0.4},
        "vol": [(bar(29), 0.85), (bar(36), 1.0), (bar(45), 1.15),
                (bar(61), 0.7), (bar(68, 4.0), 0.6)],
        "macro_env": {0: [(bar(29), 0.4), (bar(36), 0.55), (bar(45), 0.7),
                          (bar(61), 0.3)]},
    },
    {
        "name": "Horns", "script": "horns.py", "gain_db": -4.5,
        "pan": -0.2, "notes": horns_notes(),
        "macros": {0: 0.5, 1: 0.4},
        "vol": [(bar(37), 0.8), (bar(43), 1.0), (bar(45), 1.0)],
        "macro_env": {0: [(bar(37), 0.4), (bar(44), 0.65), (bar(45), 0.7)]},
    },
    {
        "name": "High Brass", "script": "brass_high.py", "gain_db": -6.0,
        "pan": 0.2, "notes": brass_high_notes(),
        "macros": {0: 0.55, 1: 0.35},
        "vol": [(bar(45), 0.9), (bar(53), 1.0), (bar(60), 1.08)],
        "macro_env": {0: [(bar(45), 0.5), (bar(57), 0.72), (bar(60), 0.8)]},
    },
    {
        "name": "Choir", "script": "choir.py", "gain_db": -3.5,
        "pan": 0.0, "notes": choir_notes(),
        "macros": {0: 0.45, 1: 0.6},
        "vol": [(bar(65), 0.75), (bar(71), 0.9), (bar(74, 4.0), 0.65)],
        "macro_env": {0: [(bar(65), 0.35), (bar(72), 0.6)]},
    },
    {
        "name": "Lead", "script": "lead.py", "gain_db": -7.5,
        "pan": 0.05, "notes": lead_notes(),
        "macros": {0: 0.6, 1: 0.35, 2: 0.5},
        "vol": [(bar(53), 0.9), (bar(60), 1.0), (bar(69), 0.8)],
        "macro_env": {
            0: [(bar(53), 0.5), (bar(57), 0.75), (bar(60), 0.85),
                (bar(69), 0.42), (bar(71, 4.0), 0.3)],
            2: [(bar(53), 0.4), (bar(69), 0.65)],
        },
    },
    {
        "name": "Pulse Arp", "script": "arp.py", "gain_db": -10.5,
        "pan": -0.1, "notes": arp_notes(),
        "macros": {0: 0.3, 1: 0.5, 2: 0.55},
        "vol": [(bar(21), 0.7), (bar(29), 0.9), (bar(45), 1.0),
                (bar(52, 4.0), 0.9)],
        "macro_env": {
            # the classic rising-cutoff build, twice
            0: [(bar(21), 0.18), (bar(28), 0.5), (bar(29), 0.35),
                (bar(40), 0.7), (bar(44), 0.85), (bar(45), 0.6),
                (bar(52), 0.8)],
            1: [(bar(21), 0.45), (bar(41), 0.6), (bar(45), 0.5)],
        },
    },
    {
        "name": "Timpani", "script": "timpani.py", "gain_db": -6.5,
        "pan": -0.05, "notes": timpani_notes(),
        "macros": {0: 0.5, 1: 0.5},
        "vol": [(bar(37), 0.7), (bar(44), 0.95), (bar(45), 0.95),
                (bar(72), 0.75)],
        "macro_env": {},
    },
    {
        "name": "Impacts", "script": "hits.py", "gain_db": -5.5,
        "pan": 0.0, "notes": hits_notes(),
        "macros": {0: 0.5, 1: 0.6},
        "vol": [(bar(13), 0.85), (bar(45), 0.85), (bar(61), 0.7)],
        "macro_env": {0: [(bar(13), 0.4), (bar(29), 0.5), (bar(45), 0.7),
                          (bar(61), 0.3)]},
    },
    {
        "name": "Air Shimmer", "script": "shimmer.py", "gain_db": -12.0,
        "pan": 0.1, "notes": shimmer_notes(),
        "macros": {0: 0.55, 1: 0.7},
        "vol": [(bar(1), 0.9), (bar(43), 1.0), (bar(71), 0.8)],
        "macro_env": {},
    },
    {
        "name": "Aurora Bells", "script": "bells.py", "gain_db": -8.5,
        "pan": 0.25, "notes": bells_notes(),
        "macros": {0: 0.35, 1: 0.5, 2: 0.55},
        "vol": [(bar(3), 0.62), (bar(13), 0.85), (bar(63), 1.0),
                (bar(72), 1.0)],
        "macro_env": {1: [(bar(3), 0.5), (bar(63), 0.65)]},
    },
    {
        "name": "Riser", "script": "riser.py", "gain_db": -10.0,
        "pan": 0.0, "notes": riser_notes(),
        "macros": {0: 0.0, 1: 0.5, 2: 0.5},
        "vol": [(bar(27), 0.8), (bar(43), 1.0)],
        "macro_env": {
            0: [(bar(27), 0.0), (bar(28, 4.0), 0.6), (bar(29), 0.0),
                (bar(43), 0.0), (bar(44, 4.0), 1.0), (bar(45), 0.0)],
            1: [(bar(27), 0.4), (bar(29), 0.6), (bar(43), 0.45),
                (bar(45), 0.85)],
        },
    },
]


def track_gain(track, beat):
    """Linear gain (envelope value) for a track at `beat`."""
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
    """Automated macro value at `beat` (falls back to the initial value)."""
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
    """How many tracks have a sounding note at `beat` (excludes tails)."""
    count = 0
    for track in TRACKS:
        for start, dur, _pitch, _vel in track["notes"]:
            if start <= beat < start + dur:
                count += 1
                break
    return count

SECTIONS = [
    ("A Adrift", bar(1), bar(13)),
    ("B Ignition", bar(13), bar(29)),
    ("C Approach", bar(29), bar(45)),
    ("D Perihelion", bar(45), bar(61)),
    ("E Afterglow", bar(61), bar(75)),
]
