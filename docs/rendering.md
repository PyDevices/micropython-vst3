# Hearing what you wrote

There are four ways to turn a project into audio, and they are not
alternatives - they answer different questions. This page is which one to
reach for. How to run each lives with the tool.

## Which one

| You want | Run | It needs |
|---|---|---|
| A composer project, on any machine | `from_yaml.py song.yaml song.wav` | pip packages |
| A soundtrack piece, checking the script path | `composer/preview.py --piece NAME` | pip packages, installed MPVST |
| Any `.RPP`, for real | `bounce.py song.rpp` | Reaper, installed MPVST |
| A soundtrack piece, for real | `reaper.sh --render --piece NAME` | Reaper, installed MPVST |

The two in the top half run in one CPython process and take roughly as long
as the music does - sixteen voices over two and a half minutes cost two and a
half minutes. The two in the bottom half load the plug-in, which starts a
MicroPython sidecar per instrument and effect, so they pay a startup cost per
slot before a note sounds.

Details: [the composer guide](../examples/reaper-composer/mpvst_composer/mpvst_composer_guide.md#-rendering)
for the first, [`tools/README.md`](../tools/README.md#composing-a-piece) for
the second, [`examples/soundtrack/README.md`](../examples/soundtrack/README.md)
and [`reaper/README.md`](../reaper/README.md) for the last two.

## The two offline paths are not the same offline

Both skip the DAW and the compiled engine, and both end up in the same DSP.
They differ in how the sound gets built, so they catch different mistakes.

`preview.py` runs the piece's **instrument scripts**, exec'd against the
`vstaudio` shim exactly the way the sidecar loads them. It goes through
`mpvst_instrument_adapter`, so the normalized host values cross the same
seam - which is why it needs MPVST installed even though no plug-in loads.
Reach for it when the question is about a script: does it register an output,
does a macro reach it, does the adapter hand it the units it expects.

`OfflineRenderer` skips the scripts and drives `audioinstruments` and
`audioeffects` directly, so it needs no bundle at all. Reach for it when the
question is about the music: are the notes where you meant them, is the
arrangement balanced, does the mix bus land where you set it.

## What offline does not prove

Neither offline path tells you the plug-in works. They share the DSP and
nothing else. The class IDs, the state chunk, the item timing, the send
topology and the macro resync are all things a project file only *asserts* -
a host has to honour them, and only a bounce shows whether one did.

They also do not prove a script sounds like the hardware it is named after,
or like anything in particular; only that it does not crash and is not
silent. Hearing it is still on you.

So: render offline while you are writing, bounce before you believe it. When
the two disagree, the bounce is right about the plug-in and the offline render
is right about the arithmetic, and the gap between them is the bug.

The gap is usually small. Sixteen-voice Canon comes out 150.00 s and
-14.36 LUFS offline against 150.00 s and -14.09 LUFS bounced.

## Measuring the result

```bash
python tools/audio_qc.py my_song.wav
```

Integrated loudness, true peak, and any silence. A digitally black file, a
silent head, or a hole in the middle almost always means a plug-in did not
load rather than anything about your music. Needs `numpy`, `soundfile`,
`pyloudnorm` and `scipy`.

It checks nothing on its own account and it is not part of any render - point
it at a bounce and an offline render of the same project when you want to know
how far apart they are.
