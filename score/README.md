# Scores

Music performed entirely by the MicroPython VST3 instrument - no
third-party plug-ins, no samples. Every sound is a MicroPython script
running synthio and the audioif effects inside its own sidecar process.

Two pieces live here:

## Perihelion

A four-minute hybrid orchestral score (sixteen tracks): sub drone, Moog
bass ostinato, string and brass ensembles, choir, timpani, impacts, and
nineteen automation envelopes of filter motion. D minor, five sections,
resolving through a Picardy third.

## Automata

A five-and-a-half-minute electronic suite (twenty-four tracks, 4,600+
notes) built to outgrow Perihelion in every direction:

| | bars | meter/tempo | |
|---|---|---|---|
| I | 1-20 | 4/4 @84 | **Dawn Protocol** - air, glass, FM bells, choir hum, heartbeat kick |
| II | 1-32 | **7/8** @112 | **Assembly Line** - 2+2+3 polysynth ostinato, Reese bass, glitch percussion |
| III | 1-32 | 4/4 @126 | **Ignition** - four on the floor, the 303 wakes up, two-minute build |
| IV | 1-48 | 4/4 @128 | **Overdrive** - B minor supersaw anthem over the full kit, organ, brass stabs |
| V | 1-16 | 4/4 @64..48 | **Afterimage** - felt keys quote the Perihelion theme in D major; tape-stop ending |

What's in it that Perihelion doesn't have:

- A synthesized drum kit on separate tracks - kick, snare, hats (with
  real open/closed choking), claps, toms, shaker, glitch percussion -
  with swing, deterministic humanization, velocity ghost notes, and fills.
- A 303-style acid bass whose overlapping MIDI notes become genuine
  slides (the script glides pitch without retriggering the envelope),
  with accent handling and heavy cutoff/resonance automation.
- Transport-aware instruments: the sidechain pump pad reads
  `vstaudio.transport()` at note-on to phase-lock its duck to the beat,
  and every echo tunes its delay time to the host tempo by itself.
- A meter change into 7/8 and back, three tempos, a key modulation
  (A minor to B minor), and a closing tape-stop where the final chord
  falls two octaves as the tempo map ritards.
- Twenty-seven macro automation envelopes.

## Running them

```bash
./launch.sh                      # play Perihelion through the speakers
./launch.sh --piece automata     # play Automata
./launch.sh --render --piece automata   # headless verified bounce
```

The play mode regenerates the project under `C:\Users\bradb\Music\`,
opens REAPER with a self-deleting autoplay startup script, and leaves
REAPER open. The render mode bounces the piece offline through the
installed plug-in, checks every engine and envelope, and compares the
result against the CPython preview.

## How it fits together

- `composition.py` / `automata/composition.py` - each piece's single
  source of truth: tempo map (with time signatures), every note, gains,
  pans, swells, macro automation.
- `instruments/`, `automata/instruments/` - self-contained sidecar
  scripts, one per track.
- `generate_project.py --piece NAME` - writes the .RPP directly,
  embedding each instrument script in synthesized VST3 state chunks, so
  projects open with no environment variables.
- `render_preview.py --piece NAME` - renders the piece offline through
  the audioif CPython wheel (the same DSP the sidecars run) with
  per-section level analysis; `preview/` holds the vstaudio shim that
  lets instrument scripts run unmodified under CPython, including a
  simulated transport clock.
- `verify_song.py --piece NAME <bounce> <preview>` - compares a REAPER
  bounce against the preview section by section.
