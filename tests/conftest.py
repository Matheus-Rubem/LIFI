"""Shared pytest fixtures. Synthetic signal generator for DSP tests.

A real optical signal, as seen by the receiver after spatial filtering + intensity
extraction, is a 1D float array sampled at Fs Hz (default 30). Each bit slot is
~Fs/Rb = 6 frames wide. High level ≈ 200 (LED on), low level ≈ 50 (LED off), plus
gaussian noise.
"""
from __future__ import annotations

import numpy as np
import pytest


@pytest.fixture
def fs() -> float:
    return 30.0


@pytest.fixture
def bit_rate() -> float:
    return 5.0


@pytest.fixture
def frames_per_bit(fs, bit_rate) -> int:
    return int(round(fs / bit_rate))  # 6


@pytest.fixture
def bit_time_frames(fs, bit_rate) -> float:
    return fs / bit_rate  # 6.0


def synth_signal_from_bits(
    bits: list[int],
    frames_per_bit: int = 6,
    high: float = 200.0,
    low: float = 50.0,
    noise_std: float = 0.0,
    seed: int = 42,
) -> np.ndarray:
    """Render a list of optical bits (1=LED on, 0=LED off) into a 1D float signal.

    Each bit occupies `frames_per_bit` samples. Optionally adds gaussian noise.
    """
    rng = np.random.default_rng(seed)
    samples = []
    for b in bits:
        level = high if b == 1 else low
        samples.extend([level] * frames_per_bit)
    signal = np.array(samples, dtype=float)
    if noise_std > 0:
        signal += rng.normal(0.0, noise_std, size=signal.shape)
    return signal


@pytest.fixture
def bits_for_preamble() -> list[int]:
    """4 bytes of 0x55 with UART framing (LSB-first) = 40 alternating bits
    starting with 0 and ending with 1.

    Each 0x55 byte framed = start(0), 1,0,1,0,1,0,1,0 (LSB-first), stop(1)
                         = 0,1,0,1,0,1,0,1,0,1
    Four of these concatenated = perfectly alternating 40 bits.
    """
    one_byte = [0, 1, 0, 1, 0, 1, 0, 1, 0, 1]
    return one_byte * 4


def uart_bits_for_byte(value: int) -> list[int]:
    """Return the 10 UART bits for one byte: start(0), 8 data LSB-first, stop(1)."""
    bits = [0]
    for i in range(8):
        bits.append((value >> i) & 1)
    bits.append(1)
    return bits
