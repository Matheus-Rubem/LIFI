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


@dataclass(frozen=True)
class Threshold:
    high: float
    low: float
    threshold: float


def compute_threshold(preamble_signal: np.ndarray) -> Threshold:
    """AGC via percentis 90/10 sobre o preamble (robusto a outliers)."""
    high = float(np.percentile(preamble_signal, 90))
    low = float(np.percentile(preamble_signal, 10))
    return Threshold(high=high, low=low, threshold=(high + low) / 2.0)


def find_preamble(
    signal: np.ndarray,
    fs: float = FS_DEFAULT,
    bit_rate: float = RB_DEFAULT,
    correlation_threshold: float = 0.4,
) -> int | None:
    """Locate the start of the preamble via correlation with a 2.5 Hz square wave.

    Returns the sample index where the preamble begins, or None if not found.
    """
    samples_per_bit = fs / bit_rate
    window_frames = int(round(samples_per_bit * 8))  # ~8 bits ≈ 48 samples
    if len(signal) < window_frames * 2:
        return None

    # Reference: alternating 0/1 bits at bit_rate, each bit samples_per_bit wide.
    ref_bits = []
    for i in range(int(window_frames / samples_per_bit) + 1):
        ref_bits.append(1 if i % 2 == 0 else -1)
    ref = np.repeat(ref_bits, int(round(samples_per_bit)))[:window_frames].astype(float)
    ref -= ref.mean()
    ref /= np.linalg.norm(ref) + 1e-12

    best_corr = -1.0
    best_idx = None
    for start in range(0, len(signal) - window_frames):
        window = signal[start : start + window_frames].astype(float)
        window = window - window.mean()
        norm = np.linalg.norm(window) + 1e-12
        corr = float(np.dot(window, ref) / norm)
        if corr > best_corr:
            best_corr = corr
            best_idx = start

    if best_corr < correlation_threshold:
        return None
    return best_idx


def estimate_bit_time_frames(
    preamble_signal: np.ndarray,
    threshold: float,
) -> float:
    """Estimate bit-time (in frames) from threshold crossings in the preamble.

    0x55 with UART framing produces an alternating 0,1,0,1,... pattern at Rb bps.
    Adjacent zero-crossings of the signal occur exactly one bit-time apart
    (the square wave has period 2*Tb but two transitions per period, spaced Tb).
    """
    above = preamble_signal > threshold
    crossings = np.where(np.diff(above.astype(int)) != 0)[0]
    if len(crossings) < 3:
        raise ValueError("not enough crossings to estimate Tb")
    deltas = np.diff(crossings)
    return float(np.median(deltas))
