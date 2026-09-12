# MPVST: The MicroPython VST

Welcome to **MPVST**—a revolutionary VST3 plugin that embeds a complete MicroPython interpreter directly into your DAW. 

Instead of dealing with opaque binary patches and rigidly compiled DSP logic, MPVST allows you to write, edit, and serialize audio instruments and effects using plain-text Python scripts. Whether you're a musician looking for rapid experimentation or a developer building programmatic audio pipelines, MPVST transforms your DAW into a live-coding environment.

---

## 🚀 Installation

Windows and Linux both ship, from the [releases page](https://github.com/PyDevices/mpvst/releases).

**Windows:** run `MPVST-<version>-windows-x86_64-setup.exe`. It installs for you rather than for the whole machine, so there is no administrator prompt, and the bundle lands in `%LOCALAPPDATA%\Programs\Common\VST3`. That also decides where the uninstaller turns up later: Settings → Apps → Installed apps.

**Linux:** unpack `MPVST-<version>-linux-x86_64.tar.gz` and run the `install.sh` inside it. It copies the bundle to `~/.vst3`; `--dir` puts it elsewhere and `--uninstall` takes it away again.

Then rescan plug-ins in your DAW — **a real rescan, not a restart**. Hosts cache what they found last time, and in Reaper that is Preferences → Plug-ins → VST → Re-scan.

There is more detail, including what to do when you want to hear it, on the page for your platform: [Windows](windows/README.md), [Linux](linux/README.md).

---

## 🎛️ Basic Usage in Reaper

Using MPVST is just like using any other VST3 plugin, but with a lot more flexibility under the hood.

1. **Pick an instrument.** MPVST does not install as one plug-in — every instrument and effect in the library shows up in your FX browser under its own name and category. Search for **TR-808**, or **Minimoog**, or **Tape Delay**, and drop it on a track like anything else.
2. **Open its editor.** You get a patch selector, a Bypass switch, an engine-status light, and a slider per macro, labelled with whatever that instrument calls its knobs. Click a control to focus it, then scroll — sideways adjusts, up and down move between controls.
3. **Play it.** From here it behaves like any other VST3: MIDI in, macros automate, the project saves and reopens.

> [!NOTE]
> Each of those named plug-ins is a two-line Python script that the plug-in builds when you instantiate it, and your project saves that script as plain text. That is why the list is not compiled in, and why adding an instrument is writing a script rather than rebuilding anything.

The two entries called **MPVST Script Host** are the odd ones out: they run whatever script you point them at, and with none pointed at them they make no sound — an empty slot you did not choose is meant to be obvious.

---

## 💻 Writing Custom Scripts (Advanced)

If you want to bypass the built-in UI and write your own custom Python audio chains, MPVST fully supports it! 

You can copy the `default_effect.py` or `default_instrument.py` templates from `Contents/x86_64-win` inside the installed bundle, edit them to define your own DSP chains using the `audioeffects` library, and point `MPVST_SCRIPT_PATH` at your copy before starting the DAW.

### The Standard Way vs. The Adapter Way

If you are manually scripting a simple static chain, you can instantiate effects directly:
```python
import audioeffects
import vstaudio

# Manually instantiate an effect
delay = audioeffects.create("TapeDelay", vstaudio.input(), vstaudio.sample_rate())
vstaudio.output(delay.output)
```

> [!TIP]
> **Pro-Tip: Use the Adapters!** 
> If you are building robust scripts that need to survive dynamic parameter changes (macros) without audio dropouts, you should use the built-in adapter modules (`mpvst_instrument_adapter` and `mpvst_effect_adapter`). 

The adapters are what the MPVST Editor Panel uses internally. They contain advanced logic to safely rebind the audio graph if an effect needs to rebuild itself during a parameter change (like a Phaser or Vibrato).

**Example using the Effect Adapter:**
```python
# mpvst-module: audioeffects.TapeDelay
import mpvst_effect_adapter

# The adapter safely instantiates the effect and wires it to the host
mpvst_effect_adapter.run("TapeDelay", mix=0.5, feedback=0.4)
```

Two pages go further than this one: [writing your own instruments and effects](writing-scripts.md), for what a script can declare and how macros reach it, and [generating projects](generating-projects.md), if you want to build `.RPP` files programmatically rather than by hand.

Happy patching!
