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
MIN_NOTE_STEPS = 3    # >= 150 ms to drop blips (window bleed extends a 50 ms blip to 2 hops)
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

_CANDIDATES = list(range(MIDI_MIN, MIDI_MAX + 1))
_FREQS = {m: midi_to_freq(m) for m in _CANDIDATES}


def detect_window(window: np.ndarray, fs: float = SAMPLE_RATE,
                  silence_rms: float = SILENCE_RMS) -> int:
    """Return the dominant MIDI note in `window`, or REST if it is silence."""
    window = np.asarray(window, dtype=float)
    rms = float(np.sqrt(np.mean(window ** 2))) if window.size else 0.0
    if rms < silence_rms:
        return REST
    best_m = REST
    best_p = 0.0
    for m in _CANDIDATES:
        p = goertzel_power(window, _FREQS[m], fs)
        if p > best_p:
            best_p = p
            best_m = m
    return best_m


def audio_to_notes(audio: np.ndarray, fs: float = SAMPLE_RATE,
                   silence_rms: float = SILENCE_RMS) -> list[Note]:
    """Segment a float audio array ([-1,1]) into a list of Notes."""
    audio = np.asarray(audio, dtype=float)
    hop = int(round(fs * HOP_MS / 1000.0))
    win = int(round(fs * WINDOW_MS / 1000.0))
    if hop <= 0 or audio.size < hop:
        return []

    # Per-hop pitch over a trailing analysis window.
    pitches: list[int] = []
    for start in range(0, audio.size - hop + 1, hop):
        w0 = max(0, start + hop - win)
        pitches.append(detect_window(audio[w0:start + hop], fs, silence_rms))

    # Merge consecutive equal pitches into notes (steps = hop count).
    notes: list[Note] = []
    run_pitch = pitches[0]
    run_len = 1
    for p in pitches[1:]:
        if p == run_pitch:
            run_len += 1
        else:
            notes.append(Note(run_pitch, run_len))
            run_pitch, run_len = p, 1
    notes.append(Note(run_pitch, run_len))

    # Drop blips: non-rest notes shorter than MIN_NOTE_STEPS. (A blip between
    # two equal notes splits them rather than merging — acceptable here; the
    # melody is expected to use distinct, sustained notes.)
    kept = [n for n in notes if n.pitch == REST or n.steps >= MIN_NOTE_STEPS]
    return kept
