# Soundtrack

Example audio performed entirely by the MicroPython VST3 instrument - no
third-party plug-ins, no samples. Every sound is a MicroPython script
running synthio and the audioif effects inside its own sidecar process.

Each piece is a subdirectory holding its own `composition.py` and
`instruments/`. See `piece.py`, `generate_project.py`, `render_preview.py`,
`verify_song.py`, and `launch.sh` for the tooling that generates,
renders, and verifies a piece - documented in
[`../tools/README.md`](../tools/README.md), since none of it is specific
to the soundtrack.

## Why instruments are per piece, not shared

The instrument scripts are the patches, and the generated REAPER
projects embed them byte-for-byte. With a shared library, tweaking a
sound for a new piece would silently change how an older piece renders
the next time its project is regenerated. So finished pieces own their
instruments outright, the way a finished mix owns its patches. Starting
a new piece means copying the closest existing instrument in and letting
it diverge - Automata's `strings.py`, `choir.py`, and `glass.py` began
as copies from Perihelion, and its `riser.py` and `brass_stabs.py` are
deliberate mutations of Perihelion patches.

## The pieces

**Perihelion** - D minor, five sections: sub drone, Moog bass ostinato,
string and brass ensembles, choir, timpani, impacts, nineteen automation
envelopes of filter motion, resolving through a Picardy third.

**Automata** - five movements, 4,600+ notes:

| | bars | meter/tempo | |
|---|---|---|---|
| I | 1-20 | 4/4 @84 | **Dawn Protocol** - air, glass, FM bells, choir hum, heartbeat kick |
| II | 1-32 | **7/8** @112 | **Assembly Line** - 2+2+3 polysynth ostinato, Reese bass, glitch percussion |
| III | 1-32 | 4/4 @126 | **Ignition** - four on the floor, the 303 wakes up, two-minute build |
| IV | 1-48 | 4/4 @128 | **Overdrive** - B minor supersaw anthem over the full kit, organ, brass stabs |
| V | 1-16 | 4/4 @64..48 | **Afterimage** - felt keys quote the Perihelion theme in D major; tape-stop ending |

Automata's extras over Perihelion: a synthesized drum kit on separate
tracks (kick, snare, choking hi-hats, claps, toms, shaker, glitch) with
swing, humanization, ghost notes and fills; a 303-style acid bass whose
overlapping notes become genuine slides; transport-aware instruments
(the sidechain pad phase-locks its duck to the beat and every echo tunes
itself to the host tempo through `vstaudio.transport()`); a meter change,
three tempos, a key modulation, twenty-seven automation envelopes, and a
closing tape stop.

## Listening

```bash
./launch.sh                      # play Perihelion through the speakers
./launch.sh --piece automata     # play Automata
./launch.sh --render --piece automata   # headless verified bounce
```

Play mode regenerates the project under `C:\Users\bradb\Music\<Title>\`,
opens REAPER with a self-deleting autoplay startup script, and leaves
REAPER open. Render mode bounces the piece offline through the installed
plug-in, checks every engine and envelope, writes `build/<Title>.wav`,
and compares it section by section against the CPython preview.
