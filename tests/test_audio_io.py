import wave

import numpy as np

from src.audio_io import read_wav


def _write_wav(path, freq, seconds, fs):
    n = int(seconds * fs)
    t = np.arange(n) / fs
    pcm = (0.6 * np.sin(2 * np.pi * freq * t) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(fs)
        w.writeframes(pcm.tobytes())


def test_read_wav_resamples_and_normalizes(tmp_path):
    path = tmp_path / "tone.wav"
    _write_wav(path, freq=440.0, seconds=0.5, fs=44100)
    audio = read_wav(str(path), target_fs=8000)
    assert abs(len(audio) - int(0.5 * 8000)) <= 2     # resampled to 8 kHz
    assert audio.dtype == float and np.max(np.abs(audio)) <= 1.0
    # dominant frequency is preserved at ~440 Hz
    spec = np.abs(np.fft.rfft(audio))
    freqs = np.fft.rfftfreq(len(audio), 1 / 8000)
    assert abs(freqs[int(np.argmax(spec))] - 440.0) < 10.0
