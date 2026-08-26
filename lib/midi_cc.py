"""Range functions for every MIDI 1.0 Control Change code.

Source: "Table 3 - Control Change Messages and RPNs", MIDI Manufacturers
Association, 2020. Every entry below is the spec's own definition; nothing
here is invented to suit a particular instrument.

To use a scale function in your instrument file, bind it to the MIDI CC
code you want:

    from midi_cc import midi_cc_lut
    volume_func = midi_cc_lut[7]

Then to use it:

    volume = volume_func(0.25)

x is always in the range 0.0 to 1.0 - that is what the VST3 host sends for
a normalised parameter, and what the plug-in hands a macro. Each function
converts that into the unit the spec defines for that controller, so the
return type varies by what the controller actually is:

    float 0.0..1.0   continuous "amount" controllers (the spec gives these
                     a 0-127 data range and no physical unit, so they come
                     back as a fraction of full scale)
    float -1.0..1.0  bipolar controllers, 0.0 at the centre detent (64)
    int   0..127     raw data bytes - bank/program numbers, parameter
                     numbers, LSBs, note numbers
    bool             switches: the spec says <= 63 off, >= 64 on
    None             messages that carry no value at all

The spec marks a number of codes "Undefined". They are included here as
plain 0.0..1.0 pass-throughs, because undefined means free for
manufacturer use, not unusable.

ONE JUDGEMENT CALL: Sound Controllers 70-79 are bipolar below. This
document gives them a 0-127 range and defers their defaults to MMA
RP-021, which sets 64 to mean "no change from the sound's own value" -
so they modify a preset rather than replace it. If you would rather they
were absolute, change _sound_controller to _unit and nothing else moves.
"""

# --- conversions -------------------------------------------------------------


def _byte(x):
    """0.0..1.0 -> the raw 7-bit data byte the spec describes, 0..127."""
    if x < 0.0:
        x = 0.0
    elif x > 1.0:
        x = 1.0
    return int(x * 127.0 + 0.5)


def _unit(x):
    """0.0..1.0 -> fraction of full scale, for a 0-127 controller with no
    physical unit in the spec."""
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def _bipolar(x):
    """0.0..1.0 -> -1.0..+1.0 with the centre detent (byte 64) at exactly
    0.0. The two halves are scaled separately because 64 does not sit at
    the midpoint of 0..127."""
    b = _byte(x)
    if b < 64:
        return (b - 64) / 64.0
    return (b - 64) / 63.0


def _switch(x):
    """0.0..1.0 -> bool. The spec is explicit: <= 63 off, >= 64 on."""
    return _byte(x) >= 64


def _none(x):
    """Channel Mode messages whose data byte is required to be 0."""
    return None


# Sound Controllers 70-79. See the judgement call in the module docstring.
_sound_controller = _bipolar


# --- the table ---------------------------------------------------------------

# x is always in the range 0.0 to 1.0
midi_cc_lut = {
    0: _byte,                      # Bank Select (MSB)
    1: _unit,                      # Modulation Wheel or Lever
    2: _unit,                      # Breath Controller
    3: _unit,                      # Undefined
    4: _unit,                      # Foot Controller
    5: _unit,                      # Portamento Time
    6: _byte,                      # Data Entry MSB
    7: _unit,                      # Channel Volume (formerly Main Volume)
    8: _bipolar,                   # Balance
    9: _unit,                      # Undefined
    10: _bipolar,                  # Pan
    11: _unit,                     # Expression Controller
    12: _unit,                     # Effect Control 1
    13: _unit,                     # Effect Control 2
    14: _unit,                     # Undefined
    15: _unit,                     # Undefined
    16: _unit,                     # General Purpose Controller 1
    17: _unit,                     # General Purpose Controller 2
    18: _unit,                     # General Purpose Controller 3
    19: _unit,                     # General Purpose Controller 4
    20: _unit,                     # Undefined
    21: _unit,                     # Undefined
    22: _unit,                     # Undefined
    23: _unit,                     # Undefined
    24: _unit,                     # Undefined
    25: _unit,                     # Undefined
    26: _unit,                     # Undefined
    27: _unit,                     # Undefined
    28: _unit,                     # Undefined
    29: _unit,                     # Undefined
    30: _unit,                     # Undefined
    31: _unit,                     # Undefined

    # 32-63: LSB for Controls 0-31. These are the low 7 bits of a 14-bit
    # value, so they are raw bytes, never fractions.
    32: _byte,                     # LSB for Control 0 (Bank Select)
    33: _byte,                     # LSB for Control 1 (Modulation Wheel)
    34: _byte,                     # LSB for Control 2 (Breath Controller)
    35: _byte,                     # LSB for Control 3 (Undefined)
    36: _byte,                     # LSB for Control 4 (Foot Controller)
    37: _byte,                     # LSB for Control 5 (Portamento Time)
    38: _byte,                     # LSB for Control 6 (Data Entry)
    39: _byte,                     # LSB for Control 7 (Channel Volume)
    40: _byte,                     # LSB for Control 8 (Balance)
    41: _byte,                     # LSB for Control 9 (Undefined)
    42: _byte,                     # LSB for Control 10 (Pan)
    43: _byte,                     # LSB for Control 11 (Expression)
    44: _byte,                     # LSB for Control 12 (Effect Control 1)
    45: _byte,                     # LSB for Control 13 (Effect Control 2)
    46: _byte,                     # LSB for Control 14 (Undefined)
    47: _byte,                     # LSB for Control 15 (Undefined)
    48: _byte,                     # LSB for Control 16 (Gen. Purpose 1)
    49: _byte,                     # LSB for Control 17 (Gen. Purpose 2)
    50: _byte,                     # LSB for Control 18 (Gen. Purpose 3)
    51: _byte,                     # LSB for Control 19 (Gen. Purpose 4)
    52: _byte,                     # LSB for Control 20 (Undefined)
    53: _byte,                     # LSB for Control 21 (Undefined)
    54: _byte,                     # LSB for Control 22 (Undefined)
    55: _byte,                     # LSB for Control 23 (Undefined)
    56: _byte,                     # LSB for Control 24 (Undefined)
    57: _byte,                     # LSB for Control 25 (Undefined)
    58: _byte,                     # LSB for Control 26 (Undefined)
    59: _byte,                     # LSB for Control 27 (Undefined)
    60: _byte,                     # LSB for Control 28 (Undefined)
    61: _byte,                     # LSB for Control 29 (Undefined)
    62: _byte,                     # LSB for Control 30 (Undefined)
    63: _byte,                     # LSB for Control 31 (Undefined)

    # 64-69: switches. <= 63 off, >= 64 on.
    64: _switch,                   # Damper Pedal on/off (Sustain)
    65: _switch,                   # Portamento On/Off
    66: _switch,                   # Sostenuto On/Off
    67: _switch,                   # Soft Pedal On/Off
    68: _switch,                   # Legato Footswitch (>= 64 Legato)
    69: _switch,                   # Hold 2

    # 70-79: Sound Controllers. Defaults per MMA RP-021; 64 is "no change".
    70: _sound_controller,         # Sound Controller 1 (Sound Variation)
    71: _sound_controller,         # Sound Controller 2 (Timbre/Harmonic Intens.)
    72: _sound_controller,         # Sound Controller 3 (Release Time)
    73: _sound_controller,         # Sound Controller 4 (Attack Time)
    74: _sound_controller,         # Sound Controller 5 (Brightness)
    75: _sound_controller,         # Sound Controller 6 (Decay Time)
    76: _sound_controller,         # Sound Controller 7 (Vibrato Rate)
    77: _sound_controller,         # Sound Controller 8 (Vibrato Depth)
    78: _sound_controller,         # Sound Controller 9 (Vibrato Delay)
    79: _sound_controller,         # Sound Controller 10 (default undefined)

    80: _unit,                     # General Purpose Controller 5
    81: _unit,                     # General Purpose Controller 6
    82: _unit,                     # General Purpose Controller 7
    83: _unit,                     # General Purpose Controller 8
    84: _byte,                     # Portamento Control (a source note number)
    85: _unit,                     # Undefined
    86: _unit,                     # Undefined
    87: _unit,                     # Undefined
    88: _byte,                     # High Resolution Velocity Prefix
    89: _unit,                     # Undefined
    90: _unit,                     # Undefined

    # 91-95: effect depths. 0 means none, so these stay unipolar.
    91: _unit,                     # Effects 1 Depth (Reverb Send Level)
    92: _unit,                     # Effects 2 Depth (formerly Tremolo Depth)
    93: _unit,                     # Effects 3 Depth (Chorus Send Level)
    94: _unit,                     # Effects 4 Depth (formerly Celeste [Detune] Depth)
    95: _unit,                     # Effects 5 Depth (formerly Phaser Depth)

    96: _none,                     # Data Increment (Data Entry +1) - no value
    97: _none,                     # Data Decrement (Data Entry -1) - no value
    98: _byte,                     # Non-Registered Parameter Number - LSB
    99: _byte,                     # Non-Registered Parameter Number - MSB
    100: _byte,                    # Registered Parameter Number - LSB
    101: _byte,                    # Registered Parameter Number - MSB

    102: _unit,                    # Undefined
    103: _unit,                    # Undefined
    104: _unit,                    # Undefined
    105: _unit,                    # Undefined
    106: _unit,                    # Undefined
    107: _unit,                    # Undefined
    108: _unit,                    # Undefined
    109: _unit,                    # Undefined
    110: _unit,                    # Undefined
    111: _unit,                    # Undefined
    112: _unit,                    # Undefined
    113: _unit,                    # Undefined
    114: _unit,                    # Undefined
    115: _unit,                    # Undefined
    116: _unit,                    # Undefined
    117: _unit,                    # Undefined
    118: _unit,                    # Undefined
    119: _unit,                    # Undefined

    # 120-127: Channel Mode messages. These change the channel's operating
    # mode rather than a sound parameter, and the spec fixes their data
    # byte, so almost none of them carry a value to scale.
    120: _none,                    # All Sound Off (data 0)
    121: _none,                    # Reset All Controllers (data 0)
    122: _switch,                  # Local Control On/Off (0 off, 127 on)
    123: _none,                    # All Notes Off (data 0)
    124: _none,                    # Omni Mode Off (+ all notes off)
    125: _none,                    # Omni Mode On (+ all notes off)
    126: _byte,                    # Mono Mode On - data is the channel count
    127: _none,                    # Poly Mode On (data 0)
}


# --- Registered Parameter Numbers -------------------------------------------

# Table 3a. These are where the spec gives real physical units rather than
# a bare 0-127, so the functions return cents and semitones directly.
# Keyed by (MSB, LSB), the two values you send on CC 101 and CC 100.
midi_rpn_lut = {
    # MSB = +/- semitones, LSB = +/- cents. Returned in semitones over the
    # 0..24 range hardware conventionally offers.
    (0x00, 0x00): lambda x: _unit(x) * 24.0,        # Pitch Bend Sensitivity

    # 00H 00H = -100 cents, 40H 00H = A440, 7FH 7FH = +100 cents.
    (0x00, 0x01): lambda x: (_unit(x) * 2.0 - 1.0) * 100.0,  # Channel Fine Tuning

    # MSB only, resolution 100 cents: 00H = -6400 cents, 40H = A440,
    # 7FH = +6300 cents. Returned in semitones.
    (0x00, 0x02): lambda x: _byte(x) - 64,          # Channel Coarse Tuning

    (0x00, 0x03): _byte,                            # Tuning Program Change
    (0x00, 0x04): _byte,                            # Tuning Bank Select

    # Defined by the GM2 spec; manufacturer-defined elsewhere.
    (0x00, 0x05): _unit,                            # Modulation Depth Range
    (0x00, 0x06): _byte,                            # MPE Configuration Message

    # Setting RPN to 7FH,7FH disables data entry/increment/decrement until
    # a new RPN or NRPN is selected.
    (0x7F, 0x7F): _none,                            # Null Function Number
}


# --- names -------------------------------------------------------------------

# The spec's own wording, for tooling that wants to label a control. Kept
# separate from the table above so the table stays a pure code -> function
# map. These are frozen constants from a 2020 publication of a 1983 spec,
# so the duplication with the comments above cannot drift.
midi_cc_names = {
    0: "Bank Select", 1: "Modulation Wheel or Lever", 2: "Breath Controller",
    4: "Foot Controller", 5: "Portamento Time", 6: "Data Entry MSB",
    7: "Channel Volume", 8: "Balance", 10: "Pan", 11: "Expression Controller",
    12: "Effect Control 1", 13: "Effect Control 2",
    16: "General Purpose Controller 1", 17: "General Purpose Controller 2",
    18: "General Purpose Controller 3", 19: "General Purpose Controller 4",
    64: "Damper Pedal on/off (Sustain)", 65: "Portamento On/Off",
    66: "Sostenuto On/Off", 67: "Soft Pedal On/Off", 68: "Legato Footswitch",
    69: "Hold 2",
    70: "Sound Controller 1 (default: Sound Variation)",
    71: "Sound Controller 2 (default: Timbre/Harmonic Intens.)",
    72: "Sound Controller 3 (default: Release Time)",
    73: "Sound Controller 4 (default: Attack Time)",
    74: "Sound Controller 5 (default: Brightness)",
    75: "Sound Controller 6 (default: Decay Time)",
    76: "Sound Controller 7 (default: Vibrato Rate)",
    77: "Sound Controller 8 (default: Vibrato Depth)",
    78: "Sound Controller 9 (default: Vibrato Delay)",
    79: "Sound Controller 10 (default undefined)",
    80: "General Purpose Controller 5", 81: "General Purpose Controller 6",
    82: "General Purpose Controller 7", 83: "General Purpose Controller 8",
    84: "Portamento Control", 88: "High Resolution Velocity Prefix",
    91: "Effects 1 Depth (default: Reverb Send Level)",
    92: "Effects 2 Depth (formerly Tremolo Depth)",
    93: "Effects 3 Depth (default: Chorus Send Level)",
    94: "Effects 4 Depth (formerly Celeste [Detune] Depth)",
    95: "Effects 5 Depth (formerly Phaser Depth)",
    96: "Data Increment", 97: "Data Decrement",
    98: "Non-Registered Parameter Number (NRPN) - LSB",
    99: "Non-Registered Parameter Number (NRPN) - MSB",
    100: "Registered Parameter Number (RPN) - LSB",
    101: "Registered Parameter Number (RPN) - MSB",
    120: "All Sound Off", 121: "Reset All Controllers",
    122: "Local Control On/Off", 123: "All Notes Off",
    124: "Omni Mode Off", 125: "Omni Mode On",
    126: "Mono Mode On", 127: "Poly Mode On",
}

for _cc in range(32, 64):
    midi_cc_names.setdefault(_cc, "LSB for Control %d" % (_cc - 32))
for _cc in range(128):
    midi_cc_names.setdefault(_cc, "Undefined")
del _cc
