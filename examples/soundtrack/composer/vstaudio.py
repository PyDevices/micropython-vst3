"""CPython stand-in for the sidecar's vstaudio module.

The score's instrument scripts run unmodified in two places: inside the
MicroPython sidecar (where the real vstaudio usermod exists) and inside the
offline preview renderer, where this shim provides the same names on top of
the audioif CPython wheel. The preview harness drives a script by calling
_reset() before exec'ing it, then _deliver()/_pull() per block.

Event type values mirror protocol.h exactly.
"""

EVENT_NOTE_ON = 1
EVENT_NOTE_OFF = 2
EVENT_POLY_PRESSURE = 3
EVENT_PITCH_BEND = 4
EVENT_CONTROL_CHANGE = 5
EVENT_PARAMETER = 6
EVENT_CHANNEL_PRESSURE = 7
EVENT_TRANSPORT = 8
EVENT_PROGRAM_CHANGE = 9

_sample_rate = 48000
_handler = None
_output = None
_input = None
_transport = (False, 0.0, 120.0, 4, 4)


def _reset(sample_rate):
    global _sample_rate, _handler, _output, _input
    _sample_rate = int(sample_rate)
    _handler = None
    _output = None
    _input = None


def sample_rate():
    return _sample_rate


def on_event(handler):
    global _handler
    _handler = handler


def output(sample):
    global _output
    _output = sample


def clear_output():
    global _output
    _output = None


class _InputStream:
    """Finite stereo host-input stand-in for offline effect previews."""

    def __init__(self, pcm, sample_rate, chunk_bytes=2048):
        self._pcm = bytes(pcm)
        self._position = 0
        self._chunk_bytes = int(chunk_bytes)
        self.sample_rate = int(sample_rate)
        self.channel_count = 2
        self.bits_per_sample = 16
        self.samples_signed = True

    def _reset_buffer(self, single_channel_output=False, audio_channel=0):
        self._position = 0

    def _get_buffer(self, single_channel_output=False, audio_channel=0):
        start = self._position
        end = min(len(self._pcm), start + self._chunk_bytes)
        self._position = end
        status = 0 if end >= len(self._pcm) else 1
        return status, memoryview(self._pcm[start:end])


def _set_input(pcm):
    global _input
    _input = _InputStream(pcm, _sample_rate)


def input():
    if _input is None:
        raise RuntimeError("vstaudio input is not configured")
    return _input


def input_stats():
    if _input is None:
        return (0, 0, 0, False)
    return (len(_input._pcm) // 4, _input._position // 4, 0, True)


def error(_message):
    pass


def transport():
    return _transport


def _deliver(event_type, channel, note_id, data0, value0, value1,
             sample_position):
    if _handler is not None:
        _handler(event_type, channel, note_id, data0, value0, value1,
                 sample_position)


def _current_output():
    return _output
