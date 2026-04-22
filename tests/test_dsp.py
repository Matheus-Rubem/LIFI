"""Tests for dsp.py — moving average, AGC, clock recovery."""
from __future__ import annotations

import numpy as np
import pytest

from src import dsp
from tests.conftest import synth_signal_from_bits, uart_bits_for_byte


class TestMovingAverage:
    def test_moving_average_preserves_constant(self):
        signal = np.full(30, 100.0)
        filtered = dsp.moving_average(signal, m=3)
        # Interior samples unchanged; edges may differ due to 'same' mode.
        assert np.allclose(filtered[2:-2], 100.0)

    def test_moving_average_attenuates_noise(self):
        rng = np.random.default_rng(0)
        signal = 100.0 + rng.normal(0, 10, size=1000)
        filtered = dsp.moving_average(signal, m=3)
        # Moving-average with M=3 cuts variance ~1/M for white noise.
        assert filtered.std() < signal.std() * 0.7

    def test_moving_average_length_preserved(self):
        signal = np.zeros(100)
        assert dsp.moving_average(signal, m=3).shape == signal.shape

    def test_moving_average_m_equals_1_identity(self):
        signal = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        assert np.allclose(dsp.moving_average(signal, m=1), signal)


class TestComputeThreshold:
    def test_threshold_on_clean_bimodal(self, bits_for_preamble, frames_per_bit):
        preamble = synth_signal_from_bits(
            bits_for_preamble, frames_per_bit=frames_per_bit,
            high=200.0, low=50.0, noise_std=0.0,
        )
        thr = dsp.compute_threshold(preamble)
        assert 120.0 < thr.threshold < 130.0  # ≈ (200+50)/2 = 125
        assert thr.high > thr.low
        assert thr.high >= 180.0
        assert thr.low <= 70.0

    def test_threshold_robust_to_outliers(self, bits_for_preamble, frames_per_bit):
        preamble = synth_signal_from_bits(
            bits_for_preamble, frames_per_bit=frames_per_bit,
            high=200.0, low=50.0, noise_std=5.0,
        )
        # inject 3 huge spikes
        preamble[10] = 1000.0
        preamble[20] = 1000.0
        preamble[30] = 1000.0
        thr = dsp.compute_threshold(preamble)
        assert thr.threshold < 200.0  # not dragged up by outliers
        assert thr.high < 500.0


class TestFindPreamble:
    def test_finds_preamble_at_start(self, bits_for_preamble, frames_per_bit, fs, bit_rate):
        # Signal = leading silence + preamble + trailing silence
        silence_before = [1] * (frames_per_bit * 10)  # IDLE high
        silence_after = [1] * (frames_per_bit * 10)
        signal = np.concatenate([
            synth_signal_from_bits(
                [b for b in silence_before],
                frames_per_bit=1, high=200.0, low=50.0,
            ),
            synth_signal_from_bits(
                bits_for_preamble, frames_per_bit=frames_per_bit,
                high=200.0, low=50.0, noise_std=2.0,
            ),
            synth_signal_from_bits(
                [b for b in silence_after],
                frames_per_bit=1, high=200.0, low=50.0,
            ),
        ])
        idx = dsp.find_preamble(signal, fs=fs, bit_rate=bit_rate)
        assert idx is not None
        # The preamble starts at offset len(silence_before) = 60
        assert abs(idx - 60) <= frames_per_bit  # within 1 bit-time tolerance

    def test_returns_none_on_pure_noise(self, fs, bit_rate):
        rng = np.random.default_rng(1)
        signal = 100.0 + rng.normal(0, 5, size=500)
        idx = dsp.find_preamble(signal, fs=fs, bit_rate=bit_rate)
        assert idx is None

    def test_returns_none_on_constant(self, fs, bit_rate):
        signal = np.full(500, 200.0)
        idx = dsp.find_preamble(signal, fs=fs, bit_rate=bit_rate)
        assert idx is None
