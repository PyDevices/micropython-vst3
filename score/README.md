# Perihelion

A four-minute hybrid orchestral/synth score performed entirely by the
MicroPython VST3 instrument - sixteen tracks, sixteen sidecar instances,
no third-party plug-ins, no samples. Every sound is a MicroPython script
in `instruments/` running synthio and the audioif effects (chorus, echo,
freeverb) inside its own sidecar process.

In D minor, five sections:

| | bars | tempo | |
|---|---|---|---|
| A | 1-12 | 76 | **Adrift** - sub drone, breathing pad, glass halo, the four-note signal motif in bells |
| B | 13-28 | 78 | **Ignition** - the Moog ostinato lights up over a D pedal; low strings and the pulse arp join |
| C | 29-44 | 80/82 | **Approach** - theme in high strings, horns and timpani build, riser into the drop |
| D | 45-60 | 84 | **Perihelion** - brass theme over the full ensemble, lead doubles an octave up |
| E | 61-74 | 76→64 | **Afterglow** - choir and pads resolve through a Picardy third to D major |

The Moog-style motion the score asks for is host automation: nineteen
parameter envelopes drive the instruments' macro parameters - the bass and
arp cutoff/resonance sweeps, the intro's filter sunrise, the riser's
octave lift, brass brightness, echo sends.

## Playing it

```bash
./launch.sh
```

kills any stale REAPER, regenerates the project at
`C:\Users\bradb\Music\Perihelion\Perihelion.RPP`, and opens it in REAPER
with a self-deleting startup script that presses play about six seconds in
(the sidecars get a moment to boot). REAPER stays open afterwards.

```bash
./launch.sh --render
```

renders the piece headlessly through the installed plug-in instead:
verifies all sixteen engines come up, checks the automation envelopes,
bounces the full mix to `build/Perihelion.wav`, and compares it section by
section against the offline preview.

## How it fits together

- `composition.py` - the single source of truth: tempo map, every note,
  gains, pans, volume swells, macro automation.
- `instruments/*.py` - sixteen self-contained sidecar scripts. Each builds
  its wavetables, voices, filters, and effect chain, and reacts to
  note/parameter events from the host.
- `generate_project.py` - writes the .RPP directly, embedding each
  instrument script in synthesized VST3 state (the same byte layout REAPER
  saves), so the project opens with no environment variables.
- `render_preview.py` - renders the piece offline through the audioif
  CPython wheel (the same DSP the sidecars run) for fast iteration, with
  per-section level analysis and an at-most-8-simultaneous-tracks check.
- `verify_song.py` - compares a REAPER bounce against the preview.
- `preview/` - the vstaudio shim that lets instrument scripts run
  unmodified under CPython.

The composition keeps at most eight tracks sounding at once; the REAPER
bounce matches the preview within 1.3 dB per section.
