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


def _sample_bit(
    signal: np.ndarray,
    center: float,
    threshold: float,
    vote_half_width: int = 1,
) -> int | None:
    """Read the bit at `center` frames using a ±vote_half_width majority vote."""
    lo = int(round(center)) - vote_half_width
    hi = int(round(center)) + vote_half_width + 1
    if lo < 0 or hi > len(signal):
        return None
    window = signal[lo:hi]
    votes = (window > threshold).sum()
    return 1 if votes > (hi - lo) / 2 else 0


def find_end_of_preamble(
    signal: np.ndarray,
    preamble_start: int,
    bit_time_frames: float,
    threshold: float,
    n_preamble_bits: int = 40,
) -> int | None:
    """Scan bit slots after the preamble for the first violation of alternation.

    Returns the sample index of the CENTER of the STX start bit (== the first
    of the two consecutive equal bits), or None if no violation within the signal.
    """
    # bit N center = preamble_start + (N + 0.5) * Tb
    def bit_center(n: int) -> float:
        return preamble_start + (n + 0.5) * bit_time_frames

    # Sample preamble bits to know the expected alternation phase.
    prev = _sample_bit(signal, bit_center(n_preamble_bits - 1), threshold)
    n = n_preamble_bits
    while True:
        c = bit_center(n)
        if c + 1 >= len(signal):
            return None
        current = _sample_bit(signal, c, threshold)
        if current is None:
            return None
        if current == prev:
            # Two same-level bits in a row; the FIRST was the STX start bit.
            # Return the center of bit (n - 1).
            return int(round(bit_center(n - 1)))
        prev = current
        n += 1


def decode_uart_byte(
    signal: np.ndarray,
    start_bit_center: int,
    bit_time_frames: float,
    threshold: float,
) -> tuple[int | None, int]:
    """Decode one UART-framed byte starting at `start_bit_center`.

    Layout: start(0), 8 data LSB-first, stop(1). Returns (byte_value, next_start_center).
    byte_value is None if framing is invalid (start != 0 or stop != 1).
    """
    # Sanity check start bit
    start = _sample_bit(signal, start_bit_center, threshold)
    if start != 0:
        next_center = int(round(start_bit_center + 10 * bit_time_frames))
        return None, next_center

    byte = 0
    for i in range(8):
        center = start_bit_center + (i + 1) * bit_time_frames
        bit = _sample_bit(signal, center, threshold)
        if bit is None:
            next_center = int(round(start_bit_center + 10 * bit_time_frames))
            return None, next_center
        byte |= (bit & 1) << i  # LSB first

    # Stop bit must be 1
    stop_center = start_bit_center + 9 * bit_time_frames
    stop = _sample_bit(signal, stop_center, threshold)
    next_center = int(round(start_bit_center + 10 * bit_time_frames))
    if stop != 1:
        return None, next_center
    return byte, next_center
