"""Kit Tour - one drum part, ten machines, a program change every four bars.

A fixture rather than a piece of music, in the same spirit as Patch Test: the
groove never changes, so everything you hear change came from the program
change. `drumkits` holds all ten drum machines and swaps which one is playing
when a MIDI Program Change arrives, so this walks the list - TR-808, TR-909,
TR-707, TR-606, CR-78, LinnDrum, DMX, DrumTraks, SP-1200, Simmons SDS-V - four
bars each at 120.

The part is written in General MIDI, which every machine in the library now
answers, and it deliberately reaches past the five notes they all share:

  kick 36, snare 38, hats 42/46, crash 49    every kit has these
  cowbell 56                                 seven of the ten
  congas 62/63                               the LinnDrum and the TR-808 only

So the backbone holds all the way through while the decoration comes and goes.
A kit with no cowbell is silent on the cowbell - it does not answer with the
nearest drum it has, which is the whole point of the library's General MIDI
pass. The crash lands on the downbeat of every switch, so the change announces
itself.

A drum machine's macros are its own, so the program change brings each kit's
patch 0 with it; nothing here sets a macro.
"""

TITLE = "Kit_Tour"
SAMPLE_RATE = 48000
MASTER_GAIN_DB = -3.0
ACTIVE_LIMIT = 1
CLIMAX_SECTION = "TR-808"   # measured: the loudest of the ten, in both renders
BEATS_PER_BAR = 4
BARS_PER_KIT = 4
TAIL_SECONDS = 3.0

#: The kits, in the order `audioinstruments.drumkits.KITS` lists them, which
#: is the order a program change walks. Program N selects index N.
KITS = [
    "TR-808", "TR-909", "TR-707", "TR-606", "CR-78",
    "LinnDrum", "DMX", "DrumTraks", "SP-1200", "Simmons SDS-V",
]

TOTAL_BARS = BARS_PER_KIT * len(KITS)
TEMPO_MAP = [(0.0, 120.0)]

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


KICK, SNARE, HAT_C, HAT_O, CRASH = 36, 38, 42, 46, 49
COWBELL, CONGA_HI, CONGA_MID = 56, 62, 63


def groove_notes():
    """The same bar, forty times over. Only the machine underneath changes."""
    out = []
    for index in range(TOTAL_BARS):
        first = bar(index + 1)
        in_kit = index % BARS_PER_KIT          # 0-3 within this kit's block

        # The switch announces itself: a crash on the downbeat of each kit.
        if in_kit == 0:
            out.append((first, 1.0, CRASH, 0.8))

        # Backbone - every kit answers all four of these.
        for beat in (0.0, 2.0):
            out.append((first + beat, 0.3, KICK, 0.9))
        if in_kit % 2 == 1:
            out.append((first + 2.75, 0.3, KICK, 0.6))
        for beat in (1.0, 3.0):
            out.append((first + beat, 0.3, SNARE, 0.85))
        for eighth in range(8):
            beat = eighth * 0.5
            open_hat = (eighth == 7 and in_kit % 2 == 0)
            out.append((first + beat, 0.2,
                        HAT_O if open_hat else HAT_C,
                        0.5 if eighth % 2 == 0 else 0.35))

        # Decoration - here is where the kits stop agreeing.
        if in_kit in (1, 3):
            out.append((first + 2.5, 0.2, COWBELL, 0.6))
        if in_kit == 2:
            out.append((first + 1.75, 0.2, CONGA_HI, 0.55))
            out.append((first + 3.25, 0.2, CONGA_MID, 0.5))
    return out


TRACKS = [
    {
        "name": "Drum Kits", "script": "drumkits.py", "gain_db": -5.0,
        "pan": 0.0, "notes": groove_notes(),
        # Nothing set: each program change carries that kit's own patch 0.
        "macros": {},
        "vol": [(bar(1), 1.0)],
        "macro_env": {},
        # (beat, program). Zero-based on the wire - a DAW shows program 1
        # where this says 0 - and one per four-bar block, in KITS order.
        "programs": [(bar(1 + BARS_PER_KIT * index), index)
                     for index in range(len(KITS))],
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


SECTIONS = [
    (name, bar(1 + BARS_PER_KIT * index), bar(1 + BARS_PER_KIT * (index + 1)))
    for index, name in enumerate(KITS)
]
