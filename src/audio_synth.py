"""Synthesize a list of Notes into a float audio waveform (the DAC stage)."""
from __future__ import annotations

import numpy as np

from src.note_codec import REST, Note, midi_to_freq

PLAYBACK_RATE = 44100
STEP_MS = 50
ENVELOPE_MS = 10
AMPLITUDE = 0.3


def synthesize(notes: list[Note], rate: int = PLAYBACK_RATE) -> np.ndarray:
    segments: list[np.ndarray] = []
    env_n = int(rate * ENVELOPE_MS / 1000.0)
    for note in notes:
        n = int(rate * note.steps * STEP_MS / 1000.0)
        if note.pitch == REST or n <= 0:
            segments.append(np.zeros(max(n, 0)))
            continue
        t = np.arange(n) / rate
        seg = AMPLITUDE * np.sin(2 * np.pi * midi_to_freq(note.pitch) * t)
        if env_n > 0 and n >= 2 * env_n:        # fade in/out — no clicks
            ramp = np.linspace(0.0, 1.0, env_n)
            seg[:env_n] *= ramp
            seg[-env_n:] *= ramp[::-1]
        segments.append(seg)
    return np.concatenate(segments) if segments else np.zeros(0)
