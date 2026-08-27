MACRO_LABELS = ("Level", "Probe")

"""Deterministic instrument used by the Windows DAW matrix.

The script emits a constant signed 16-bit level so rendered PCM can be compared
exactly rather than approximately. A note-on opens the gate, a note-off closes
it, and Macro 01 scales the open level using the same rule as the native test
engine:

    level = 0.125 + 0.125 * macro01     while a note is held
    level = 0.0                         otherwise

At the default macro value of zero the open level is exactly 0.125, which is
4096/32768 and therefore exact in both int16 and float32.
"""

import array
import os

import audiocore
import vstaudio

FRAMES = 128
FULL_SCALE = 32768.0

_log_path = os.getenv("MPVST_TEST_LOG")


def log(message):
    if not _log_path:
        return
    try:
        with open(_log_path, "a") as handle:
            handle.write(message + "\n")
    except OSError:
        pass


_buffer = array.array("h", bytearray(FRAMES * 2))
_sample = audiocore.RawSample(_buffer,
                              sample_rate=vstaudio.sample_rate(),
                              channel_count=1)

_held = set()
_macro0 = 0.0


def _level():
    if not _held:
        return 0.0
    return 0.125 + 0.125 * _macro0


def _refresh():
    value = int(_level() * FULL_SCALE + 0.5)
    for index in range(FRAMES):
        _buffer[index] = value


def _key(channel, note_id, pitch):
    return (channel, note_id if note_id >= 0 else pitch)


def handle_event(event_type, channel, note_id, data0, value0, value1,
                 sample_position):
    global _macro0
    del value1, sample_position
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        _held.add(_key(channel, note_id, data0))
        _refresh()
    elif event_type == vstaudio.EVENT_NOTE_ON:
        _held.discard(_key(channel, note_id, data0))
        _refresh()
    elif event_type == vstaudio.EVENT_NOTE_OFF:
        _held.discard(_key(channel, note_id, data0))
        _refresh()
    elif event_type == vstaudio.EVENT_PARAMETER and data0 == 0:
        _macro0 = value0
        _refresh()


log("matrix_instrument loaded sample_rate=%d" % vstaudio.sample_rate())
_refresh()
vstaudio.on_event(handle_event)
vstaudio.output(_sample)
