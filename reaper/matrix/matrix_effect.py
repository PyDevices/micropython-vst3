MACRO_LABELS = ("Level")
"""Deterministic effect used by the DAW matrix.

Plays the host input back through an audiomixer voice at half level, so a
gate instrument feeding it at 0.125 must come out at 0.0625. Macro 01 is
accepted but unused; the fixed transform keeps the PCM check exact.
"""

import os

import audiomixer
import vstaudio

_log_path = os.getenv("MPVST_TEST_LOG")


def log(message):
    if not _log_path:
        return
    try:
        with open(_log_path, "a") as handle:
            handle.write(message + "\n")
    except OSError:
        pass


def handle_event(event_type, channel, note_id, data0, value0, value1,
                 sample_position):
    if event_type == vstaudio.EVENT_PARAMETER and data0 == 0:
        log("matrix_effect stats=%r" % (vstaudio.input_stats(),))


mixer = audiomixer.Mixer(voice_count=1, sample_rate=vstaudio.sample_rate(),
                         channel_count=2, bits_per_sample=16,
                         samples_signed=True, buffer_size=1024)
mixer.voice[0].play(vstaudio.input())
mixer.voice[0].level = 0.5
log("matrix_effect loaded stats=%r" % (vstaudio.input_stats(),))
vstaudio.on_event(handle_event)
vstaudio.output(mixer)
