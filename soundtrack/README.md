# Soundtrack

Example audio performed entirely by the MicroPython VST3 instrument - no
third-party plug-ins, no samples. Every sound is a MicroPython script
running synthio and the audioif effects inside its own sidecar process.

Each piece is a subdirectory holding its own `composition.py`. Historical
pieces also own private `instruments/`; newer compositions can opt into the
shared `../lib/instruments/` collection - loaders for audiocomponents'
`audioinstruments` package - and put `audioeffects` processors after any
instrument. Nothing else here is infrastructure, and the
directory might be renamed, restructured, or replaced independently of the
tooling that generates, renders, and verifies a piece. Resolving and
previewing a piece offline lives in `../tools/`, documented in
[`../tools/README.md`](../tools/README.md); turning it into a real REAPER
project and driving REAPER itself lives in `../reaper/` and the root
`../reaper.sh`, documented in [`../reaper/README.md`](../reaper/README.md).

## Frozen patches and the shared library

Instrument scripts are patches, and generated REAPER projects embed them
byte-for-byte. Perihelion and Automata therefore keep the private patches they
were written against: Automata's `strings.py`, `choir.py`, and `glass.py`
began as copies from Perihelion, while its `riser.py` and `brass_stabs.py` are
deliberate mutations. Velvet Circuit is the first shared-library piece. Its
composition declares `INSTRUMENTS_DIR = "../../lib/instruments"`, and each of
its effect racks instantiates only public classes from `audioeffects`. The
generated project still embeds every chosen script, so the playable `.RPP`
remains self-contained.

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

**Velvet Circuit** - 4:28 of retro-future jazz/prog written as the main title
to an imaginary 1978 crime series discovered on a satellite in 2049. Its
seven scenes move from an F-minor 5/4 horn hook through a lyrical Ab-major 6/8
middle, an E-Dorian 7/8 rooftop chase, a contrapuntal title reprise, and an
ambiguous lounge-credits cadence. Eleven shared hardware emulations perform
6,480 notes: LinnDrum, Minimoog, Rhodes, Clavinet, B3, Karplus guitar, VL1,
OB-Xa, CS-80, Solina, and Mellotron. Every track has a real MicroPython Effect
insert built only from the shared library—saturation, overdrive, chorus,
phaser, tape/slap delays, spring/plate/hall reverbs, and subtle vibrato.

**Aurelia Overture** - 5:16 of tonal concert drama in D minor and common time,
written in response to Beethoven, Vivaldi, Bach, and Puccini rather than to a
modern genre. One four-note idea governs a Grave invocation, sonata Allegro,
F-major cantabile, four-entry fugato, recapitulation, and coda. Its 5,913
notes are arranged as an orchestral hierarchy—contrabasses, pizzicato and
sustained strings, orchestral body, solo violin and flute, horns, organ,
piano, choir, and structural timpani/cymbal. Eleven restrained hall/chamber
inserts place the shared instruments in depth without turning the piece into
an effects showcase.

**Neon Meridian** - 2:56 of 80s synthwave in A minor, three sections at
100/106 bpm. A Juno-106 pad opens alone and the harmonic rhythm accelerates
from four bars per chord to one, pulling into a Minimoog eighth-note ostinato
under the full LinnDrum. A Prophet-5 states the theme twice, a four-bar
breakdown strips everything back to a rimshot pulse and the DX7 signal motif,
and the climax lifts through the relative major before a ritard onto a held
Am(add9). Every chord is a triad plus an added ninth; the C-major excursion at
bar 61 is the only modulation. Nine shared instruments - LinnDrum, Minimoog,
Taurus, Juno-106, SH-101, Solina, OB-Xa, Prophet-5, DX7 - and **no effect
inserts at all**: the Juno's bucket-brigade chorus, the Solina's ensemble and
the Minimoog's overdrive are part of the instruments, exactly as they were
part of the hardware.

## Fixtures

Two directories are test fixtures, not pieces of music, and exist to
exercise something specific rather than to be listened to for their own
sake:

**PatchTest** - one Minimoog, one program change, nothing else. Bars 1-8
and 9-16 play byte-identical material, so any measured difference between
them can only have come from the patch change at bar 9 - proof that a MIDI
Program Change reaches an instrument script and re-applies its patch.

**ShimmerLab** - four ways to make the Perihelion "Air Shimmer" sound
musical, stacked on four tracks over the same sixteen bars so switching
between them is a solo button rather than a seek - an A/B listening rig,
not a finished cue.

## Listening

```bash
../reaper.sh                      # play Perihelion through the speakers
../reaper.sh --piece automata     # play Automata
../reaper.sh --piece velvetcircuit # play Velvet Circuit
../reaper.sh --piece aureliaoverture # play Aurelia Overture
../reaper.sh --render --piece automata   # headless verified bounce
../reaper.sh --render --piece velvetcircuit # render/verify it
../reaper.sh --render --piece aureliaoverture # render/verify it
../reaper.sh --piece neonmeridian        # play Neon Meridian
../reaper.sh --render --piece neonmeridian # render/verify it
```

Play mode regenerates the project under `$WIN_MUSIC\<Title>\` (the Windows
Music folder for the account `../reaper.sh` runs under, e.g.
`C:\Users\<you>\Music`; set `WIN_MUSIC` to override it),
opens REAPER with a self-deleting autoplay startup script, and leaves
REAPER open. Render mode bounces the piece offline through the installed
plug-in, checks every engine and envelope, writes `build/<Title>.wav`
alongside the `build/<Title>.RPP` that produced it (the exact project
REAPER rendered, so the two can never drift),
and compares it section by section against the CPython preview.
