"""Velvet Circuit - a retro-future jazz/prog main title.

This is the first soundtrack piece built directly from the shared hardware
library and the first with real MicroPython Effect inserts.  It deliberately
turns away from Perihelion's orchestral film language and Automata's EDM arc:
an imaginary 1978 crime series discovered on a satellite in 2049.

The signature is a clipped F-minor horn line over a 5/4 pocket.  The middle
opens into an Ab-major 6/8 love theme, a 7/8 rooftop chase changes the camera
angle, and the final title reprise puts all three melodic identities in
counterpoint.  The last credits cadence resolves not to a plain tonic but to
F minor/major ambiguity (F-C-Ab-A-D-G): the mystery remains open next week.

All instruments resolve from ../../lib/instruments.  Effect scripts below are
only racks: every processor they instantiate is imported from lib/effects.
"""

TITLE = "Velvet_Circuit"
SAMPLE_RATE = 48000
MASTER_GAIN_DB = -1.5
ACTIVE_LIMIT = None
CLIMAX_SECTION = "VI Final Broadcast"
TAIL_SECONDS = 14.0
INSTRUMENTS_DIR = "../../lib/instruments"

# Quarter-note beat locations.  The first three sections share 5/4 at 126;
# later cameras move through 6/8, 7/8, 5/4, and a relaxed 4/4 credits roll.
M1, M2, M3, M4, M5, M6 = 0.0, 40.0, 120.0, 240.0, 312.0, 424.0
M7 = 504.0
TOTAL_BEATS = 536.0

TEMPO_MAP = [
    (M1, 126.0, 5, 4),
    (M4, 92.0, 6, 8),
    (M5, 138.0, 7, 8),
    (M6, 126.0, 5, 4),
    (M7, 104.0, 4, 4),
    (528.0, 90.0, 4, 4),
    (532.0, 74.0, 4, 4),
]

SECTIONS = [
    ("I Cold Open", M1, M2),
    ("II Main Title", M2, M3),
    ("III Split Screen", M3, M4),
    ("IV Blue Hour", M4, M5),
    ("V Rooftop Chase", M5, M6),
    ("VI Final Broadcast", M6, M7),
    ("VII End Credits", M7, TOTAL_BEATS),
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


def fbar(bar, off=0.0):
    """The opening 48 five-beat bars."""
    return M1 + (bar - 1) * 5.0 + off


def bluebar(bar, off=0.0):
    """Six eighths = three quarter-note beats."""
    return M4 + (bar - 1) * 3.0 + off


def chasebar(bar, off=0.0):
    """Seven eighths = three and a half quarter-note beats."""
    return M5 + (bar - 1) * 3.5 + off


def rbar(bar, off=0.0):
    return M6 + (bar - 1) * 5.0 + off


def endbar(bar, off=0.0):
    return M7 + (bar - 1) * 4.0 + off


_SEMITONES = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
    "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8,
    "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11,
}


def P(name):
    return 12 * (int(name[-1]) + 1) + _SEMITONES[name[:-1]]


def human(seed, index, amount=0.008):
    value = ((seed * 1103515245 + index * 12345) & 0xFFFF) / 65535.0
    return (value - 0.5) * 2.0 * amount


def chord(out, start, duration, names, velocity, roll=0.0):
    for index, name in enumerate(names):
        delay = roll * index
        out.append((start + delay, max(0.05, duration - delay), P(name),
                    max(0.05, min(1.0, velocity - index * 0.012))))


# Harmony --------------------------------------------------------------------

FIVE_CHORDS = [
    ("F1", ("F2", "C3", "Eb3", "Ab3", "G4")),       # Fm9
    ("Db2", ("Db2", "Ab2", "C3", "F3", "G3")),     # Dbmaj9#11
    ("Bb1", ("Bb1", "F2", "Ab2", "Db3", "C4")),     # Bbm9
    ("C2", ("C2", "G2", "Bb2", "Db3", "Eb3")),      # C7alt
]

BLUE_CHORDS = [
    ("Ab1", ("Ab2", "Eb3", "G3", "Bb3", "C4")),
    ("C2", ("C3", "G3", "Bb3", "Eb4")),
    ("Db2", ("Db3", "Ab3", "C4", "Eb4", "F4")),
    ("Eb2", ("Eb3", "Bb3", "Db4", "F4", "C5")),
    ("F2", ("F2", "C3", "Eb3", "Ab3", "G4")),
    ("Bb1", ("Bb2", "F3", "Ab3", "C4", "Db4")),
    ("Db2", ("Db3", "Ab3", "C4", "F4")),
    ("Eb2", ("Eb3", "G3", "Db4", "F4", "Bb4")),
]

CHASE_CHORDS = [
    ("E1", ("E2", "B2", "D3", "F#3", "G3")),
    ("D2", ("D2", "A2", "C3", "E3", "F#3")),
    ("C2", ("C2", "G2", "B2", "D3", "F#3")),
    ("B1", ("B1", "F#2", "A2", "C3", "D3")),
]


# Effect racks ---------------------------------------------------------------

def rack(name, imports, body):
    source = ("# mpvst-macro-labels: Rack 01 | Rack 02 | Rack 03 | Rack 04\n"
              "import vstaudio\n"
              "from effects import %s\n"
              "source = vstaudio.input()\n%s\n" % (imports, body))
    return {"name": name, "source": source, "macros": {}, "macro_env": {}}


FX_DRUMS = rack(
    "Desk Heat", "Saturation, Overdrive",
    "heat = Saturation(source, amount=0.16)\n"
    "desk = Overdrive(heat.output, drive=0.18, tone_hz=7200.0, mix=0.22)\n"
    "vstaudio.output(desk.output)")

FX_BASS = rack(
    "Valve Bass", "Saturation, Overdrive",
    "valve = Saturation(source, amount=0.22)\n"
    "edge = Overdrive(valve.output, drive=0.12, tone_hz=3200.0, mix=0.16)\n"
    "vstaudio.output(edge.output)")

FX_RHODES = rack(
    "Neon Suitcase", "Chorus, TapeDelay, Reverb",
    "chorus = Chorus(source, rate=0.34, depth_ms=4.0, voices=3, mix=0.28)\n"
    "echo = TapeDelay(chorus.output, time_ms=355.0, feedback=0.22, mix=0.14, wow=0.22, tone_hz=4300.0)\n"
    "room = Reverb(echo.output, preset='plate', mix=0.16)\n"
    "vstaudio.output(room.output)")

FX_CLAV = rack(
    "Chrome Clav", "Phaser, Overdrive",
    "phase = Phaser(source, rate=0.31, depth=0.72, stages=6, feedback=0.38, mix=0.42)\n"
    "amp = Overdrive(phase.output, drive=0.28, tone_hz=5600.0, mix=0.58)\n"
    "vstaudio.output(amp.output)")

FX_ORGAN = rack(
    "Rotary Room", "Chorus, Saturation, Reverb",
    # The shared B3 already models two-speed Leslie rotors.  A restrained
    # cabinet chorus here adds the mic/room spread without phase-cancelling
    # that instrument-level motion.
    "cab = Chorus(source, rate=0.72, depth_ms=3.2, voices=2, mix=0.18)\n"
    "heat = Saturation(cab.output, amount=0.13)\n"
    "room = Reverb(heat.output, preset='room', mix=0.13)\n"
    "vstaudio.output(room.output)")

FX_GUITAR = rack(
    "Midnight Combo", "Overdrive, SlapbackDelay, Reverb",
    "amp = Overdrive(source, drive=0.34, tone_hz=5100.0, mix=0.72)\n"
    "slap = SlapbackDelay(amp.output, time_ms=88.0, mix=0.16)\n"
    "spring = Reverb(slap.output, preset='spring', mix=0.15)\n"
    "vstaudio.output(spring.output)")

FX_WIND = rack(
    "Tenor Chamber", "SlapbackDelay, Reverb",
    "slap = SlapbackDelay(source, time_ms=112.0, mix=0.12)\n"
    "room = Reverb(slap.output, preset='chamber', mix=0.22)\n"
    "vstaudio.output(room.output)")

FX_BRASS = rack(
    "Brass Plate", "Saturation, Reverb",
    "tape = Saturation(source, amount=0.12)\n"
    "plate = Reverb(tape.output, preset='plate', mix=0.14)\n"
    "vstaudio.output(plate.output)")

FX_CS80 = rack(
    "Satellite Echo", "TapeDelay, Reverb",
    "echo = TapeDelay(source, time_ms=238.0, feedback=0.27, mix=0.18, wow=0.16, tone_hz=5200.0)\n"
    "hall = Reverb(echo.output, preset='hall', mix=0.18)\n"
    "vstaudio.output(hall.output)")

FX_STRINGS = rack(
    "Velvet Hall", "Reverb",
    "hall = Reverb(source, preset='hall', mix=0.24)\n"
    "vstaudio.output(hall.output)")

FX_TAPE = rack(
    "Ghost Projector", "Vibrato, Reverb",
    "flutter = Vibrato(source, rate=4.7, depth_semitones=0.06)\n"
    "room = Reverb(flutter.output, preset='chamber', mix=0.26)\n"
    "vstaudio.output(room.output)")


# Drums ----------------------------------------------------------------------

KICK, RIM, SNARE, CLAP = 36, 37, 38, 39
HAT_C, HAT_O, COWBELL, TAMBO, CABASA = 42, 46, 56, 54, 69
TOM_L, TOM_M, TOM_H = 43, 47, 50


def drum_notes():
    out = []
    # Cold open: rim/cabasa telegraph the 3+2 grouping before the kit arrives.
    for bar in range(1, 9):
        for off, pitch, vel in ((0.0, RIM, 0.34), (1.5, CABASA, 0.22),
                                (3.0, RIM, 0.28), (4.0, CABASA, 0.2)):
            out.append((fbar(bar, off), 0.10, pitch, vel + 0.025 * bar))
        if bar >= 5:
            out.append((fbar(bar), 0.16, KICK, 0.55 + 0.04 * (bar - 5)))
            out.append((fbar(bar, 3.0), 0.16, KICK, 0.42))
        if bar in (4, 8):
            out.append((fbar(bar, 4.5), 0.25, COWBELL, 0.45))

    # Main title and split-screen solos: a greasy 5/4 funk pocket.
    for bar in range(9, 49):
        phrase_end = bar in (16, 24, 32, 40, 48)
        kicks = (0.0, 1.5, 3.0, 4.25) if bar % 2 else (0.0, 1.75, 3.0, 4.0)
        for i, off in enumerate(kicks):
            out.append((fbar(bar, off), 0.15, KICK, 0.78 if i == 0 else 0.59))
        for off, vel in ((2.0, 0.76), (4.0, 0.82)):
            out.append((fbar(bar, off + human(3, bar * 4 + int(off))),
                        0.12, SNARE, vel))
        if bar >= 17:
            out.append((fbar(bar, 4.5), 0.13, CLAP, 0.34))
        for eighth in range(10):
            if phrase_end and eighth >= 8:
                continue
            off = eighth * 0.5 + human(5, bar * 10 + eighth, 0.01)
            pitch = HAT_O if eighth == 9 and bar % 4 == 0 else HAT_C
            vel = 0.43 if eighth % 2 == 0 else 0.28
            out.append((fbar(bar, off), 0.09 if pitch == HAT_C else 0.34,
                        pitch, vel))
        if phrase_end:
            for off, pitch, vel in ((4.0, TOM_H, 0.54), (4.25, TOM_M, 0.62),
                                    (4.5, TOM_L, 0.72), (4.75, SNARE, 0.68)):
                out.append((fbar(bar, off), 0.12, pitch, vel))

    # Blue Hour: feathered 6/8, rim clicks and cabasa instead of a backbeat.
    for bar in range(1, 25):
        out.append((bluebar(bar), 0.14, KICK, 0.43 if bar < 17 else 0.52))
        if bar % 2 == 0:
            out.append((bluebar(bar, 2.0), 0.14, KICK, 0.31))
        out.append((bluebar(bar, 1.5), 0.10, RIM, 0.38))
        for eighth in range(6):
            pitch = CABASA if eighth % 2 else HAT_C
            out.append((bluebar(bar, eighth * 0.5 + human(7, bar * 6 + eighth)),
                        0.08, pitch, 0.18 + (0.09 if eighth in (0, 3) else 0.0)))
        if bar in (8, 16, 24):
            out.append((bluebar(bar, 2.5), 0.20, TOM_M, 0.45))

    # Rooftop Chase: 7/8 articulated 2+2+3, with four-bar fill mutations.
    for bar in range(1, 33):
        for off, vel in ((0.0, 0.82), (1.0, 0.55), (2.0, 0.7)):
            out.append((chasebar(bar, off), 0.13, KICK, vel))
        out.append((chasebar(bar, 1.5), 0.11, SNARE, 0.76))
        out.append((chasebar(bar, 3.0), 0.11, SNARE, 0.82))
        for eighth in range(7):
            pitch = HAT_O if eighth == 6 and bar % 4 == 0 else HAT_C
            out.append((chasebar(bar, eighth * 0.5 + human(11, bar * 7 + eighth)),
                        0.08 if pitch == HAT_C else 0.28, pitch,
                        0.46 if eighth in (0, 2, 4) else 0.29))
        if bar % 8 == 0:
            for off, pitch in ((2.5, TOM_H), (2.75, TOM_M), (3.0, TOM_L),
                               (3.25, SNARE)):
                out.append((chasebar(bar, off), 0.10, pitch, 0.62))

    # Final title: familiar groove, denser tambourine and a hard final break.
    for bar in range(1, 17):
        for off, vel in ((0.0, 0.9), (1.5, 0.65), (3.0, 0.76), (4.25, 0.68)):
            if bar == 16 and off > 3.0:
                continue
            out.append((rbar(bar, off), 0.14, KICK, vel))
        for off in (2.0, 4.0):
            if not (bar == 16 and off == 4.0):
                out.append((rbar(bar, off), 0.11, SNARE, 0.88))
                out.append((rbar(bar, off + 0.03), 0.13, CLAP, 0.47))
        for eighth in range(10):
            if bar == 16 and eighth >= 7:
                continue
            out.append((rbar(bar, eighth * 0.5), 0.08, HAT_C,
                        0.5 if eighth % 2 == 0 else 0.31))
            if eighth % 2:
                out.append((rbar(bar, eighth * 0.5 + 0.02), 0.08, TAMBO, 0.21))
    for off, pitch, vel in ((3.5, TOM_H, 0.72), (3.75, TOM_M, 0.78),
                            (4.0, TOM_L, 0.86), (4.25, SNARE, 0.9)):
        out.append((rbar(16, off), 0.13, pitch, vel))

    # End credits strip the arrangement back to a small lounge kit.
    for bar in range(1, 8):
        out.append((endbar(bar), 0.14, KICK, 0.45 - 0.025 * bar))
        out.append((endbar(bar, 2.0), 0.10, RIM, 0.36 - 0.018 * bar))
        for off in (0.5, 1.5, 2.5, 3.5):
            out.append((endbar(bar, off), 0.08, HAT_C, 0.22))
    out += [(endbar(8), 0.18, KICK, 0.5),
            (endbar(8), 0.22, COWBELL, 0.32)]
    return out


# Bass -----------------------------------------------------------------------

def bass_notes():
    out = []
    # Bass enters like a title card at the midpoint of the cold open.
    for bar in range(5, 9):
        root = P(FIVE_CHORDS[(bar - 5) % 4][0])
        out.append((fbar(bar), 2.4, root, 0.55))
        out.append((fbar(bar, 3.0), 0.7, root + 12, 0.42))
        out.append((fbar(bar, 4.0), 0.7, root + 7, 0.46))

    patterns = (
        ((0.0, 0), (0.75, 12), (1.5, 7), (2.25, 10),
         (3.0, 0), (3.5, 3), (4.25, 5), (4.75, 7)),
        ((0.0, 0), (0.5, 7), (1.25, 10), (2.0, 12),
         (2.75, 3), (3.5, 0), (4.0, -1), (4.5, 0)),
    )
    for bar in range(9, 49):
        root = P(FIVE_CHORDS[(bar - 9) % 4][0])
        for off, interval in patterns[bar % 2]:
            out.append((fbar(bar, off), 0.38 if off % 1.0 else 0.48,
                        root + interval, 0.62 + (0.08 if off == 0 else 0.0)))

    for bar in range(1, 25):
        root = P(BLUE_CHORDS[(bar - 1) % 8][0])
        out.append((bluebar(bar), 1.65, root, 0.45))
        out.append((bluebar(bar, 2.0), 0.42, root + 7, 0.35))
        approach = root + (1 if bar % 2 else -1)
        out.append((bluebar(bar, 2.5), 0.34, approach, 0.31))

    chase_pattern = ((0.0, 0), (0.5, 7), (1.0, 12), (1.75, 10),
                     (2.25, 7), (2.75, 3), (3.25, 0))
    for bar in range(1, 33):
        root = P(CHASE_CHORDS[(bar - 1) % 4][0])
        for off, interval in chase_pattern:
            out.append((chasebar(bar, off), 0.30, root + interval,
                        0.65 + (0.07 if off == 0 else 0.0)))

    for bar in range(1, 17):
        root = P(FIVE_CHORDS[(bar - 1) % 4][0])
        for off, interval in patterns[(bar + 1) % 2]:
            out.append((rbar(bar, off), 0.39, root + interval,
                        0.69 + (0.08 if off == 0 else 0.0)))

    credit_roots = ("F1", "Db2", "Ab1", "C2", "F1", "Bb1", "C2")
    for bar, name in enumerate(credit_roots, 1):
        root = P(name)
        out.append((endbar(bar), 1.7, root, 0.38))
        out.append((endbar(bar, 2.0), 0.75, root + 7, 0.3))
        out.append((endbar(bar, 3.0), 0.65, root + 12, 0.32))
    out.append((endbar(8), 7.0, P("F1"), 0.42))
    return out


# Keyboards and guitar -------------------------------------------------------

def rhodes_notes():
    out = []
    # A few isolated voicings under the monochrome cold open.
    for bar in range(3, 9):
        names = FIVE_CHORDS[(bar - 3) % 4][1]
        chord(out, fbar(bar, 0.5), 3.7, names[1:], 0.35, roll=0.035)
    for bar in range(9, 49):
        names = FIVE_CHORDS[(bar - 9) % 4][1]
        chord(out, fbar(bar), 1.25, names, 0.49, roll=0.012)
        chord(out, fbar(bar, 2.5), 0.72, names[1:], 0.38)
        chord(out, fbar(bar, 4.0), 0.72, names[2:], 0.43)
    # Blue Hour is the harmonic heart: rolled, long suitcase voicings.
    for bar in range(1, 25):
        names = BLUE_CHORDS[(bar - 1) % 8][1]
        chord(out, bluebar(bar), 2.82, names, 0.46 + 0.03 * (bar >= 17),
              roll=0.045)
    for bar in range(1, 33):
        names = CHASE_CHORDS[(bar - 1) % 4][1]
        chord(out, chasebar(bar), 0.62, names[1:], 0.39)
        chord(out, chasebar(bar, 2.0), 0.62, names[2:], 0.35)
    for bar in range(1, 17):
        names = FIVE_CHORDS[(bar - 1) % 4][1]
        chord(out, rbar(bar), 1.35, names, 0.53, roll=0.015)
        chord(out, rbar(bar, 2.5), 0.72, names[1:], 0.42)
        chord(out, rbar(bar, 4.0), 0.70, names[2:], 0.47)
    credit_voicings = [BLUE_CHORDS[i][1] for i in (4, 2, 0, 3, 4, 5, 3)]
    for bar, names in enumerate(credit_voicings, 1):
        chord(out, endbar(bar), 3.75, names, 0.38, roll=0.055)
    chord(out, endbar(8), 7.5, ("F2", "C3", "Ab3", "A3", "D4", "G4"),
          0.42, roll=0.045)
    return out


def clavinet_notes():
    out = []
    scale_sets = (
        ("F3", "C4", "Eb4", "Ab3", "G4"),
        ("Db3", "Ab3", "C4", "F4", "G4"),
        ("Bb2", "F3", "Ab3", "Db4", "C4"),
        ("C3", "G3", "Bb3", "Db4", "Eb4"),
    )
    hits = (0, 2, 3, 5, 7, 8, 10, 12, 13, 15, 17, 19)
    for bar in range(7, 49):
        tones = scale_sets[(bar - 9) % 4]
        for index, step in enumerate(hits):
            if bar in (16, 24, 32, 40, 48) and step >= 16:
                continue
            name = tones[(index + bar) % len(tones)]
            accent = 0.16 if step in (0, 8, 12) else 0.0
            out.append((fbar(bar, step * 0.25 + human(17, bar * 20 + step, 0.004)),
                        0.115, P(name), 0.34 + accent))
    chase_tones = (("E3", "B3", "D4", "F#4", "G4"),
                   ("D3", "A3", "C4", "E4", "F#4"),
                   ("C3", "G3", "B3", "D4", "F#4"),
                   ("B2", "F#3", "A3", "C4", "D4"))
    for bar in range(1, 33):
        tones = chase_tones[(bar - 1) % 4]
        for step in (0, 2, 3, 5, 6, 8, 10, 11, 13):
            out.append((chasebar(bar, step * 0.25), 0.11,
                        P(tones[(step + bar) % 5]),
                        0.38 + (0.12 if step in (0, 8) else 0.0)))
    for bar in range(1, 17):
        tones = scale_sets[(bar - 1) % 4]
        for index, step in enumerate(hits):
            if bar == 16 and step >= 14:
                continue
            out.append((rbar(bar, step * 0.25), 0.11,
                        P(tones[(index + bar + 2) % 5]),
                        0.39 + (0.13 if step in (0, 12) else 0.0)))
    return out


def organ_notes():
    out = []
    for bar in range(9, 49):
        names = FIVE_CHORDS[(bar - 9) % 4][1]
        for off, vel in ((1.5, 0.34), (3.5, 0.39)):
            chord(out, fbar(bar, off), 0.58, names[1:4], vel)
    # A slow hymn beneath the love theme; the rotary room supplies motion.
    for bar in range(9, 25, 2):
        names = BLUE_CHORDS[(bar - 1) % 8][1]
        chord(out, bluebar(bar), 5.82, names[:4], 0.29, roll=0.025)
    for bar in range(1, 33):
        names = CHASE_CHORDS[(bar - 1) % 4][1]
        chord(out, chasebar(bar, 1.0), 0.48, names[1:4], 0.39)
        chord(out, chasebar(bar, 2.75), 0.45, names[2:], 0.36)
    for bar in range(1, 17):
        names = FIVE_CHORDS[(bar - 1) % 4][1]
        chord(out, rbar(bar, 1.5), 0.65, names[1:4], 0.43)
        chord(out, rbar(bar, 3.5), 0.70, names[2:], 0.46)
    return out


def guitar_notes():
    out = []
    # Clean chord fragments are the glue in the title statement.
    for bar in range(9, 25):
        names = FIVE_CHORDS[(bar - 9) % 4][1]
        for index, name in enumerate(names[1:5]):
            out.append((fbar(bar, 0.25 + index * 0.75), 0.48, P(name) + 12,
                        0.34 + 0.025 * index))
        out.append((fbar(bar, 4.25), 0.55, P(names[2]) + 12, 0.39))

    # Eight-bar guitar feature: composed F-Dorian cells, not random noodling.
    scale = [P(n) for n in ("F4", "G4", "Ab4", "Bb4", "C5", "D5", "Eb5", "F5")]
    cells = ((0, 2, 3, 4, 2, 1, 0), (2, 4, 6, 7, 6, 4, 3),
             (4, 3, 2, 0, 1, 2, 4), (5, 7, 6, 4, 3, 2, 0))
    positions = (0.0, 0.75, 1.25, 2.0, 3.0, 3.5, 4.25)
    durations = (0.52, 0.30, 0.48, 0.72, 0.32, 0.52, 0.62)
    for local_bar in range(8):
        cell = cells[local_bar % 4]
        for off, dur, degree in zip(positions, durations, cell):
            octave = 12 if local_bar >= 6 and degree < 3 else 0
            out.append((fbar(25 + local_bar, off), dur, scale[degree] + octave,
                        0.52 + 0.035 * local_bar))
    # After the solo, answer the wind and organ in clipped upper-register dyads.
    for bar in range(33, 49):
        names = FIVE_CHORDS[(bar - 9) % 4][1]
        for off in (0.5, 3.0):
            chord(out, fbar(bar, off), 0.42, (names[2], names[4]), 0.38)

    # Chase guitar: relentless two-note shapes on the 2+2+3 anchors.
    for bar in range(1, 33):
        names = CHASE_CHORDS[(bar - 1) % 4][1]
        for index, off in enumerate((0.0, 1.0, 2.0, 3.0)):
            chord(out, chasebar(bar, off), 0.38,
                  (names[1], names[3]), 0.42 + 0.04 * (index == 0))
    for bar in range(1, 17):
        names = FIVE_CHORDS[(bar - 1) % 4][1]
        for index, name in enumerate(names[1:5]):
            out.append((rbar(bar, 0.25 + index * 0.75), 0.46,
                        P(name) + 12, 0.42))
    # Harmonic-like credits arpeggio.
    for bar in range(1, 8):
        names = BLUE_CHORDS[(bar + 3) % 8][1]
        for index, name in enumerate(names[-4:]):
            out.append((endbar(bar, index * 0.75), 0.62, P(name) + 12, 0.29))
    for name, off in zip(("F4", "C5", "A5", "D6", "G6"), (0, 0.6, 1.2, 1.8, 2.4)):
        out.append((endbar(8, off), 5.0 - off, P(name), 0.31))
    return out


# Principal voices -----------------------------------------------------------

THEME = (
    (0, 0.50, 0.58, "F4"), (0, 1.25, 0.34, "Ab4"),
    (0, 1.75, 0.58, "Bb4"), (0, 2.75, 0.42, "C5"),
    (0, 3.50, 0.55, "Eb5"), (0, 4.25, 0.58, "C5"),
    (1, 0.00, 0.68, "Db5"), (1, 1.00, 0.42, "C5"),
    (1, 1.75, 0.64, "Bb4"), (1, 2.75, 0.42, "Ab4"),
    (1, 3.50, 0.40, "G4"), (1, 4.25, 0.58, "F4"),
    (2, 0.25, 0.42, "F4"), (2, 1.00, 0.42, "Ab4"),
    (2, 1.75, 0.60, "C5"), (2, 2.75, 0.38, "Db5"),
    (2, 3.50, 0.38, "C5"), (2, 4.20, 0.65, "Bb4"),
    (3, 0.00, 0.38, "G4"), (3, 0.75, 0.38, "Bb4"),
    (3, 1.50, 0.48, "Db5"), (3, 2.25, 0.48, "C5"),
    (3, 3.25, 0.48, "Ab4"), (3, 4.25, 0.68, "F4"),
)


def theme_phrase(bar_function, start_bar, velocity=0.7, octave=0):
    return [(bar_function(start_bar + bar, off), dur, P(name) + octave, velocity)
            for bar, off, dur, name in THEME]


def wind_notes():
    out = []
    # Smoky answers around the brass theme.
    answers = (("C5", 0.75), ("Eb5", 0.42), ("F5", 0.75),
               ("G5", 0.40), ("F5", 0.65))
    for start in (9, 17):
        for index, (name, dur) in enumerate(answers):
            bar = start + 1 + index
            out.append((fbar(bar, 3.65), dur, P(name), 0.46 + index * 0.025))

    # Second soloist in Split Screen, lyrical against the guitar's angularity.
    phrases = [
        ((0.0, 1.10, "F4"), (1.5, 0.42, "Ab4"), (2.25, 1.20, "C5"),
         (4.0, 0.72, "Bb4")),
        ((0.25, 0.70, "Db5"), (1.25, 0.58, "C5"), (2.25, 1.35, "Ab4"),
         (4.0, 0.65, "G4")),
        ((0.0, 0.52, "Bb4"), (0.75, 0.52, "C5"), (1.5, 0.72, "Eb5"),
         (2.75, 1.30, "F5"), (4.5, 0.38, "Eb5")),
        ((0.0, 1.45, "C5"), (2.0, 0.62, "Bb4"), (3.0, 1.55, "F4")),
    ]
    for local in range(8):
        for off, dur, name in phrases[local % 4]:
            out.append((fbar(33 + local, off), dur, P(name), 0.53 + 0.025 * local))

    # Blue Hour's eight-bar love melody, developed three times.
    love = (
        (0, 0.0, 1.20, "Eb5"), (0, 1.5, 0.42, "F5"), (0, 2.0, 0.78, "G5"),
        (1, 0.0, 1.72, "C5"), (1, 2.0, 0.72, "Bb4"),
        (2, 0.0, 0.75, "Ab4"), (2, 1.0, 0.72, "C5"), (2, 2.0, 0.78, "Eb5"),
        (3, 0.0, 1.25, "F5"), (3, 1.5, 1.20, "Eb5"),
        (4, 0.0, 1.25, "C5"), (4, 1.5, 0.42, "Db5"), (4, 2.0, 0.78, "Eb5"),
        (5, 0.0, 1.72, "Ab4"), (5, 2.0, 0.72, "Bb4"),
        (6, 0.0, 0.72, "C5"), (6, 1.0, 0.72, "Eb5"), (6, 2.0, 0.78, "F5"),
        (7, 0.0, 2.72, "Eb5"),
    )
    for cycle in range(3):
        shift = 12 if cycle == 2 else 0
        vel = 0.48 + 0.045 * cycle
        for bar, off, dur, name in love:
            out.append((bluebar(1 + cycle * 8 + bar, off), dur,
                        P(name) + shift, vel))

    # In the reprise, the wind states the title up an octave over the brass.
    out += theme_phrase(rbar, 9, 0.58, 12)
    out += [(endbar(2, 0.5), 1.5, P("Ab4"), 0.34),
            (endbar(3, 0.0), 1.0, P("C5"), 0.32),
            (endbar(4, 1.0), 1.8, P("Bb4"), 0.31),
            (endbar(6, 0.0), 2.5, P("F4"), 0.28)]
    return out


def brass_notes():
    out = []
    # Teaser fragments, then two complete title statements.
    out += [(fbar(4, 3.5), 0.5, P("C5"), 0.4),
            (fbar(8, 3.5), 0.45, P("Eb5"), 0.52),
            (fbar(8, 4.25), 0.58, P("F5"), 0.58)]
    out += theme_phrase(fbar, 9, 0.69)
    out += theme_phrase(fbar, 17, 0.74)
    # Punctuate all three Split Screen soloists.
    for bar in range(25, 49):
        names = FIVE_CHORDS[(bar - 9) % 4][1]
        if bar % 2:
            chord(out, fbar(bar, 3.75), 0.62, names[2:], 0.44)
        if bar in (32, 40, 48):
            chord(out, fbar(bar, 4.25), 0.62, names[1:5], 0.58)
    # 7/8 chase stabs follow the long 3-eighth group.
    for bar in range(1, 33):
        names = CHASE_CHORDS[(bar - 1) % 4][1]
        chord(out, chasebar(bar, 2.5), 0.48, names[1:5],
              0.43 + 0.04 * (bar % 4 == 0))
    out += theme_phrase(rbar, 1, 0.78)
    out += theme_phrase(rbar, 9, 0.86)
    chord(out, rbar(16, 4.25), 0.68, ("F3", "C4", "Eb4", "Ab4", "G5"), 0.82)
    chord(out, endbar(8), 7.2, ("F3", "C4", "Ab4", "A4", "D5", "G5"), 0.38)
    return out


def cs80_notes():
    out = []
    # Cold-open silhouette and chromatic question mark.
    intro = ((1, 0.0, 3.8, "F4"), (2, 0.0, 1.2, "Ab4"),
             (2, 1.5, 1.2, "G4"), (3, 0.0, 2.2, "Db5"),
             (4, 0.0, 1.0, "C5"), (4, 1.5, 2.8, "Gb4"),
             (7, 0.0, 3.0, "C5"), (8, 1.0, 1.8, "Eb5"))
    for bar, off, dur, name in intro:
        out.append((fbar(bar, off), dur, P(name), 0.38 + 0.035 * (bar > 4)))

    # Countermelody is deliberately long-note legato against the clipped hook.
    counter = ((0, 0.0, 2.2, "C4"), (0, 3.0, 1.6, "Db4"),
               (1, 0.0, 2.2, "Eb4"), (1, 3.0, 1.6, "C4"),
               (2, 0.0, 2.2, "Ab3"), (2, 3.0, 1.6, "Bb3"),
               (3, 0.0, 4.5, "C4"))
    for start in (9, 17):
        for bar, off, dur, name in counter:
            out.append((fbar(start + bar, off), dur, P(name), 0.36))

    # Rooftop lead: E-Dorian cells stretch across the 2+2+3 grid.
    scale = [P(n) for n in ("E4", "F#4", "G4", "A4", "B4", "C#5", "D5", "E5")]
    cells = ((0, 2, 4, 3, 6), (4, 5, 7, 6, 4),
             (2, 1, 0, 3, 4), (6, 4, 3, 2, 0))
    for bar in range(1, 33):
        cell = cells[(bar - 1) % 4]
        for index, (off, dur) in enumerate(((0.0, 0.42), (0.5, 0.40),
                                            (1.25, 0.58), (2.0, 0.42),
                                            (2.75, 0.62))):
            octave = 12 if bar >= 25 and index == 2 else 0
            out.append((chasebar(bar, off), dur, scale[cell[index]] + octave,
                        0.48 + 0.009 * bar))

    # Reprise counterline rises where the opening one fell.
    for cycle in range(2):
        start = 1 + cycle * 8
        for bar, off, dur, name in counter:
            out.append((rbar(start + bar, off), dur, P(name) + (12 if cycle else 0),
                        0.43 + 0.05 * cycle))
    out += [(endbar(1), 2.5, P("C5"), 0.32),
            (endbar(5), 2.5, P("Ab4"), 0.29),
            (endbar(8), 6.8, P("A4"), 0.31)]
    return out


# Ensemble colors ------------------------------------------------------------

def strings_notes():
    out = []
    # Only a faint reveal before Blue Hour; then the real string entrance.
    for bar in (21, 23):
        names = FIVE_CHORDS[(bar - 9) % 4][1]
        chord(out, fbar(bar), 9.7, names[1:5], 0.22, roll=0.03)
    for bar in range(1, 25, 2):
        names = BLUE_CHORDS[(bar - 1) % 8][1]
        chord(out, bluebar(bar), 5.86, names, 0.34 + 0.025 * (bar >= 17),
              roll=0.025)
    # A rising line in the final title ties the love theme to the spy hook.
    for bar in range(1, 17):
        names = FIVE_CHORDS[(bar - 1) % 4][1]
        chord(out, rbar(bar), 4.82, names[1:5], 0.27 + 0.009 * bar)
    for bar in range(1, 8):
        names = BLUE_CHORDS[(bar + 3) % 8][1]
        chord(out, endbar(bar), 3.78, names[1:], 0.24)
    chord(out, endbar(8), 7.3, ("F3", "C4", "Ab4", "A4", "D5", "G5"), 0.29)
    return out


def mellotron_notes():
    out = []
    # Tape-flute ghosts around the cold open, then a descant in Blue Hour.
    out += [(fbar(1), 4.2, P("C5"), 0.25),
            (fbar(2, 0.5), 3.7, P("Db5"), 0.23),
            (fbar(3), 4.1, P("Ab4"), 0.25),
            (fbar(5), 3.5, P("Eb5"), 0.27),
            (fbar(7), 4.0, P("C5"), 0.25)]
    descant = ((0, 0.0, 1.0, "Ab5"), (0, 1.5, 1.2, "G5"),
               (2, 0.0, 1.0, "F5"), (2, 1.5, 1.2, "Eb5"),
               (4, 0.0, 1.0, "C5"), (4, 1.5, 1.2, "Db5"),
               (6, 0.0, 2.6, "Bb4"))
    for cycle in range(3):
        for bar, off, dur, name in descant:
            out.append((bluebar(1 + cycle * 8 + bar, off), dur, P(name),
                        0.25 + 0.025 * cycle))
    out += [(endbar(1), 3.2, P("C5"), 0.23),
            (endbar(3), 3.2, P("Ab4"), 0.22),
            (endbar(5), 3.2, P("G4"), 0.2),
            (endbar(7), 3.2, P("F4"), 0.2),
            (endbar(8), 7.0, P("D5"), 0.22)]
    return out


# Track table ----------------------------------------------------------------

TRACKS = [
    {"name": "LinnDrum Ensemble", "script": "linndrum.py", "gain_db": -1.5,
     "pan": 0.0, "notes": drum_notes(),
     "macros": {0: 0.62, 1: 0.42, 2: 0.48, 3: 0.52, 4: 0.62,
                6: 0.45, 10: 0.48, 11: 0.48, 12: 0.48, 13: 0.48,
                14: 0.33, 15: 0.48},
     "vol": [(M1, 0.72), (M2, 0.94), (M3, 1.0), (M4, 0.68),
             (M5, 0.98), (M6, 1.08), (M7, 0.62), (TOTAL_BEATS, 0.5)],
     "macro_env": {0: [(M1, 0.52), (M2, 0.62), (M4, 0.5), (M5, 0.65),
                       (M6, 0.7), (M7, 0.48)],
                   2: [(M1, 0.32), (M3, 0.5), (M4, 0.38), (M6, 0.58)],
                   4: [(M1, 0.42), (M3, 0.64), (M4, 0.38), (M6, 0.7)],
                   14: [(M1, 0.52), (M4, 0.26), (M5, 0.38), (M6, 0.56)]},
     "effects": [FX_DRUMS]},
    {"name": "Minimoog Bass", "script": "minimoog.py", "gain_db": -2.5,
     "pan": 0.0, "notes": bass_notes(),
     "macros": {0: 0.52, 1: 0.30, 2: 0.28, 3: 0.55, 4: 0.0,
                5: 0.47, 6: 0.53, 7: 0.02, 8: 0.02, 9: 0.25,
                10: 0.38, 11: 0.12, 12: 0.03, 13: 0.34, 14: 0.26,
                15: 0.34},
     "vol": [(M1, 0.78), (M2, 0.94), (M4, 0.65), (M5, 0.92),
             (M6, 1.0), (M7, 0.68)],
     "macro_env": {1: [(fbar(5), 0.23), (M2, 0.34), (M3, 0.45),
                       (M4, 0.22), (M5, 0.48), (M6, 0.42), (M7, 0.24)],
                   2: [(M1, 0.22), (M3, 0.38), (M4, 0.2), (M5, 0.42)],
                   3: [(M1, 0.42), (M3, 0.65), (M4, 0.35), (M6, 0.62)],
                   15: [(M1, 0.22), (M5, 0.4), (M6, 0.36), (M7, 0.15)]},
     "effects": [FX_BASS]},
    {"name": "Rhodes Suitcase", "script": "rhodes.py", "gain_db": -8.0,
     "pan": -0.08, "notes": rhodes_notes(),
     "macros": {0: 0.5, 1: 0.58, 2: 0.62, 3: 0.28, 4: 0.28,
                5: 0.22, 6: 0.56, 7: 0.02, 8: 0.45, 9: 0.36,
                10: 0.24, 11: 0.12},
     "vol": [(M1, 0.68), (M2, 0.85), (M3, 0.92), (M4, 1.05),
             (M5, 0.7), (M6, 0.92), (M7, 0.95)],
     "macro_env": {1: [(M1, 0.42), (M3, 0.68), (M4, 0.5), (M6, 0.72)],
                   4: [(M1, 0.18), (M4, 0.42), (M5, 0.2), (M7, 0.36)],
                   5: [(M1, 0.15), (M3, 0.34), (M4, 0.18), (M6, 0.38)],
                   6: [(M1, 0.46), (M3, 0.68), (M4, 0.52), (M6, 0.72)]},
     "effects": [FX_RHODES]},
    {"name": "Clavinet D6", "script": "clavinet.py", "gain_db": 1.0,
     "pan": 0.14, "notes": clavinet_notes(),
     "macros": {0: 0.48, 1: 0.68, 2: 0.18, 3: 0.38, 4: 0.22,
                5: 0.72, 6: 0.01, 7: 0.28, 8: 0.12, 9: 0.08},
     "vol": [(fbar(7), 0.58), (M2, 0.85), (M3, 1.0), (M5, 0.92),
             (M6, 1.08), (M7, 0.0)],
     "macro_env": {2: [(M1, 0.3), (M3, 0.12), (M5, 0.32), (M6, 0.08)],
                   3: [(M1, 0.18), (M2, 0.42), (M3, 0.62), (M5, 0.48),
                       (M6, 0.7)],
                   4: [(M1, 0.16), (M3, 0.34), (M5, 0.58), (M6, 0.3)],
                   5: [(M1, 0.5), (M3, 0.8), (M5, 0.7), (M6, 0.88)]},
     "effects": [FX_CLAV]},
    {"name": "Hammond B3", "script": "b3.py", "gain_db": -3.0,
     "pan": 0.08, "notes": organ_notes(),
     "macros": {0: 0.44, 1: 0.48, 2: 0.74, 3: 0.58, 4: 0.22,
                5: 0.36, 6: 0.3, 7: 0.22, 8: 0.22, 9: 0.3},
     "vol": [(M2, 0.72), (M3, 0.92), (M4, 0.55), (M5, 0.84),
             (M6, 1.0), (M7, 0.0)],
     "macro_env": {5: [(M2, 0.25), (M3, 0.48), (M4, 0.18), (M5, 0.52)],
                   8: [(M2, 0.18), (fbar(41), 0.82), (M4, 0.2),
                       (M5, 0.88), (M6, 0.72)],
                   9: [(M2, 0.18), (M3, 0.48), (M4, 0.12), (M6, 0.54)]},
     "effects": [FX_ORGAN]},
    {"name": "Karplus Guitar", "script": "karplus.py", "gain_db": 1.0,
     "pan": -0.16, "notes": guitar_notes(),
     "macros": {0: 0.52, 1: 0.28, 2: 0.58, 3: 0.62, 4: 0.64,
                5: 0.38},
     "vol": [(M2, 0.7), (M3, 1.1), (fbar(33), 0.78), (M5, 0.98),
             (M6, 0.88), (M7, 0.7)],
     "macro_env": {1: [(M2, 0.42), (M3, 0.18), (fbar(33), 0.38),
                       (M5, 0.22), (M7, 0.68)],
                   2: [(M2, 0.42), (M3, 0.68), (M5, 0.5), (M7, 0.78)],
                   3: [(M2, 0.48), (M3, 0.72), (M5, 0.58), (M7, 0.82)],
                   4: [(M2, 0.45), (M3, 0.82), (M5, 0.72), (M7, 0.32)]},
     "effects": [FX_GUITAR]},
    {"name": "VL1 Tenor", "script": "vl1.py", "gain_db": -2.5,
     "pan": 0.11, "notes": wind_notes(),
     "macros": {0: 0.52, 1: 0.62, 2: 0.55, 3: 0.18, 4: 0.08,
                5: 0.08, 6: 0.2, 7: 0.72, 8: 0.16},
     "vol": [(M2, 0.68), (fbar(33), 1.0), (M4, 0.88), (bluebar(17), 1.05),
             (M5, 0.0), (rbar(9), 0.92), (M7, 0.5)],
     "macro_env": {1: [(M2, 0.48), (fbar(33), 0.72), (M4, 0.55),
                       (bluebar(17), 0.82), (rbar(9), 0.74), (M7, 0.42)],
                   2: [(M2, 0.42), (fbar(33), 0.68), (M4, 0.52),
                       (rbar(9), 0.7)],
                   4: [(M2, 0.04), (fbar(33), 0.16), (M4, 0.06),
                       (bluebar(17), 0.2), (rbar(9), 0.14)]},
     "effects": [FX_WIND]},
    {"name": "OB-Xa Brass", "script": "obxa.py", "gain_db": -6.0,
     "pan": -0.04, "notes": brass_notes(),
     "macros": {0: 0.49, 1: 0.38, 2: 0.52, 3: 0.34, 4: 0.62,
                5: 0.06, 6: 0.26, 7: 0.03, 8: 0.42, 9: 0.18},
     "vol": [(M1, 0.52), (M2, 0.9), (M3, 0.68), (M5, 0.82),
             (M6, 1.08), (M7, 0.56)],
     "macro_env": {1: [(M1, 0.22), (M2, 0.42), (M3, 0.34), (M5, 0.5),
                       (M6, 0.62)],
                   2: [(M1, 0.38), (M2, 0.58), (M3, 0.48), (M5, 0.66),
                       (M6, 0.75)],
                   4: [(M1, 0.42), (M2, 0.68), (M5, 0.72), (M6, 0.84)],
                   5: [(M1, 0.18), (M2, 0.05), (M5, 0.02), (M6, 0.0)]},
     "effects": [FX_BRASS]},
    {"name": "CS-80 Counterline", "script": "cs80.py", "gain_db": -10.5,
     "pan": 0.16, "notes": cs80_notes(),
     "macros": {0: 0.46, 1: 0.42, 2: 0.3, 3: 0.08, 4: 0.14,
                5: 0.12, 6: 0.48, 7: 0.5, 8: 0.08, 9: 0.28,
                10: 0.62, 11: 0.24, 12: 0.12, 13: 0.32, 14: 0.3,
                15: 0.58},
     "vol": [(M1, 0.72), (M2, 0.58), (M3, 0.35), (M5, 1.0),
             (M6, 0.84), (M7, 0.48)],
     "macro_env": {1: [(M1, 0.24), (M2, 0.48), (M5, 0.58), (M6, 0.68),
                       (M7, 0.3)],
                   5: [(M1, 0.18), (M2, 0.08), (M5, 0.24), (M6, 0.16)],
                   6: [(M1, 0.32), (M2, 0.52), (M5, 0.68), (M6, 0.72)],
                   15: [(M1, 0.38), (M2, 0.6), (M5, 0.78), (M6, 0.86)]},
     "effects": [FX_CS80]},
    {"name": "Solina Strings", "script": "solina.py", "gain_db": 2.0,
     "pan": -0.1, "notes": strings_notes(),
     "macros": {0: 0.42, 1: 0.5, 2: 0.62, 3: 0.44, 4: 0.58,
                5: 0.22, 6: 0.58, 7: 0.34},
     "vol": [(fbar(21), 0.38), (M4, 0.92), (bluebar(17), 1.08),
             (M5, 0.0), (M6, 0.86), (rbar(9), 1.0), (M7, 0.52)],
     "macro_env": {4: [(M3, 0.42), (M4, 0.68), (M6, 0.74), (M7, 0.48)],
                   5: [(M3, 0.12), (M4, 0.38), (M6, 0.22)],
                   7: [(M3, 0.18), (M4, 0.48), (bluebar(17), 0.68),
                       (M6, 0.52), (rbar(13), 0.82)]},
     "effects": [FX_STRINGS]},
    {"name": "Mellotron Flute", "script": "mellotron.py", "gain_db": 6.0,
     "pan": 0.18, "notes": mellotron_notes(),
     "macros": {0: 0.38, 1: 0.52, 2: 0.22, 3: 0.32, 4: 0.28,
                5: 0.42, 6: 0.18},
     "vol": [(M1, 0.8), (M2, 0.0), (M4, 0.72), (bluebar(17), 0.9),
             (M5, 0.0), (M7, 0.62)],
     "macro_env": {1: [(M1, 0.38), (M4, 0.58), (bluebar(17), 0.7),
                       (M7, 0.42)],
                   3: [(M1, 0.42), (M4, 0.24), (bluebar(17), 0.5),
                       (M7, 0.6)],
                   6: [(M1, 0.28), (M4, 0.12), (M7, 0.36)]},
     "effects": [FX_TAPE]},
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
