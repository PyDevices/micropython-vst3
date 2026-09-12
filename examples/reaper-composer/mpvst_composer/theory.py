from enum import Enum
from typing import List


class Note(Enum):
    C = 0
    Cs = 1
    Db = 1
    D = 2
    Ds = 3
    Eb = 3
    E = 4
    F = 5
    Fs = 6
    Gb = 6
    G = 7
    Gs = 8
    Ab = 8
    A = 9
    As = 10
    Bb = 10
    B = 11


class Scale(Enum):
    MAJOR = [0, 2, 4, 5, 7, 9, 11]
    MINOR = [0, 2, 3, 5, 7, 8, 10]
    DORIAN = [0, 2, 3, 5, 7, 9, 10]
    PHRYGIAN = [0, 1, 3, 5, 7, 8, 10]
    LYDIAN = [0, 2, 4, 6, 7, 9, 11]
    MIXOLYDIAN = [0, 2, 4, 5, 7, 9, 10]
    LOCRIAN = [0, 1, 3, 5, 6, 8, 10]
    HARMONIC_MINOR = [0, 2, 3, 5, 7, 8, 11]
    MELODIC_MINOR = [0, 2, 3, 5, 7, 9, 11]
    PENTATONIC_MAJOR = [0, 2, 4, 7, 9]
    PENTATONIC_MINOR = [0, 3, 5, 7, 10]
    BLUES = [0, 3, 5, 6, 7, 10]


class Chord(Enum):
    TRIAD = [1, 3, 5]
    SEVENTH = [1, 3, 5, 7]
    NINTH = [1, 3, 5, 7, 9]
    SUS2 = [1, 2, 5]
    SUS4 = [1, 4, 5]


class TheoryEngine:
    def __init__(self, key: Note = Note.C, scale: Scale = Scale.MAJOR):
        self.key = key
        self.scale = scale

    def get_midi_note(self, scale_degree: int, octave: int = 4, accidental: int = 0) -> int:
        """
        Convert a scale degree (1-indexed) into a MIDI note number.
        Accidental: +1 for sharp, -1 for flat.
        """
        degree_idx = scale_degree - 1
        scale_length = len(self.scale.value)
        octave_offset = degree_idx // scale_length
        scale_idx = degree_idx % scale_length
        base_pc = self.key.value
        interval = self.scale.value[scale_idx]
        final_note = 12 + (octave + octave_offset) * 12 + base_pc + interval + accidental
        return max(0, min(127, final_note))

    def get_chord_degrees(self, root_degree: int, chord_type: Chord = Chord.TRIAD, inversion: int = 0) -> List[int]:
        """
        Returns a list of absolute scale degrees for a given chord built on the root_degree.
        E.g., root_degree=2, chord_type=TRIAD -> [2, 4, 6]
        inversion=1 (1st inversion), inversion=2 (2nd inversion), inversion=-1 (1st inversion down)
        """
        degrees = [root_degree + (interval - 1) for interval in chord_type.value]
        scale_length = len(self.scale.value)

        for _ in range(inversion):
            degrees.append(degrees.pop(0) + scale_length)

        for _ in range(-inversion if inversion < 0 else 0):
            degrees.insert(0, degrees.pop() - scale_length)

        return degrees
