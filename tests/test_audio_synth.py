# tests/test_audio_synth.py
import numpy as np

from src.note_codec import Note, REST, midi_to_freq
from src.audio_synth import synthesize, PLAYBACK_RATE


def _dominant_freq(sig, fs):
    spec = np.abs(np.fft.rfft(sig))
    freqs = np.fft.rfftfreq(len(sig), 1 / fs)
    return freqs[int(np.argmax(spec))]


def test_synthesize_length_matches_duration():
    out = synthesize([Note(60, 8)])           # 8 * 50 ms = 0.4 s
    assert abs(len(out) - int(0.4 * PLAYBACK_RATE)) <= 2


def test_synthesize_dominant_frequency_matches_note():
    out = synthesize([Note(69, 20)])          # A4 = 440 Hz, 1 s
    f = _dominant_freq(out, PLAYBACK_RATE)
    assert abs(f - 440.0) < 5.0


def test_rest_is_silence():
    out = synthesize([Note(REST, 4)])
    assert np.max(np.abs(out)) < 1e-9


def test_no_clipping():
    out = synthesize([Note(60, 8), Note(64, 8), Note(67, 8)])
    assert np.max(np.abs(out)) <= 1.0


def test_audio_rx_module_imports_and_has_play():
    import src.audio_rx as arx
    assert hasattr(arx, "play_payload")
    assert hasattr(arx, "main")
