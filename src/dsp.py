"""DSP stage for the receiver: moving average, AGC, clock recovery."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# System parameters (mirror spec §6)
FS_DEFAULT = 30.0       # webcam frame rate (Hz)
RB_DEFAULT = 5.0        # optical bit rate (bps)


def moving_average(signal: np.ndarray, m: int = 3) -> np.ndarray:
    """FIR passa-baixa (janela retangular) de M taps. mode='same' preserva length."""
    if m <= 0:
        raise ValueError("m must be >= 1")
    kernel = np.ones(m) / m
    return np.convolve(signal, kernel, mode="same")
