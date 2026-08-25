# mpvst-macro-labels: Level | Probe

"""Edited variant of the matrix instrument.

Installing this over the original file and toggling Reload Script proves that a
reload picks up what is on disk now. The held level is a fixed 0.375 and
ignores Macro 01, so the rendered plateau distinguishes this source from the
original no matter what the macro happens to be set to.
"""

import array

import audiocore
import vstaudio

FRAMES = 128
HELD_LEVEL = 0.375

_buffer = array.array("h", bytearray(FRAMES * 2))
_sample = audiocore.RawSample(_buffer,
                              sample_rate=vstaudio.sample_rate(),
                              channel_count=1)

_held = set()


def _refresh():
    value = int((HELD_LEVEL if _held else 0.0) * 32768.0 + 0.5)
    for index in range(FRAMES):
        _buffer[index] = value


def _key(channel, note_id, pitch):
    return (channel, note_id if note_id >= 0 else pitch)


def handle_event(event_type, channel, note_id, data0, value0, value1,
                 sample_position):
    del value1, sample_position
    if event_type == vstaudio.EVENT_NOTE_ON and value0 > 0.0:
        _held.add(_key(channel, note_id, data0))
        _refresh()
    elif event_type in (vstaudio.EVENT_NOTE_ON, vstaudio.EVENT_NOTE_OFF):
        _held.discard(_key(channel, note_id, data0))
        _refresh()


_refresh()
vstaudio.on_event(handle_event)
vstaudio.output(_sample)
