"""The composer behind the soundtrack pieces beside this package.

A piece is a directory holding `composition.py` - the tempo map, the notes,
the gains, the automation - and any effects that piece alone uses. From one
of those you can go two ways:

    python -m composer.reaper Perihelion     a Reaper project
    python -m composer.preview Perihelion    a WAV, without Reaper

`preview` renders offline through the same DSP the plug-in runs, using the
CPython build of audioif, so you can hear a change without opening a DAW.
`reaper` writes the project you then hand to `../bounce.py`.

This is not the composer in `../../reaper-composer/`. That one is a framework
you write a song *with*; this one reads songs already written as modules. They
came from different hands and are kept apart on purpose.
"""
