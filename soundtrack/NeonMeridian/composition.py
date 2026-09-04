"""Neon Meridian - 80s synthwave for the MicroPython VST3.

Nine shared hardware emulations, no effect inserts. The instruments carry
their own character the way the hardware did: the Juno-106's bucket-brigade
chorus, the Solina's ensemble, the Minimoog's overdrive, the LinnDrum's
samples. Depth comes from arrangement, register, and pan - not from a rack.

Times are in beats (4/4 throughout, one bar = 4 beats, bar 1 starts at
beat 0). Velocities and macro values are 0..1.

Form, in A minor:
  A  "Nightfall"   bars  1-20  @100  Juno pad alone, bell motif, Taurus
                                     pedal, SH-101 arp, hats then kick;
                                     harmonic rhythm accelerates 4 bars
                                     per chord -> 1 bar per chord
  B  "Neon Mile"   bars 21-52  @106  Minimoog ostinato and the full
                                     LinnDrum; Prophet-5 states the theme
                                     twice, Solina and OB-Xa join; a
                                     four-bar breakdown at 45 rebuilds
  C  "Afterburn"   bars 53-76  @106  theme at full weight, an eight-bar
                                     lift through the relative major,
                                     return to A minor, ritard to a held
                                     Am(add9)

The one modulation is the C-major excursion at bar 61; everything else is
diatonic A minor coloured with added ninths.
"""

TITLE = "Neon_Meridian"
INSTRUMENTS_DIR = "../../lib/instruments"
SAMPLE_RATE = 48000
MASTER_GAIN_DB = 0.0
ACTIVE_LIMIT = 9
CLIMAX_SECTION = "C Afterburn"
BEATS_PER_BAR = 4
TOTAL_BARS = 76
TAIL_SECONDS = 10.0

# (starting beat, bpm) - piecewise constant, points are section boundaries.
TEMPO_MAP = [
    (0.0, 100.0),    # A  (bar 1)
    (80.0, 106.0),   # B  (bar 21) - and C, which keeps the tempo
    (288.0, 100.0),  # ritard begins (bar 73)
    (292.0, 92.0),   # bar 74
    (296.0, 84.0),   # bar 75
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

F1, G1, A1, C2, D2, E2, F2, G2, A2 = 29, 31, 33, 36, 38, 40, 41, 43, 45
C3, D3, E3, F3, G3, A3, B3 = 48, 50, 52, 53, 55, 57, 59
C4, D4, E4, F4, G4, A4, B4 = 60, 62, 64, 65, 67, 69, 71
C5, D5, E5, F5, G5, A5, B5 = 72, 74, 76, 77, 79, 81, 83
C6, E6 = 84, 88

# LinnDrum voices (General MIDI positions, as the emulation maps them).
BD, SD, CLAP, RIM = 36, 38, 39, 37
CH, PEDAL_H, OH = 42, 44, 46
LT, MT, HT = 41, 45, 48
CRASH, RIDE = 49, 51


# Harmony ---------------------------------------------------------------------

# Every chord is a triad plus an added ninth - the "mild colour" of the
# piece.  Voicings are fixed per register so the parts stay in their lanes
# instead of leaping an octave whenever the root moves.
PAD_VOICING = {
    "Am": (A3, C4, E4, B4),      # Am(add9)
    "F": (F3, A3, C4, G4),       # Fadd9
    "C": (C4, E4, G4, D5),       # Cadd9
    "G": (G3, B3, D4, A4),       # Gadd9
}
STRING_VOICING = {
    "Am": (E4, A4, C5),
    "F": (F4, A4, C5),
    "C": (E4, G4, C5),
    "G": (D4, G4, B4),
}
STAB_VOICING = {
    "Am": (A4, C5, E5),
    "F": (A4, C5, F5),
    "C": (G4, C5, E5),
    "G": (G4, B4, D5),
}
ARP_TONES = {
    "Am": (A3, C4, E4, A4),
    "F": (F3, A3, C4, F4),
    "C": (C4, E4, G4, C5),
    "G": (G3, B3, D4, G4),
}
BASS_ROOT = {"Am": A1, "F": F1, "C": C2, "G": G1}
SUB_ROOT = {"Am": A1, "F": F1, "C": C2, "G": G1}

# (start_bar, span_bars, chord).  Section A's harmonic rhythm accelerates
# from four bars per chord to one, which is what actually creates the pull
# into the downbeat of B.
PROGRESSION = (
    [(1, 4, "Am"), (5, 4, "F"), (9, 4, "C"), (13, 4, "G")]
    + [(17, 1, "Am"), (18, 1, "F"), (19, 1, "C"), (20, 1, "G")]
    # B: eight turns of the loop
    + [(21 + 4 * i + j, 1, name)
       for i in range(8)
       for j, name in enumerate(("Am", "F", "C", "G"))]
    # C: two turns in A minor
    + [(53 + 4 * i + j, 1, name)
       for i in range(2)
       for j, name in enumerate(("Am", "F", "C", "G"))]
    # C: the relative-major lift, closing on a dominant to get home
    + [(61, 1, "F"), (62, 1, "C"), (63, 1, "G"), (64, 1, "Am"),
       (65, 1, "F"), (66, 1, "C"), (67, 1, "G"), (68, 1, "G")]
    # C: return and final cadence
    + [(69, 1, "Am"), (70, 1, "F"), (71, 1, "C"), (72, 1, "G"),
       (73, 4, "Am")]
)


def chord_at(bar_number):
    """Chord name governing 1-indexed `bar_number`."""
    for start, span, name in PROGRESSION:
        if start <= bar_number < start + span:
            return name
    return "Am"


def chord_spans(first_bar, last_bar):
    """(start_bar, span_bars, chord) clipped to [first_bar, last_bar]."""
    out = []
    for start, span, name in PROGRESSION:
        lo = max(start, first_bar)
        hi = min(start + span, last_bar + 1)
        if hi > lo:
            out.append((lo, hi - lo, name))
    return out


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


# Note durations are always trimmed slightly below their nominal length.
# Two notes of the same pitch that merely touch would be a same-pitch
# overlap in the generated MIDI, which generate_project.py rejects outright.
GAP = 0.06


def held(start, beats, pitches, vel):
    """One sustained stack, released just before the next chord lands."""
    return [(start, max(0.05, beats - GAP), p, vel) for p in pitches]


# --- Juno-106 pad ------------------------------------------------------------

def pad_notes():
    """The bed, present from the first bar to the last."""
    out = []
    for start, span, name in chord_spans(1, TOTAL_BARS):
        vel = 0.52
        if start >= 21:
            vel = 0.58
        if start >= 53:
            vel = 0.64
        if start >= 73:
            vel = 0.5
        out += held(bar(start), span * BEATS_PER_BAR,
                    PAD_VOICING[name], vel)
    return out


# --- Solina string ensemble --------------------------------------------------

def strings_notes():
    """Upper sustain. Enters with the theme, carries the lift, then fades."""
    out = []
    for start, span, name in chord_spans(37, 72):
        if 45 <= start <= 48:          # sits out the breakdown
            continue
        vel = 0.5 if start < 53 else 0.62
        out += held(bar(start), span * BEATS_PER_BAR,
                    STRING_VOICING[name], vel)
    # final chord, an octave of air over the ritard
    out += held(bar(73), 4 * BEATS_PER_BAR, (E4, A4, C5, E5), 0.44)
    return out


# --- Moog Taurus pedal -------------------------------------------------------

def sub_notes():
    """Roots only, and only where the Minimoog isn't already playing them."""
    out = []
    for start, span, name in chord_spans(5, 20):
        out.append((bar(start), span * BEATS_PER_BAR - GAP,
                    SUB_ROOT[name], 0.6))
    # breakdown: the sub is what holds the floor when the drums drop
    for start, span, name in chord_spans(45, 48):
        out.append((bar(start), span * BEATS_PER_BAR - GAP,
                    SUB_ROOT[name], 0.62))
    # climax downbeats, reinforcing rather than doubling
    for n in (53, 57, 61, 65, 69):
        out.append((bar(n), BEATS_PER_BAR - GAP, SUB_ROOT[chord_at(n)], 0.55))
    out.append((bar(73), 4 * BEATS_PER_BAR - GAP, A1, 0.58))
    return out


# --- Minimoog bass -----------------------------------------------------------

# Straight eighths with an octave lift on the "and" of 2 and of 4 - the
# engine of the whole piece.  Accent pattern, not pitch pattern, is what
# makes it drive.
BASS_STEPS = ((0.0, 0), (0.5, 0), (1.0, 0), (1.5, 12),
              (2.0, 0), (2.5, 0), (3.0, 0), (3.5, 12))


def bass_bar(start_beat, root, vel):
    out = []
    for offset, step in BASS_STEPS:
        accent = 0.14 if offset == 0.0 else (0.07 if step else 0.0)
        out.append((start_beat + offset, 0.44, root + step,
                    min(1.0, vel + accent)))
    return out


def bass_notes():
    out = []
    for start, span, name in chord_spans(21, 72):
        if 45 <= start <= 48:          # out for the breakdown
            continue
        vel = 0.62
        if start >= 29:
            vel = 0.68
        if start >= 53:
            vel = 0.74
        for n in range(start, start + span):
            out += bass_bar(bar(n), BASS_ROOT[name], vel)
    # one last root, landing with the final chord
    out.append((bar(73), 3.0, A1, 0.7))
    return out


# --- SH-101 arpeggio ---------------------------------------------------------

# Sixteenths, up-and-back across the chord's four tones.  Sixteenths are
# 0.25 beats and each note is 0.2, so repeated tones never collide.
ARP_PATTERN = (0, 1, 2, 3, 2, 1, 0, 1, 2, 3, 2, 1, 0, 1, 2, 3)


def arp_notes():
    out = []
    for start, span, name in chord_spans(9, 72):
        if 45 <= start <= 46:          # clears the top of the breakdown
            continue
        tones = ARP_TONES[name]
        vel = 0.34
        if start >= 21:
            vel = 0.42
        if start >= 47:                # the rebuild out of the breakdown
            vel = 0.46
        if start >= 53:
            vel = 0.5
        for n in range(start, start + span):
            for i, index in enumerate(ARP_PATTERN):
                accent = 0.08 if i % 4 == 0 else 0.0
                out.append((bar(n) + i * 0.25, 0.2, tones[index],
                            min(1.0, vel + accent)))
    return out


# --- OB-Xa stabs -------------------------------------------------------------

def stab_notes():
    """Offbeat eighth-note chords - the classic poly-brass push."""
    out = []
    for start, span, name in chord_spans(37, 72):
        if 45 <= start <= 48:
            continue
        vel = 0.46 if start < 53 else 0.56
        voicing = STAB_VOICING[name]
        for n in range(start, start + span):
            for offset in (1.5, 2.5, 3.5):
                out += [(bar(n) + offset, 0.4, p, vel) for p in voicing]
    # a single held hit on the last chord
    out += held(bar(73), BEATS_PER_BAR, STAB_VOICING["Am"], 0.5)
    return out


# --- Prophet-5 lead ----------------------------------------------------------

# The theme: eight bars over Am F C G Am F C G.  Written once, restated
# with a different register and articulation each time it comes back.
THEME = (
    # (bar offset, beat in bar, duration, pitch)
    (0, 0.0, 2.0, E5), (0, 2.0, 1.0, D5), (0, 3.0, 1.0, C5),
    (1, 0.0, 3.0, A4), (1, 3.0, 1.0, C5),
    (2, 0.0, 2.0, E5), (2, 2.0, 2.0, G5),
    (3, 0.0, 3.0, D5), (3, 3.0, 1.0, B4),
    (4, 0.0, 2.0, E5), (4, 2.0, 1.0, D5), (4, 3.0, 1.0, C5),
    (5, 0.0, 2.0, A4), (5, 2.0, 1.0, C5), (5, 3.0, 1.0, E5),
    (6, 0.0, 3.0, G5), (6, 3.0, 1.0, E5),
    (7, 0.0, 4.0, D5),
)

# The lift: eight bars over F C G Am F C G G, sitting a register higher.
LIFT = (
    (0, 0.0, 2.0, C5), (0, 2.0, 2.0, F5),
    (1, 0.0, 3.0, E5), (1, 3.0, 1.0, G5),
    (2, 0.0, 2.0, D5), (2, 2.0, 1.0, B4), (2, 3.0, 1.0, D5),
    (3, 0.0, 4.0, C5),
    (4, 0.0, 2.0, C5), (4, 2.0, 1.0, F5), (4, 3.0, 1.0, A5),
    (5, 0.0, 3.0, G5), (5, 3.0, 1.0, E5),
    (6, 0.0, 2.0, D5), (6, 2.0, 2.0, G5),
    (7, 0.0, 3.0, B4), (7, 3.0, 1.0, D5),
)


def phrase(table, first_bar, vel, transpose=0):
    return [(bar(first_bar + offset, beat), dur - GAP, pitch + transpose, vel)
            for offset, beat, dur, pitch in table]


def lead_notes():
    out = []
    out += phrase(THEME, 29, 0.62)                   # first statement
    out += phrase(THEME, 37, 0.7)                    # restated, stronger
    out += phrase(THEME, 53, 0.8)                    # climax
    out += phrase(LIFT, 61, 0.82)                    # relative-major lift
    # final descent home
    out += [(bar(69), 2.0 - GAP, E5, 0.7),
            (bar(69, 2.0), 2.0 - GAP, C5, 0.66),
            (bar(70), 3.0 - GAP, A4, 0.64),
            (bar(70, 3.0), 1.0 - GAP, C5, 0.6),
            (bar(71), 2.0 - GAP, E5, 0.62),
            (bar(71, 2.0), 2.0 - GAP, D5, 0.58),
            (bar(72), 4.0 - GAP, B4, 0.56),
            (bar(73), 6.0, A4, 0.54)]
    return out


# --- DX7 bells ---------------------------------------------------------------

# The four-note signal: E - D - C - A, the head of the theme. It opens the
# piece, marks the breakdown, and closes it.
MOTIF = (E5, D5, C5, A4)


def bell_notes():
    out = []
    # A: stated twice, slowly, two beats a note
    for n, base in ((3, 0), (11, 0)):
        for i, pitch in enumerate(MOTIF):
            out.append((bar(n) + i * 2.0, 1.9, pitch + base, 0.44))
    # B breakdown: the motif alone, an octave up, no drums under it
    for i, pitch in enumerate(MOTIF):
        out.append((bar(45) + i * 4.0, 3.8, pitch + 12, 0.4))
    # sparse punctuation through the climax
    for n in (57, 65):
        for i, pitch in enumerate(MOTIF):
            out.append((bar(n) + i * 1.0, 0.9, pitch + 12, 0.34))
    # outro: the motif resolves down to the tonic and rings out
    for i, pitch in enumerate(MOTIF):
        out.append((bar(73) + i * 2.0, 1.9, pitch, 0.4))
    out.append((bar(75), 6.0, A5, 0.36))
    out.append((bar(75), 6.0, E6, 0.3))
    return out


# --- LinnDrum ---------------------------------------------------------------

def hats(first_bar, last_bar, eighths=True, vel=0.4):
    out = []
    step = 0.5 if eighths else 1.0
    count = int(BEATS_PER_BAR / step)
    for n in range(first_bar, last_bar + 1):
        for i in range(count):
            offset = i * step
            if eighths and offset == 3.5:
                continue                       # open hat takes this slot
            accent = 0.12 if offset == int(offset) else 0.0
            out.append((bar(n) + offset, 0.2, CH, min(1.0, vel + accent)))
        if eighths:
            out.append((bar(n) + 3.5, 0.4, OH, 0.42))
    return out


def backbeat(first_bar, last_bar, clap=True, vel=0.72):
    out = []
    for n in range(first_bar, last_bar + 1):
        for offset in (1.0, 3.0):
            out.append((bar(n) + offset, 0.4, SD, vel))
            if clap:
                out.append((bar(n) + offset, 0.4, CLAP, vel - 0.08))
    return out


def kicks(first_bar, last_bar, vel=0.85):
    """Kick on 1 and 3 with a pickup sixteenth before the next downbeat."""
    out = []
    for n in range(first_bar, last_bar + 1):
        out.append((bar(n), 0.4, BD, vel))
        out.append((bar(n) + 2.0, 0.4, BD, vel - 0.06))
        if n % 4 == 0:                          # every fourth bar, a push
            out.append((bar(n) + 3.75, 0.2, BD, vel - 0.18))
    return out


def tom_fill(n, vel=0.7):
    """Four sixteenths across the last beat of bar `n`."""
    return [(bar(n) + 3.0 + i * 0.25, 0.22, p, vel + i * 0.03)
            for i, p in enumerate((HT, HT, MT, LT))]


def drum_notes():
    out = []
    # A: hats alone, then the kick joins for the last four bars
    out += hats(13, 20, eighths=False, vel=0.34)
    out += kicks(17, 20, vel=0.72)
    out += backbeat(19, 20, clap=False, vel=0.6)
    out += tom_fill(20, 0.68)
    out.append((bar(21), 0.4, CRASH, 0.7))

    # B: the full pattern
    out += hats(21, 44)
    out += kicks(21, 44)
    out += backbeat(21, 44)
    out += tom_fill(28, 0.68)
    out += tom_fill(36, 0.72)
    out += tom_fill(44, 0.76)

    # B breakdown at 45-48: nothing but a rim pulse, then the rebuild
    for n in range(45, 49):
        out += [(bar(n) + o, 0.2, RIM, 0.34) for o in (0.0, 2.0)]
    out += hats(49, 52)
    out += kicks(49, 52)
    out += backbeat(49, 52)
    out += tom_fill(52, 0.8)

    # C: full weight through the climax and the lift
    out.append((bar(53), 0.4, CRASH, 0.78))
    out += hats(53, 72)
    out += kicks(53, 72, vel=0.9)
    out += backbeat(53, 72, vel=0.78)
    out.append((bar(61), 0.4, CRASH, 0.72))
    out += tom_fill(60, 0.78)
    out += tom_fill(68, 0.78)
    out += tom_fill(72, 0.82)

    # the drums stop on the final downbeat and leave the pad ringing
    out.append((bar(73), 0.4, BD, 0.85))
    out.append((bar(73), 0.4, CRASH, 0.7))
    return out


# Tracks ----------------------------------------------------------------------

# vol: [(beat, multiplier), ...] - linear VOLENV2 automation over gain_db
# macro_env: {macro_index: [(beat, value), ...]} - linear PARMENV automation

def _db(x):
    return 10.0 ** (x / 20.0)


TRACKS = [
    {
        "name": "LinnDrum", "script": "linndrum.py", "gain_db": -7.0,
        "pan": 0.0, "notes": drum_notes(),
        "macros": {},
        "vol": [(bar(13), 0.7), (bar(21), 1.0), (bar(45), 0.8),
                (bar(49), 1.0), (bar(53), 1.08), (bar(73), 1.0)],
        "macro_env": {},
    },
    {
        "name": "Moog Bass", "script": "minimoog.py", "gain_db": -8.0,
        "pan": 0.0, "notes": bass_notes(),
        # Glide (macro 4) stays at zero: this bass restates the root on
        # every eighth, and any portamento at all smears the drive.
        # Osc2/Osc3 sit about six cents either side of the root: enough for
        # the Model D's thickness, not enough to blur the pitch centre.
        # Noise Mix (7) off - the Model D mixes noise into the voice, and an
        # unset 0.5 put hiss under every bass note.
        "macros": {0: 0.7, 1: 0.35, 2: 0.35, 3: 0.55, 4: 0.0, 5: 0.62,
                   6: 0.4, 7: 0.0, 8: 0.0, 9: 0.35, 10: 0.6, 11: 0.15,
                   12: 0.05, 13: 0.35, 14: 0.3, 15: 0.3},
        "vol": [(bar(21), 0.9), (bar(29), 1.0), (bar(53), 1.08),
                (bar(72), 1.0)],
        "macro_env": {
            # Four-bar cutoff waves that open a little further each
            # section - the one gesture the Minimoog is really for.
            1: [(bar(21), 0.28), (bar(25), 0.42), (bar(29), 0.34),
                (bar(33), 0.5), (bar(37), 0.4), (bar(41), 0.58),
                (bar(44), 0.64), (bar(49), 0.36), (bar(52), 0.6),
                (bar(53), 0.46), (bar(57), 0.66), (bar(61), 0.54),
                (bar(65), 0.72), (bar(69), 0.6), (bar(72), 0.4)],
            15: [(bar(21), 0.2), (bar(37), 0.3), (bar(53), 0.42)],
        },
    },
    {
        "name": "Taurus Sub", "script": "taurus.py", "gain_db": -11.0,
        "pan": 0.0, "notes": sub_notes(),
        # Osc B Detune (1) and Beat Freq (6) stay low deliberately.  The
        # Taurus beats its two oscillators against each other, and at a
        # 55 Hz root even a 1 Hz beat is a third of a semitone - this is a
        # pedal, so it wants a slow shimmer, not an audible interval.
        "macros": {0: 0.6, 1: 0.15, 2: 0.1, 3: 0.25, 4: 0.3, 5: 0.3,
                   6: 0.1, 7: 0.2, 8: 0.5, 9: 0.85, 10: 0.4},
        "vol": [(bar(5), 0.7), (bar(13), 0.95), (bar(45), 1.0),
                (bar(53), 0.85), (bar(73), 0.8)],
        "macro_env": {3: [(bar(5), 0.18), (bar(17), 0.3), (bar(45), 0.26),
                          (bar(53), 0.32), (bar(73), 0.2)]},
    },
    {
        "name": "Juno Pad", "script": "juno106.py", "gain_db": -6.0,
        "pan": 0.0, "notes": pad_notes(),
        # Noise Level (4) off: the Juno's noise source is mixed per voice, so
        # an unset 0.5 put four noise oscillators under every pad chord.
        # HPF (7) stays low so the sub-oscillator keeps its weight, and the
        # LFO (9) is slow - it is wired to cutoff with a fixed depth here.
        "macros": {0: 0.7, 1: 0.42, 2: 0.22, 3: 0.4, 4: 0.0, 5: 0.72,
                   6: 0.3, 7: 0.1, 8: 0.35, 9: 0.2, 10: 0.35, 11: 0.35,
                   12: 0.5, 13: 0.8, 14: 0.55, 15: 0.4},
        "vol": [(bar(1), 0.55), (bar(9), 0.85), (bar(21), 0.8),
                (bar(45), 0.95), (bar(53), 0.85), (bar(73), 0.9),
                (bar(76, 4.0), 0.7)],
        "macro_env": {
            # The intro is one long filter sunrise; it re-opens for the
            # lift and closes again over the ritard.
            1: [(bar(1), 0.14), (bar(13), 0.4), (bar(21), 0.46),
                (bar(45), 0.34), (bar(53), 0.5), (bar(61), 0.58),
                (bar(69), 0.5), (bar(76), 0.24)],
        },
    },
    {
        "name": "SH-101 Arp", "script": "sh101.py", "gain_db": -6.0,
        "pan": -0.22, "notes": arp_notes(),
        "macros": {0: 0.6, 1: 0.4, 2: 0.4, 3: 0.4, 4: 0.5, 5: 0.6, 6: 0.7},
        "vol": [(bar(9), 0.5), (bar(17), 0.8), (bar(21), 0.9),
                (bar(45), 0.5), (bar(49), 1.0), (bar(53), 1.0),
                (bar(72), 0.85)],
        "macro_env": {
            # Two long cutoff builds: into B, and out of the breakdown.
            3: [(bar(9), 0.2), (bar(20), 0.5), (bar(21), 0.38),
                (bar(44), 0.68), (bar(47), 0.24), (bar(52), 0.8),
                (bar(53), 0.5), (bar(68), 0.74), (bar(72), 0.45)],
            4: [(bar(9), 0.4), (bar(44), 0.6), (bar(53), 0.52)],
        },
    },
    {
        "name": "Solina", "script": "solina.py", "gain_db": -1.5,
        "pan": 0.18, "notes": strings_notes(),
        "macros": {0: 0.6, 1: 0.6, 2: 0.5, 3: 0.4, 4: 0.8, 5: 0.35,
                   6: 0.5, 7: 0.4},
        "vol": [(bar(37), 0.75), (bar(53), 1.0), (bar(61), 1.1),
                (bar(69), 0.9), (bar(73), 0.7)],
        "macro_env": {7: [(bar(37), 0.3), (bar(53), 0.5), (bar(61), 0.62)]},
    },
    {
        "name": "OB-Xa Stabs", "script": "obxa.py", "gain_db": -8.0,
        "pan": 0.24, "notes": stab_notes(),
        "macros": {0: 0.6, 1: 0.45, 2: 0.5, 3: 0.3, 4: 0.55, 5: 0.15,
                   6: 0.4, 7: 0.05, 8: 0.5, 9: 0.3},
        "vol": [(bar(37), 0.8), (bar(53), 1.05), (bar(69), 0.9)],
        "macro_env": {2: [(bar(37), 0.42), (bar(53), 0.58), (bar(61), 0.66),
                          (bar(72), 0.45)]},
    },
    {
        "name": "Prophet Lead", "script": "prophet5.py", "gain_db": -7.5,
        "pan": 0.06, "notes": lead_notes(),
        # Poly Mod (4) and Sync (6) pinned off. Poly Mod multiplies osc B's
        # frequency, so an unset 0.5 detuned it by most of a semitone and
        # made the lead sound sour no matter what Osc2 Detune said.
        "macros": {0: 0.7, 1: 0.5, 2: 0.3, 3: 0.5, 4: 0.0, 5: 0.62,
                   6: 0.0, 7: 0.35, 8: 0.05, 9: 0.4, 10: 0.7, 11: 0.05,
                   12: 0.4, 13: 0.5, 14: 0.35, 15: 0.12},
        "vol": [(bar(29), 0.85), (bar(37), 0.95), (bar(53), 1.1),
                (bar(61), 1.1), (bar(69), 0.9), (bar(73), 0.75)],
        "macro_env": {
            1: [(bar(29), 0.42), (bar(36), 0.55), (bar(37), 0.5),
                (bar(44), 0.62), (bar(53), 0.6), (bar(61), 0.7),
                (bar(69), 0.5), (bar(73), 0.36)],
            15: [(bar(29), 0.1), (bar(53), 0.16), (bar(69), 0.22)],
        },
    },
    {
        "name": "DX7 Bells", "script": "dx7.py", "gain_db": -2.0,
        "pan": -0.12, "notes": bell_notes(),
        # Vibrato Depth (12) is pinned off. Unset macros arrive at 0.5, and
        # half-depth DX7 vibrato is ~12 cents of wobble - the last thing a
        # bell motif stating the theme should have.
        # Mod Ratio (2) is quantised to whole numbers - an unset 0.5 put the
        # modulator on the 6th harmonic, which is where the clang came from.
        # Ratio 3 with less FM, less brightness and no tremolo gives a tine
        # that states the motif instead of fighting it. Vibrato (12) stays
        # off; Tremolo Depth (11) is ring modulation here, so off as well.
        "macros": {0: 0.55, 1: 0.25, 2: 0.2, 3: 0.1, 4: 0.45, 5: 0.25,
                   6: 0.15, 7: 0.7, 8: 0.3, 9: 0.05, 10: 0.35, 11: 0.0,
                   12: 0.0, 13: 0.4, 14: 0.3, 15: 0.5},
        "vol": [(bar(3), 0.8), (bar(45), 1.0), (bar(57), 0.7),
                (bar(73), 1.0)],
        "macro_env": {10: [(bar(3), 0.45), (bar(45), 0.6), (bar(73), 0.5)]},
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
    ("A Nightfall", bar(1), bar(21)),
    ("B Neon Mile", bar(21), bar(53)),
    ("C Afterburn", bar(53), bar(77)),
]
