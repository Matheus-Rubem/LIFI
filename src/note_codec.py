# src/note_codec.py
"""Codec for a melody as a list of notes <-> bytes (the payload contract).

Each note is 2 bytes: [pitch][steps].
  pitch : MIDI note number in [48, 72], or REST (0) for silence.
  steps : duration in 50 ms steps, clamped to [1, 255].
"""
from __future__ import annotations

from dataclasses import dataclass

REST = 0
MIDI_MIN = 48
MIDI_MAX = 72


@dataclass(frozen=True)
class Note:
    pitch: int   # MIDI number, or REST for silence
    steps: int   # duration in 50 ms steps


def midi_to_freq(midi: int) -> float:
    """Frequency in Hz of a MIDI note number (A4 = 69 = 440 Hz)."""
    return 440.0 * 2.0 ** ((midi - 69) / 12.0)


def encode(notes: list[Note]) -> bytes:
    out = bytearray()
    for n in notes:
        pitch = n.pitch if (n.pitch == REST or MIDI_MIN <= n.pitch <= MIDI_MAX) else REST
        steps = max(1, min(255, n.steps))
        out.append(pitch)
        out.append(steps)
    return bytes(out)


def decode(payload: bytes) -> list[Note]:
    notes: list[Note] = []
    for i in range(0, len(payload) - 1, 2):  # drop an odd trailing byte
        pitch = payload[i]
        steps = payload[i + 1]
        if pitch != REST and not (MIDI_MIN <= pitch <= MIDI_MAX):
            pitch = REST
        notes.append(Note(pitch, steps))
    return notes
