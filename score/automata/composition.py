"""Automata - a five-movement electronic suite for the MicroPython VST3.

Twenty-four tracks, twenty-four sidecar instances, no third-party sounds.
Where Perihelion was a film cue, Automata is a machine coming to life:

  I    Dawn Protocol    bars 1-20   4/4 @84    A minor. Air, glass, FM
                                    bells, a choir hum, a heartbeat kick.
  II   Assembly Line    bars 1-32   7/8 @112   The machine starts moving:
                                    a hypnotic 2+2+3 polysynth ostinato,
                                    Reese bass, glitch percussion.
  III  Ignition         bars 1-32   4/4 @126   Four on the floor. The 303
                                    wakes up, sidechained pads pump
                                    (phase-locked via vstaudio.transport),
                                    a two-minute build to the drop.
  IV   Overdrive        bars 1-48   4/4 @128   B minor anthem: supersaw
                                    theme over the full kit, organ floor,
                                    brass stabs, then a deconstruction.
  V    Afterimage       bars 1-16   4/4 @64..48  D major. Felt keys quote
                                    the Perihelion theme; the final chord
                                    dies as a tape stop.

Groove is real: swing on the hats, humanized shakers, velocity accents,
ghost notes, fills. The acid line slides between overlapping notes the
way a 303 ties steps. All echoes and the sidechain pump sync themselves
to the host tempo through the plug-in's transport API.
"""

TITLE = "Automata"
SAMPLE_RATE = 48000
MASTER_GAIN_DB = -2.5
ACTIVE_LIMIT = None
CLIMAX_SECTION = "IV Overdrive"
TAIL_SECONDS = 12.0

# Movement starts, in quarter-note beats.
M1, M2, M3, M4, M5 = 0.0, 80.0, 192.0, 320.0, 512.0
TOTAL_BEATS = 576.0

# (beat, bpm, ts_num, ts_den) - piecewise constant, square points.
TEMPO_MAP = [
    (M1, 84.0, 4, 4),
    (M2, 112.0, 7, 8),
    (M3, 126.0, 4, 4),
    (M4, 128.0, 4, 4),
    (M5, 64.0, 4, 4),
    (568.0, 56.0, 4, 4),
    (572.0, 48.0, 4, 4),
]

SECTIONS = [
    ("I Dawn", M1, M2),
    ("II Assembly", M2, M3),
    ("III Ignition", M3, M4),
    ("IV Overdrive", M4, M5),
    ("V Afterimage", M5, TOTAL_BEATS),
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


def b1(bar, off=0.0):
    return M1 + (bar - 1) * 4.0 + off


def b2(bar, off=0.0):
    """7/8 bars: 3.5 quarter-note beats per bar; off is in beats."""
    return M2 + (bar - 1) * 3.5 + off


def b3(bar, off=0.0):
    return M3 + (bar - 1) * 4.0 + off


def b4(bar, off=0.0):
    return M4 + (bar - 1) * 4.0 + off


def b5(bar, off=0.0):
    return M5 + (bar - 1) * 4.0 + off


# Pitch names ----------------------------------------------------------------

_SEMIS = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4,
          "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9,
          "A#": 10, "Bb": 10, "B": 11}


def P(name):
    """"A2" -> 45 (C4 = 60)."""
    letter = name[:-1]
    octave = int(name[-1])
    return 12 * (octave + 1) + _SEMIS[letter]


KICK, SNARE, CLAP = 36, 38, 39
HAT_C, HAT_O = 42, 46
TOM_L, TOM_M, TOM_H = 43, 47, 50


def hum(seed, i, amount=0.007):
    """Deterministic humanization jitter in beats."""
    h = ((seed * 1103515245 + i * 12345) & 0xFFFF) / 65535.0
    return (h - 0.5) * 2.0 * amount


# =============================================================================
# Percussion
# =============================================================================

def kick_notes():
    out = []
    # I: heartbeat, bars 15-20 (lub-dub)
    for bar in range(15, 21):
        out.append((b1(bar, 0.0), 0.3, KICK, 0.5))
        out.append((b1(bar, 0.65), 0.3, KICK, 0.32))
    # II: 7/8 kick on the 2+2+3 anchors (eighths 0 and 4), from bar 9
    for bar in range(9, 33):
        out.append((b2(bar, 0.0), 0.3, KICK, 0.78))
        out.append((b2(bar, 2.0), 0.3, KICK, 0.66))
        if bar % 4 == 3:
            out.append((b2(bar, 1.0), 0.3, KICK, 0.5))
    # III: four on the floor (gap in the last half of bar 32)
    for bar in range(1, 33):
        for q in range(4):
            if bar == 32 and q >= 3:
                continue
            out.append((b3(bar, q), 0.3, KICK, 0.85 + (0.05 if q == 0 else 0)))
    # IV: full weight; breakdown bars 17-24 halves; out-bars keep driving
    for bar in range(1, 49):
        beats = (0, 2) if 17 <= bar <= 24 else (0, 1, 2, 3)
        for q in beats:
            if bar == 48 and q >= 3:
                continue
            out.append((b4(bar, q), 0.3, KICK, 0.9 + (0.05 if q == 0 else 0)))
    # V: heartbeat returns, fading
    for i, bar in enumerate(range(9, 15)):
        vel = 0.42 - 0.05 * i
        out.append((b5(bar, 0.0), 0.3, KICK, max(0.12, vel)))
        out.append((b5(bar, 0.65), 0.3, KICK, max(0.08, vel - 0.14)))
    return out


def snare_notes():
    out = []
    # II: the 7/8 backbeat lands on eighth 2, ghost on eighth 6
    for bar in range(13, 33):
        out.append((b2(bar, 1.0), 0.15, SNARE, 0.55))
        if bar % 2 == 0:
            out.append((b2(bar, 3.0), 0.12, SNARE, 0.22))
    # III: backbeat from bar 9, ghosts; the build stacks eighths then a roll
    for bar in range(9, 25):
        out.append((b3(bar, 1.0), 0.15, SNARE, 0.8))
        out.append((b3(bar, 3.0), 0.15, SNARE, 0.82))
        if bar % 2 == 0:
            out.append((b3(bar, 3.75), 0.1, SNARE, 0.3))
    for bar in range(25, 29):
        for e in range(8):
            out.append((b3(bar, e * 0.5), 0.12, SNARE,
                        0.5 + 0.02 * e if e % 2 else 0.62))
    for bar in range(29, 32):
        for s in range(16):
            out.append((b3(bar, s * 0.25), 0.1, SNARE,
                        0.5 + 0.15 * (bar - 29) + 0.012 * s))
    for s in range(14):
        out.append((b3(32, s * 0.25), 0.1, SNARE, 0.7 + 0.02 * s))
    # IV: backbeat everywhere the kick is full; roll into V at 45-48
    for bar in range(1, 49):
        if 17 <= bar <= 24 or bar >= 45:
            continue
        out.append((b4(bar, 1.0), 0.15, SNARE, 0.88))
        out.append((b4(bar, 3.0), 0.15, SNARE, 0.9))
        if bar % 4 == 0:
            out.append((b4(bar, 3.5), 0.12, SNARE, 0.55))
            out.append((b4(bar, 3.75), 0.12, SNARE, 0.65))
    for bar in range(45, 48):
        for e in range(8):
            out.append((b4(bar, e * 0.5), 0.12, SNARE, 0.45 + 0.06 * (bar - 45)))
    for s in range(14):
        out.append((b4(48, s * 0.25), 0.1, SNARE, 0.62 + 0.025 * s))
    return out


def hats_notes():
    out = []
    # II: sparse closed offbeats from bar 17, open on the long group
    for bar in range(17, 33):
        for e in (1, 3, 5):
            out.append((b2(bar, e * 0.5) + hum(11, bar * 8 + e), 0.1,
                        HAT_C, 0.4 + (0.1 if e == 5 else 0.0)))
        if bar % 4 == 0:
            out.append((b2(bar, 3.0), 0.4, HAT_O, 0.5))
    # III: offbeat eighths, then swung sixteenths from bar 17
    for bar in range(1, 17):
        for q in range(4):
            out.append((b3(bar, q + 0.5), 0.1, HAT_C, 0.52))
        if bar >= 9 and bar % 2 == 0:
            out.append((b3(bar, 3.5), 0.4, HAT_O, 0.5))
    for bar in range(17, 33):
        for s in range(16):
            t = b3(bar, s * 0.25) + (0.03 if s % 2 == 1 else 0.0)
            vel = 0.55 if s % 4 == 2 else (0.32 if s % 2 == 1 else 0.42)
            out.append((t + hum(13, bar * 16 + s, 0.004), 0.1, HAT_C, vel))
    # IV: swung sixteenths, open hat on the and-of-four
    for bar in range(1, 49):
        if bar >= 45:
            continue
        dense = not (17 <= bar <= 24)
        steps = range(16) if dense else range(0, 16, 2)
        for s in steps:
            t = b4(bar, s * 0.25) + (0.03 if s % 2 == 1 else 0.0)
            vel = 0.6 if s % 4 == 2 else (0.34 if s % 2 == 1 else 0.45)
            out.append((t + hum(17, bar * 16 + s, 0.004), 0.1, HAT_C, vel))
        if dense and bar % 2 == 0:
            out.append((b4(bar, 3.5), 0.45, HAT_O, 0.55))
    return out


def claps_notes():
    out = []
    for bar in range(5, 33):
        out.append((b3(bar, 1.0), 0.3, CLAP, 0.6))
        out.append((b3(bar, 3.0), 0.3, CLAP, 0.62))
    for bar in range(25, 41):
        out.append((b4(bar, 1.0), 0.3, CLAP, 0.7))
        out.append((b4(bar, 3.0), 0.3, CLAP, 0.72))
    return out


def toms_notes():
    out = []
    # II bar 32: descending fill over the last five eighths
    fill = [(1.0, TOM_H), (1.5, TOM_H), (2.0, TOM_M), (2.5, TOM_M),
            (3.0, TOM_L)]
    for off, pitch in fill:
        out.append((b2(32, off), 0.3, pitch, 0.7))
    # III: accents in the second half
    for bar in (20, 24, 28):
        out.append((b3(bar, 3.5), 0.3, TOM_M, 0.6))
        out.append((b3(bar, 3.75), 0.3, TOM_L, 0.65))
    # IV: breakdown groove and the big fills
    for bar in range(17, 25):
        out.append((b4(bar, 2.5), 0.25, TOM_L, 0.55))
        out.append((b4(bar, 3.5), 0.25, TOM_M, 0.5))
    for bar, scale in ((8, 0.8), (16, 0.9), (40, 1.0)):
        seq = [(3.0, TOM_H), (3.25, TOM_H), (3.5, TOM_M), (3.75, TOM_L)]
        for off, pitch in seq:
            out.append((b4(bar, off), 0.22, pitch, 0.55 * scale + 0.2))
    return out


def shaker_notes():
    out = []
    # II: every eighth, 2+2+3 accents
    for bar in range(5, 33):
        for e in range(7):
            vel = 0.6 if e in (0, 2, 4) else 0.28
            out.append((b2(bar, e * 0.5) + hum(23, bar * 8 + e), 0.1,
                        70, vel))
    # IV: sixteenths through the peak section
    for bar in range(25, 41):
        for s in range(16):
            vel = 0.5 if s % 4 == 0 else 0.24
            out.append((b4(bar, s * 0.25) + hum(29, bar * 16 + s), 0.08,
                        70, vel))
    return out


def glitch_notes():
    out = []
    # II: ticks and crushes scattered on the odd eighths
    for bar in range(1, 33):
        if bar % 2 == 1:
            out.append((b2(bar, 0.5), 0.1, 65, 0.5))
        if bar % 4 == 2:
            out.append((b2(bar, 2.5), 0.15, 50, 0.6))
        if bar in (9, 17, 25):
            out.append((b2(bar, 0.0), 0.4, 36, 0.7))
    # III: fills at phrase ends
    for bar in (8, 12, 16, 20, 24):
        out.append((b3(bar, 3.5), 0.1, 65, 0.55))
        out.append((b3(bar, 3.75), 0.1, 50, 0.6))
    # IV: stutter accents through the peak
    for bar in range(25, 41):
        if bar % 2 == 1:
            out.append((b4(bar, 1.75), 0.1, 65, 0.5))
        if bar % 4 == 3:
            out.append((b4(bar, 3.5), 0.15, 36, 0.55))
    return out


def impact_notes():
    return [
        (b2(1), 3.0, P("A2"), 0.6),
        (b2(17), 3.0, P("A2"), 0.6),
        (b3(1), 3.5, P("A2"), 0.85),
        (b4(1), 3.5, P("B2"), 1.0),
        (b4(25), 3.5, P("B2"), 0.9),
        (b5(1), 3.0, P("D3"), 0.5),
    ]


# =============================================================================
# Bass
# =============================================================================

def acid_pattern(base, start_bar, bars, bfun, energy):
    """A rolling two-bar acid loop; slides are notes that overlap.

    base is the root MIDI note (A1 or B1). energy 0..1 scales velocity.
    """
    R, O, b7, b3_, b5f = base, base + 12, base + 10, base + 3, base + 6
    # (sixteenth, pitch, vel, slide_from_prev)
    loop = [
        (0, R, 0.95, False), (2, R, 0.5, False), (3, O, 0.7, True),
        (5, R, 0.55, False), (7, b7, 0.75, True), (8, R, 0.9, False),
        (10, R, 0.45, False), (12, b3_ + 12, 0.8, True), (14, O, 0.6, True),
        (16, R, 0.95, False), (18, R, 0.5, False), (19, O, 0.72, True),
        (21, b5f, 0.78, True), (23, R, 0.55, False), (24, R, 0.88, False),
        (26, b7, 0.6, False), (28, O, 0.85, True), (30, b7, 0.5, True),
    ]
    out = []
    for two_bar in range(bars // 2):
        bar = start_bar + two_bar * 2
        for i, (s, pitch, vel, slide) in enumerate(loop):
            t = bfun(bar, s * 0.25)
            dur = 0.21
            if i + 1 < len(loop) and loop[i + 1][3]:
                dur = (loop[i + 1][0] - s) * 0.25 + 0.06
            out.append((t, dur, pitch, min(1.0, vel * (0.7 + 0.3 * energy))))
    return out


def acid_notes():
    out = []
    # III: sparse entry, then the full line
    A1 = P("A1")
    intro = [(0, A1, 0.9), (3, A1 + 12, 0.6), (8, A1, 0.85), (14, A1 + 10, 0.6)]
    for bar in range(5, 9):
        for s, pitch, vel in intro:
            out.append((b3(bar, s * 0.25), 0.2, pitch, vel))
    out += acid_pattern(A1, 9, 24, b3, 0.75)
    # IV: transposed to B, driving the whole movement except the breakdown
    B1 = P("B1")
    out += acid_pattern(B1, 1, 16, b4, 0.9)
    out += acid_pattern(B1, 25, 16, b4, 1.0)
    # the deconstruction: the acid is what remains
    out += acid_pattern(B1, 41, 8, b4, 0.85)
    return out


def sub_bass_notes():
    out = []
    out.append((b1(9), b1(21) - b1(9) - 0.5, P("A1"), 0.55))
    # II: roots every two bars
    roots = [P("A1"), P("G1"), P("F1"), P("G1")] * 3
    for i, root in enumerate(roots):
        out.append((b2(9 + i * 2), 6.8, root, 0.6))
    # III: sustained roots under the pads (Am F C G)
    prog = [P("A1"), P("F1"), P("C2"), P("G1")]
    for cycle in range(4):
        for j, root in enumerate(prog):
            bar = 1 + cycle * 8 + j * 2
            out.append((b3(bar), 7.6, root, 0.65))
    # IV: pumping eighth roots under the drop (Bm G D A)
    prog4 = [P("B1"), P("G1"), P("D2"), P("A1")]
    for bar in range(1, 49):
        if 17 <= bar <= 24:
            root = prog4[(bar - 17) % 4]
            out.append((b4(bar), 3.8, root, 0.6))
            continue
        root = prog4[(bar - 1) % 4]
        for e in range(8):
            out.append((b4(bar, e * 0.5), 0.42, root, 0.6 + (0.1 if e == 0 else 0)))
    # V: D pedal
    out.append((b5(1), b5(15) - b5(1) - 0.5, P("D2"), 0.5))
    return out


def reese_notes():
    out = []
    roots = [P("A2"), P("G2"), P("F2"), P("G2")]
    for i in range(12):
        out.append((b2(5 + i * 2), 6.8, roots[i % 4], 0.62))
    return out


# =============================================================================
# Synths
# =============================================================================

OST = {
    "Am": ["A3", "C4", "E4", "G4", "A4", "G4", "E4"],
    "G":  ["G3", "B3", "D4", "G4", "A4", "G4", "D4"],
    "F":  ["F3", "A3", "C4", "E4", "F4", "E4", "C4"],
}


def polyseq_notes():
    chords = (["Am", "Am", "G", "G", "F", "F", "G", "G"] * 4)[:32]
    out = []
    for bar, chord in enumerate(chords, start=1):
        pattern = OST[chord]
        for e, name in enumerate(pattern):
            vel = 0.68 if e in (0, 2, 4) else 0.42
            vel += 0.06 * (bar // 8)
            out.append((b2(bar, e * 0.5) + hum(31, bar * 8 + e, 0.004),
                        0.4, P(name), min(1.0, vel)))
    return out


def pump_pad_notes():
    out = []
    # III: Am F C G, re-pressed each bar so the pump re-locks its phase
    voicings = [["A2", "E3", "C4"], ["F2", "C3", "A3"],
                ["C3", "G3", "E4"], ["G2", "D3", "B3"]]
    for bar in range(1, 33):
        chord = voicings[((bar - 1) // 2) % 4]
        for name in chord:
            out.append((b3(bar), 3.9, P(name), 0.55 + 0.006 * bar))
    # IV: Bm G D A
    voicings4 = [["B2", "F#3", "D4"], ["G2", "D3", "B3"],
                 ["D3", "A3", "F#4"], ["A2", "E3", "C#4"]]
    for bar in range(1, 41):
        chord = voicings4[(bar - 1) % 4]
        for name in chord:
            out.append((b4(bar), 3.9, P(name), 0.62))
    return out


def theme_bar_phrase(bfun, start_bar, shift, vel):
    """The eight-bar Automata anthem, written in B minor at shift=0."""
    seq = [
        (1, 0.0, 1.5, "B4"), (1, 1.5, 0.5, "C#5"), (1, 2.0, 2.0, "D5"),
        (2, 0.0, 2.5, "F#5"), (2, 2.5, 1.0, "E5"), (2, 3.5, 0.5, "D5"),
        (3, 0.0, 1.5, "A4"), (3, 1.5, 0.5, "B4"), (3, 2.0, 2.0, "D5"),
        (4, 0.0, 3.0, "C#5"), (4, 3.0, 1.0, "B4"),
        (5, 0.0, 1.5, "B4"), (5, 1.5, 0.5, "C#5"), (5, 2.0, 1.0, "D5"),
        (5, 3.0, 1.0, "E5"),
        (6, 0.0, 2.0, "F#5"), (6, 2.0, 1.0, "G5"), (6, 3.0, 1.0, "F#5"),
        (7, 0.0, 2.5, "A5"), (7, 2.5, 1.5, "F#5"),
        (8, 0.0, 2.0, "E5"), (8, 2.0, 2.0, "C#5"),
    ]
    return [(bfun(start_bar + bar - 1, off), dur, P(name) + shift, vel)
            for bar, off, dur, name in seq]


def supersaw_notes():
    out = []
    out += theme_bar_phrase(b4, 1, 0, 0.8)
    out += theme_bar_phrase(b4, 9, 0, 0.85)
    out += theme_bar_phrase(b4, 25, 0, 0.9)
    out += theme_bar_phrase(b4, 33, 0, 0.92)
    # held peak instead of the resolving tail
    out = out[:-2] + [(b4(40, 0.0), 4.0, P("F#5"), 0.95)]
    return out


def arp_fast_notes():
    out = []
    # III bars 17-32: two-octave broken minor chord in sixteenths
    steps = (0, 7, 12, 15, 19, 24, 19, 12)
    prog = {0: P("A2"), 1: P("F2"), 2: P("C3"), 3: P("G2")}
    for bar in range(17, 33):
        root = prog[((bar - 1) // 2) % 4]
        for s in range(16):
            out.append((b3(bar, s * 0.25), 0.2, root + steps[s % 8],
                        0.5 + (0.12 if s % 8 == 0 else 0.0)))
    # IV bars 25-40
    prog4 = {0: P("B2"), 1: P("G2"), 2: P("D3"), 3: P("A2")}
    for bar in range(25, 41):
        root = prog4[(bar - 1) % 4]
        for s in range(16):
            out.append((b4(bar, s * 0.25), 0.2, root + steps[s % 8],
                        0.52 + (0.12 if s % 8 == 0 else 0.0)))
    return out


def fm_bells_notes():
    out = [
        # I: the motif, stated twice, then a high answer
        (b1(3, 0.0), 1.5, P("A4"), 0.6), (b1(3, 1.5), 1.0, P("C5"), 0.5),
        (b1(3, 2.5), 1.5, P("B4"), 0.55), (b1(4, 0.0), 3.0, P("E5"), 0.6),
        (b1(7, 0.0), 1.5, P("E5"), 0.55), (b1(7, 1.5), 1.0, P("D5"), 0.5),
        (b1(7, 2.5), 1.0, P("C5"), 0.5), (b1(8, 0.0), 2.5, P("B4"), 0.5),
        (b1(12, 0.0), 1.5, P("A4"), 0.6), (b1(12, 1.5), 1.0, P("C5"), 0.52),
        (b1(12, 2.5), 1.0, P("B4"), 0.5), (b1(13, 0.0), 4.0, P("E5"), 0.6),
        (b1(17, 0.0), 2.0, P("A5"), 0.45), (b1(18, 0.0), 2.0, P("E5"), 0.4),
        # II: echoes over the ostinato
        (b2(13, 0.0), 1.5, P("A4"), 0.5), (b2(13, 1.5), 1.5, P("E5"), 0.45),
        (b2(21, 0.0), 1.5, P("C5"), 0.5), (b2(21, 1.5), 1.5, P("B4"), 0.45),
        # V: doubling the keys sparsely
        (b5(3, 0.0), 2.0, P("D5"), 0.4), (b5(4, 0.0), 3.0, P("A5"), 0.42),
        (b5(9, 0.0), 2.0, P("D6"), 0.35), (b5(11, 0.0), 2.5, P("A5"), 0.32),
        (b5(13, 0.0), 6.0, P("F#5"), 0.4),
    ]
    return out


def keys_notes():
    """Movement V: the Perihelion theme, quoted in D major."""
    phrase = [
        (3, 0.0, 2.0, "D4"), (3, 2.0, 1.0, "F#4"), (3, 3.0, 1.0, "G4"),
        (4, 0.0, 3.0, "A4"), (4, 3.0, 1.0, "G4"),
        (5, 0.0, 2.0, "F#4"), (5, 2.0, 1.0, "A4"), (5, 3.0, 1.0, "G4"),
        (6, 0.0, 2.5, "E4"), (6, 2.5, 1.5, "D4"),
        (9, 0.0, 2.0, "D5"), (9, 2.0, 1.0, "F#5"), (9, 3.0, 1.0, "G5"),
        (10, 0.0, 3.0, "A5"), (10, 3.0, 1.0, "G5"),
        (11, 0.0, 2.0, "F#5"), (11, 2.0, 1.0, "A5"), (11, 3.0, 1.0, "G5"),
        (12, 0.0, 2.5, "E5"), (12, 2.5, 1.5, "D5"),
    ]
    out = [(b5(bar, off), dur, P(name), 0.55 if bar < 9 else 0.45)
           for bar, off, dur, name in phrase]
    # left hand
    lh = [(1, "D3"), (2, "A2"), (3, "D3"), (4, "A2"), (5, "B2"), (6, "G2"),
          (7, "A2"), (8, "A2"), (9, "D3"), (10, "A2"), (11, "B2"),
          (12, "G2")]
    for bar, name in lh:
        out.append((b5(bar), 3.8, P(name), 0.4))
    out.append((b5(13), 8.0, P("D3"), 0.5))
    out.append((b5(13), 8.0, P("A3"), 0.45))
    out.append((b5(13), 8.0, P("F#4"), 0.45))
    return out


def organ_notes():
    out = []
    prog = [["B2", "F#3"], ["G2", "D3"], ["D3", "A3"], ["A2", "E3"]]
    for bar in range(1, 41):
        if 17 <= bar <= 20:
            continue
        chord = prog[(bar - 1) % 4]
        for name in chord:
            out.append((b4(bar), 3.9, P(name), 0.55))
    return out


def brass_stabs_notes():
    out = []
    chords = [["B3", "D4", "F#4"], ["G3", "B3", "D4"],
              ["D4", "F#4", "A4"], ["A3", "C#4", "E4"]]
    # IV breakdown: call-and-answer stabs
    for bar in range(17, 25):
        chord = chords[(bar - 1) % 4]
        for name in chord:
            out.append((b4(bar, 0.0), 0.6, P(name), 0.75))
            out.append((b4(bar, 1.5), 0.4, P(name), 0.6))
        if bar % 2 == 0:
            for name in chord:
                out.append((b4(bar, 2.5), 0.4, P(name), 0.68))
    # peak: downbeat punches
    for bar in range(25, 41):
        if bar % 2 == 1:
            chord = chords[(bar - 1) % 4]
            for name in chord:
                out.append((b4(bar, 0.0), 0.8, P(name), 0.8))
    return out


def strings_notes():
    out = []
    # II bars 17-32: long lines rising over the ostinato
    line = [("A4", 17), ("G4", 19), ("F4", 21), ("G4", 23),
            ("C5", 25), ("B4", 27), ("A4", 29), ("G4", 31)]
    for name, bar in line:
        out.append((b2(bar), 6.8, P(name), 0.5 + 0.01 * (bar - 17)))
    for extra, bar in (("E5", 29), ("D5", 31)):
        out.append((b2(bar), 6.8, P(extra), 0.45))
    # III bars 17-32: sustained color above the groove
    for bar, names in ((17, ["A4", "E5"]), (21, ["F4", "C5"]),
                       (25, ["C5", "G5"]), (29, ["B4", "E5"])):
        for name in names:
            out.append((b3(bar), 15.6, P(name), 0.5))
    # IV: countermelody over the peak
    counter = ["D5", "D5", "F#5", "E5", "B4", "B4", "D5", "C#5",
               "D5", "E5", "F#5", "G5", "F#5", "E5", "D5", "C#5"]
    for i, name in enumerate(counter):
        out.append((b4(25 + i), 3.9, P(name), 0.6))
    # V: suspensions
    out.append((b5(7), 8.0, P("A4"), 0.4))
    out.append((b5(11), 8.0, P("F#4"), 0.36))
    return out


def choir_notes():
    out = [
        # I: the hum
        (b1(9), 8.0, [P("A3"), P("C4"), P("E4")], 0.45),
        (b1(13), 8.0, [P("F3"), P("A3"), P("C4")], 0.45),
        (b1(17), 14.0, [P("A3"), P("C4"), P("E4")], 0.48),
        # V: the resolution
        (b5(1), 8.0, [P("D4"), P("F#4"), P("A4")], 0.5),
        (b5(3), 8.0, [P("A3"), P("C#4"), P("E4")], 0.45),
        (b5(5), 8.0, [P("B3"), P("D4"), P("F#4")], 0.48),
        (b5(7), 8.0, [P("G3"), P("B3"), P("D4")], 0.45),
        (b5(9), 8.0, [P("D4"), P("F#4"), P("A4")], 0.48),
        (b5(11), 8.0, [P("A3"), P("D4"), P("E4")], 0.42),
        (b5(13), 12.0, [P("D4"), P("F#4"), P("A4")], 0.52),
    ]
    flat = []
    for start, dur, pitches, vel in out:
        if isinstance(pitches, list):
            for p in pitches:
                flat.append((start, dur, p, vel))
        else:
            flat.append((start, dur, pitches, vel))
    return flat


def glass_notes():
    out = []
    dyads = [(2, ["A4", "E5"], 8), (5, ["G4", "D5"], 8), (8, ["A4", "E5"], 8),
             (11, ["F4", "C5"], 8), (14, ["A4", "E5"], 10)]
    for bar, names, dur in dyads:
        for name in names:
            out.append((b1(bar), dur, P(name), 0.48))
    for bar, names, dur in ((3, ["D5", "A5"], 8), (7, ["C#5", "A5"], 8),
                            (11, ["B4", "D5"], 6), (13, ["F#5", "A5"], 12)):
        for name in names:
            out.append((b5(bar), dur, P(name), 0.42))
    return out


def riser_notes():
    return [
        (b1(19), 8.0, P("A2"), 0.5),          # into II
        (b2(31), 7.0, P("A2"), 0.6),          # into III
        (b3(29), 15.5, P("A2"), 0.7),         # the big one into IV
        (b4(45), 15.0, P("B2"), 0.6),         # into V
        (b5(13), 14.0, P("D3"), 0.55),        # the tape-stop cluster
    ]


def texture_notes():
    return [
        (b1(1), b1(20) - b1(1) + 2.0, P("C4"), 0.5),
        (b5(1), b5(16) - b5(1) + 2.0, P("C4"), 0.45),
    ]


# =============================================================================
# Track table
# =============================================================================

TRACKS = [
    {"name": "Kick", "script": "kick.py", "gain_db": -5.0, "pan": 0.0,
     "notes": kick_notes(),
     "macros": {0: 0.45, 1: 0.55},
     "vol": [(M1, 0.85), (M2, 1.0), (M5, 0.9)],
     "macro_env": {1: [(M1, 0.06), (b1(20, 4.0), 0.06), (b2(1), 0.5),
                       (b4(48, 4.0), 0.5), (b5(1), 0.06)]}},
    {"name": "Snare", "script": "snare.py", "gain_db": -3.0, "pan": 0.02,
     "notes": snare_notes(),
     "macros": {0: 0.5, 1: 0.35},
     "vol": [(M2, 0.9), (M3, 1.0), (M4, 1.05)],
     "macro_env": {0: [(b3(1), 0.45), (b3(29), 0.68), (b4(1), 0.5),
                       (b4(45), 0.65)]}},
    {"name": "Hats", "script": "hats.py", "gain_db": -8.5, "pan": 0.12,
     "notes": hats_notes(),
     "macros": {0: 0.5},
     "vol": [(M2, 0.85), (M3, 1.0)],
     "macro_env": {0: [(b3(1), 0.4), (b3(29), 0.7), (b4(1), 0.55)]}},
    {"name": "Claps", "script": "claps.py", "gain_db": -7.0, "pan": -0.06,
     "notes": claps_notes(),
     "macros": {0: 0.5, 1: 0.6},
     "vol": [(M3, 0.9), (M4, 1.0)],
     "macro_env": {0: [(b3(5), 0.42), (b4(25), 0.6)]}},
    {"name": "Toms", "script": "toms.py", "gain_db": -7.0, "pan": 0.0,
     "notes": toms_notes(),
     "macros": {0: 0.55, 1: 0.5},
     "vol": [(M2, 1.0)],
     "macro_env": {1: [(M2, 0.35), (b4(17), 0.6), (b4(41), 0.4)]}},
    {"name": "Shaker", "script": "shaker.py", "gain_db": -11.0, "pan": -0.2,
     "notes": shaker_notes(),
     "macros": {0: 0.5},
     "vol": [(M2, 1.0)],
     "macro_env": {}},
    {"name": "Glitch", "script": "glitch.py", "gain_db": -13.0, "pan": 0.15,
     "notes": glitch_notes(),
     "macros": {0: 0.4},
     "vol": [(M2, 1.0)],
     "macro_env": {0: [(b2(1), 0.3), (b3(25), 0.6), (b4(1), 0.4)]}},
    {"name": "Impact", "script": "impact.py", "gain_db": -6.5, "pan": 0.0,
     "notes": impact_notes(),
     "macros": {0: 0.5, 1: 0.6},
     "vol": [(M2, 0.8), (M3, 0.95), (M4, 1.0), (M5, 0.7)],
     "macro_env": {}},
    {"name": "Acid", "script": "acid.py", "gain_db": -8.5, "pan": 0.0,
     "notes": acid_notes(),
     "macros": {0: 0.35, 1: 0.6, 2: 0.5, 3: 0.25},
     "vol": [(M3, 0.9), (M4, 1.0), (b4(41), 1.05)],
     "macro_env": {
         0: [(b3(5), 0.22), (b3(9), 0.35), (b3(13), 0.28), (b3(17), 0.5),
             (b3(21), 0.38), (b3(25), 0.62), (b3(29), 0.8), (b3(32), 0.88),
             (b4(1), 0.6), (b4(5), 0.75), (b4(9), 0.55), (b4(13), 0.8),
             (b4(17), 0.35), (b4(25), 0.7), (b4(29), 0.88), (b4(33), 0.6),
             (b4(37), 0.85), (b4(41), 0.5), (b4(44), 0.75), (b4(47), 0.3),
             (b4(48, 4.0), 0.2)],
         1: [(b3(5), 0.5), (b3(25), 0.68), (b4(1), 0.6), (b4(41), 0.75)],
         2: [(b3(5), 0.4), (b3(25), 0.6), (b4(1), 0.55), (b4(41), 0.7)]}},
    {"name": "Sub Bass", "script": "sub_bass.py", "gain_db": -6.5,
     "pan": 0.0, "notes": sub_bass_notes(),
     "macros": {0: 0.65},
     "vol": [(M1, 0.9), (M3, 1.0), (M5, 0.85)],
     "macro_env": {}},
    {"name": "Reese", "script": "reese.py", "gain_db": -10.5, "pan": 0.0,
     "notes": reese_notes(),
     "macros": {0: 0.4, 1: 0.6},
     "vol": [(M2, 0.95)],
     "macro_env": {0: [(b2(5), 0.3), (b2(17), 0.5), (b2(29), 0.62),
                       (b2(32, 3.5), 0.4)]}},
    {"name": "Supersaw", "script": "supersaw.py", "gain_db": -1.0,
     "pan": 0.0, "notes": supersaw_notes(),
     "macros": {0: 0.6, 1: 0.45, 2: 0.4},
     "vol": [(M4, 0.95), (b4(25), 1.05), (b4(40, 4.0), 1.0)],
     "macro_env": {0: [(b4(1), 0.55), (b4(9), 0.7), (b4(25), 0.8),
                       (b4(37), 0.9)]}},
    {"name": "Pump Pad", "script": "pump_pad.py", "gain_db": -8.0,
     "pan": 0.0, "notes": pump_pad_notes(),
     "macros": {0: 0.45, 1: 0.75, 2: 0.5},
     "vol": [(M3, 0.85), (b3(17), 1.0), (M4, 1.0), (b4(40, 4.0), 0.9)],
     "macro_env": {
         0: [(b3(1), 0.32), (b3(17), 0.5), (b3(29), 0.66), (b4(1), 0.55),
             (b4(25), 0.68), (b4(40, 4.0), 0.45)],
         1: [(b3(1), 0.6), (b3(25), 0.8), (b4(1), 0.85), (b4(17), 0.5),
             (b4(25), 0.85)]}},
    {"name": "Polyseq", "script": "polyseq.py", "gain_db": -6.0,
     "pan": 0.0, "notes": polyseq_notes(),
     "macros": {0: 0.35, 1: 0.5, 2: 0.55},
     "vol": [(M2, 0.9), (b2(17), 1.0), (b2(32, 3.5), 0.95)],
     "macro_env": {0: [(b2(1), 0.25), (b2(9), 0.45), (b2(17), 0.35),
                       (b2(25), 0.6), (b2(31), 0.75), (b2(32, 3.5), 0.5)],
                   1: [(b2(1), 0.45), (b2(25), 0.62)]}},
    {"name": "Arp", "script": "arp_fast.py", "gain_db": -10.0, "pan": -0.1,
     "notes": arp_fast_notes(),
     "macros": {0: 0.4, 1: 0.5},
     "vol": [(M3, 0.85), (M4, 1.0)],
     "macro_env": {0: [(b3(17), 0.3), (b3(29), 0.6), (b3(32, 4.0), 0.75),
                       (b4(25), 0.5), (b4(37), 0.72)]}},
    {"name": "FM Bells", "script": "fm_bells.py", "gain_db": -9.5,
     "pan": 0.2, "notes": fm_bells_notes(),
     "macros": {0: 0.45, 1: 0.6},
     "vol": [(M1, 0.95), (M2, 0.85), (M5, 1.0)],
     "macro_env": {1: [(M1, 0.55), (M2, 0.4), (M5, 0.7)]}},
    {"name": "Keys", "script": "keys.py", "gain_db": -7.5, "pan": -0.05,
     "notes": keys_notes(),
     "macros": {0: 0.55, 1: 0.5},
     "vol": [(M5, 1.0), (b5(13), 0.95), (b5(16, 4.0), 0.7)],
     "macro_env": {0: [(b5(1), 0.55), (b5(9), 0.62), (b5(13), 0.4)]}},
    {"name": "Organ", "script": "organ.py", "gain_db": -10.5, "pan": 0.05,
     "notes": organ_notes(),
     "macros": {0: 0.45, 1: 0.4},
     "vol": [(M4, 0.9), (b4(25), 1.0)],
     "macro_env": {0: [(b4(1), 0.4), (b4(25), 0.6), (b4(40, 4.0), 0.4)]}},
    {"name": "Brass", "script": "brass_stabs.py", "gain_db": -7.5,
     "pan": 0.18, "notes": brass_stabs_notes(),
     "macros": {0: 0.55, 1: 0.35},
     "vol": [(M4, 0.95), (b4(25), 1.05)],
     "macro_env": {0: [(b4(17), 0.48), (b4(25), 0.68), (b4(40), 0.75)]}},
    {"name": "Strings", "script": "strings.py", "gain_db": -6.5,
     "pan": -0.15, "notes": strings_notes(),
     "macros": {0: 0.45, 1: 0.4},
     "vol": [(M2, 0.85), (M3, 0.9), (b4(25), 1.0), (M5, 0.8)],
     "macro_env": {0: [(b2(17), 0.35), (b3(17), 0.5), (b4(25), 0.65),
                       (M5, 0.3)]}},
    {"name": "Choir", "script": "choir.py", "gain_db": -7.0, "pan": 0.0,
     "notes": choir_notes(),
     "macros": {0: 0.45, 1: 0.6},
     "vol": [(M1, 0.9), (M5, 1.0), (b5(16, 4.0), 0.75)],
     "macro_env": {0: [(b5(1), 0.4), (b5(13), 0.6)]}},
    {"name": "Glass", "script": "glass.py", "gain_db": -12.0, "pan": 0.1,
     "notes": glass_notes(),
     "macros": {0: 0.35, 1: 0.6},
     "vol": [(M1, 0.9), (M5, 1.0)],
     "macro_env": {0: [(b1(2), 0.25), (b1(16), 0.5), (b5(3), 0.35),
                       (b5(13), 0.6)]}},
    {"name": "Riser", "script": "riser.py", "gain_db": -10.0, "pan": 0.0,
     "notes": riser_notes(),
     "macros": {0: 0.0, 1: 0.5, 2: 0.5, 3: 0.0},
     "vol": [(M1, 0.8), (M3, 1.0), (b5(13), 0.9)],
     "macro_env": {
         0: [(b1(19), 0.0), (b1(20, 4.0), 0.5), (b2(1), 0.0),
             (b2(31), 0.0), (b2(32, 3.5), 0.85), (b3(1), 0.0),
             (b3(29), 0.0), (b3(32, 4.0), 1.0), (b4(1), 0.0),
             (b4(45), 0.0), (b4(48, 4.0), 0.9), (b5(1), 0.0)],
         1: [(b1(19), 0.4), (b3(1), 0.55), (b3(32), 0.85), (b4(1), 0.5)],
         3: [(b5(13), 0.0), (b5(14, 2.0), 0.0), (b5(16, 4.0), 1.0)]}},
    {"name": "Texture", "script": "texture.py", "gain_db": -17.0,
     "pan": 0.1, "notes": texture_notes(),
     "macros": {0: 0.5, 1: 0.7},
     "vol": [(M1, 1.0)],
     "macro_env": {0: [(b1(1), 0.35), (b1(20), 0.6), (b5(1), 0.4),
                       (b5(16), 0.3)]}},
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
        p0, m0 = points[i]
        p1, m1 = points[i + 1]
        if beat <= p1:
            f = (beat - p0) / (p1 - p0) if p1 > p0 else 1.0
            return base * (m0 + (m1 - m0) * f)
    return base * points[-1][1]


def macro_value(track, index, beat):
    env = track["macro_env"].get(index)
    if not env:
        return track["macros"].get(index, 0.5)
    if beat <= env[0][0]:
        return env[0][1]
    for i in range(len(env) - 1):
        p0, v0 = env[i]
        p1, v1 = env[i + 1]
        if beat <= p1:
            f = (beat - p0) / (p1 - p0) if p1 > p0 else 1.0
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
