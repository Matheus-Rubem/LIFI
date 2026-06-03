"""Audio file input: read a WAV into a mono float array at a target rate."""
from __future__ import annotations

import wave

import numpy as np


def read_wav(path: str, target_fs: int) -> np.ndarray:
    """Read a WAV file into a mono float array in [-1, 1], resampled to target_fs."""
    with wave.open(path, "rb") as w:
        fr, sw, ch, n = w.getframerate(), w.getsampwidth(), w.getnchannels(), w.getnframes()
        raw = w.readframes(n)
    dtype = {1: np.int8, 2: np.int16, 4: np.int32}[sw]
    data = np.frombuffer(raw, dtype=dtype).astype(float)
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1)
    data /= float(2 ** (8 * sw - 1))                 # normalize to [-1, 1]
    if fr != target_fs and len(data) > 1:            # linear resample to target_fs
        m = int(len(data) * target_fs / fr)
        data = np.interp(np.linspace(0, len(data) - 1, m), np.arange(len(data)), data)
    return data
