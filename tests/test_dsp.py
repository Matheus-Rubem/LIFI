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
