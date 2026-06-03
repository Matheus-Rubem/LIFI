# src/pitch_detect.py
"""Pitch detection via a bank of Goertzel filters (one per musical note).

Goertzel computes the power at a single frequency with a 2nd-order IIR filter —
a narrow digital band-pass. A bank of them (one per semitone) is the digital
equivalent of a set of resonant LC circuits.
"""
from __future__ import annotations

import numpy as np

from src.note_codec import MIDI_MAX, MIDI_MIN, REST, Note, midi_to_freq

SAMPLE_RATE = 8000
HOP_MS = 50           # time granularity (also the note duration step)
WINDOW_MS = 125       # analysis window — wide enough to resolve low semitones
MIN_NOTE_STEPS = 2    # >= 100 ms to drop blips
SILENCE_RMS = 0.01    # below this RMS the window is silence


def goertzel_power(samples: np.ndarray, freq: float, fs: float) -> float:
    """Power at exactly `freq` (generalized Goertzel — no bin rounding)."""
    w = 2.0 * np.pi * freq / fs
    coeff = 2.0 * np.cos(w)
    s1 = 0.0
    s2 = 0.0
    for x in np.asarray(samples, dtype=float):
        s0 = x + coeff * s1 - s2
        s2 = s1
        s1 = s0
    return float(s1 * s1 + s2 * s2 - coeff * s1 * s2)
