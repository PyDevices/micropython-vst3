# mpvst-macro-labels: Cutoff | Echo | Space
#
# Supersaw anthem lead: five saws fanned across the stereo field at
# -18/-9/0/+9/+18 cents, delayed vibrato, tempo-synced echo, hall.
# Monophonic - a new press takes over the line. Macros: cutoff, echo
# send, hall send.

import array
import math

import audiodelays
import audiofreeverb
import synthio
import vstaudio

SR = vstaudio.sample_rate()
TAU = 2.0 * math.pi


def make_table(parts, length=2048, gain=32000):
    vals = [0.0] * length
    for mult, amp in parts:
        step = TAU * mult / length
        for i in range(length):
            vals[i] += amp * math.sin(step * i)
    peak = 0.0
    for v in vals:
        a = v if v >= 0.0 else -v
        if a > peak:
            peak = a
    if peak <= 0.0:
        peak = 1.0
    out = array.array("h", bytearray(length * 2))
    scale = gain / peak
    for i in range(length):
        out[i] = int(vals[i] * scale)
    return out


def noise_table(length=8192, seed=1234567):
    out = array.array("h", bytearray(length * 2))
    state = seed
    for i in range(length):
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        out[i] = ((state >> 15) & 0xFFFF) - 32768
    return out


def logmap(v, lo, hi):
    return lo * ((hi / lo) ** v)


def beat_clock():
    info = vstaudio.transport()
    bpm = info[2] if info[2] and info[2] > 1.0 else 120.0
    return bpm, info[1] * bpm / 60.0


SAW = make_table([(n, 1.0 / (n ** 0.92)) for n in range(1, 27)])
CENTS = (-18.0, -9.0, 0.0, 9.0, 18.0)
PANS = (-0.5, -0.25, 0.0, 0.25, 0.5)
RISE = array.array("h", (0, 32767))

synth = synthio.Synthesizer(sample_rate=SR, channel_count=2)
cutoff = synthio.Math(synthio.MathOperation.SUM, 4200.0, 0.0, 0.0)
lp = synthio.Biquad(synthio.FilterMode.LOW_PASS, cutoff, Q=0.9)
env = synthio.Envelope(attack_time=0.02, decay_time=0.2,
                       release_time=0.15, attack_level=1.0,
                       sustain_level=0.88)

echo = audiodelays.Echo(max_delay_ms=1000, delay_ms=350, decay=0.4,
                        mix=0.22, sample_rate=SR, channel_count=2,
                        bits_per_sample=16, samples_signed=True,
                        buffer_size=2048, freq_shift=False)
verb = audiofreeverb.Freeverb(roomsize=0.86, damp=0.4, mix=0.24,
                              sample_rate=SR, channel_count=2,
                              bits_per_sample=16, samples_signed=True,
                              buffer_size=2048)
echo.play(synth)
verb.play(echo)

# (pitch, notes): a note-off only ends the line if it names the pitch
# that is currently sounding, so legato overlaps hand over cleanly no
# matter which order the host delivers same-tick offs and ons.
current = None


def release_current():
    global current
    if current is not None:
        for note in current[1]:
            synth.release(note)
        current = None


def handle_event(event_type, channel, note_id, data0, value0, value1,
                 sample_position):
    global current
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        release_current()
        bpm, _ = beat_clock()
        want = 60000.0 / bpm * 1.5
        if abs(echo.delay_ms - want) > 4.0:
            echo.delay_ms = want
        hz = synthio.midi_to_hz(data0 + value1)
        amp = 0.09 + 0.11 * value0
        wobble = synthio.LFO(rate=5.2, scale=0.009)
        onset = synthio.LFO(waveform=RISE, once=True, rate=1.0 / 0.5,
                            scale=1.0, interpolate=True)
        vib = synthio.Math(synthio.MathOperation.PRODUCT, wobble, onset,
                           1.0)
        notes = []
        for cents, pan in zip(CENTS, PANS):
            notes.append(synthio.Note(hz * (2.0 ** (cents / 1200.0)),
                                      waveform=SAW, envelope=env,
                                      filter=lp, amplitude=amp,
                                      panning=pan, bend=vib))
        current = (data0, tuple(notes))
        for note in notes:
            synth.press(note)
    elif event_type in (vstaudio.EVENT_NOTE_OFF, vstaudio.EVENT_NOTE_ON):
        if current is not None and current[0] == data0:
            release_current()
    elif event_type == vstaudio.EVENT_PARAMETER:
        if data0 == 0:
            cutoff.a = logmap(value0, 900.0, 12000.0)
        elif data0 == 1:
            echo.mix = 0.45 * value0
        elif data0 == 2:
            verb.mix = 0.1 + 0.35 * value0


# Patch 1 (Program Change 0) is the sound this script's module-level
# defaults describe, so a fresh instance and Patch 1 are the same thing.
# piece.py also reads it: a macro a composition does not set resolves here
# rather than to 0.5. Derived by tools/derive_patches.py - see that file
# before editing these numbers by hand.
PATCHES = {
    0: ("Init", (
        0.594705, 0.488889, 0.4)),
}


def _apply_patch(index, channel=0, note_id=-1, sample_position=0):
    patch = PATCHES.get(index)
    if patch is None:
        return
    for macro_index, macro_value in enumerate(patch[1]):
        handle_event(vstaudio.EVENT_PARAMETER, channel, note_id,
                     macro_index, macro_value, 0.0, sample_position)


def _dispatch(event_type, channel, note_id, data0, value0, value1,
              sample_position):
    if event_type == vstaudio.EVENT_PROGRAM_CHANGE:
        _apply_patch(data0, channel, note_id, sample_position)
        return
    handle_event(event_type, channel, note_id, data0, value0, value1,
                 sample_position)


vstaudio.on_event(_dispatch)

vstaudio.output(verb)
