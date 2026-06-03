# tests/test_pitch_detect.py
import numpy as np

from src.pitch_detect import goertzel_power


def _sine(freq, n, fs):
    t = np.arange(n) / fs
    return 0.5 * np.sin(2 * np.pi * freq * t)


def test_goertzel_peaks_at_the_present_tone():
    fs = 8000
    sig = _sine(440.0, 1000, fs)
    p_on = goertzel_power(sig, 440.0, fs)
    p_off = goertzel_power(sig, 660.0, fs)  # a different (absent) frequency
    assert p_on > 50 * p_off


def test_goertzel_near_zero_for_silence():
    fs = 8000
    assert goertzel_power(np.zeros(1000), 440.0, fs) < 1e-6
