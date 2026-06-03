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


# tests/test_pitch_detect.py (append)
from src.note_codec import Note, REST
from src.pitch_detect import audio_to_notes, detect_window, SAMPLE_RATE


def test_detect_window_returns_correct_midi():
    from src.note_codec import midi_to_freq
    win = _sine(midi_to_freq(60), 1000, SAMPLE_RATE)  # C4
    assert detect_window(win, SAMPLE_RATE) == 60


def test_detect_window_silence_is_rest():
    assert detect_window(np.zeros(1000), SAMPLE_RATE) == REST


def test_audio_to_notes_segments_two_held_notes():
    from src.note_codec import midi_to_freq
    fs = SAMPLE_RATE
    # 0.5 s of C4 then 0.5 s of E4
    a = _sine(midi_to_freq(60), int(0.5 * fs), fs)
    b = _sine(midi_to_freq(64), int(0.5 * fs), fs)
    notes = audio_to_notes(np.concatenate([a, b]), fs)
    pitches = [n.pitch for n in notes]
    assert 60 in pitches and 64 in pitches
    assert pitches.index(60) < pitches.index(64)
    # ~0.5 s each => ~10 steps of 50 ms (allow tolerance)
    for n in notes:
        if n.pitch in (60, 64):
            assert 7 <= n.steps <= 12


def test_audio_to_notes_drops_blips():
    from src.note_codec import midi_to_freq
    fs = SAMPLE_RATE
    blip = _sine(midi_to_freq(67), int(0.05 * fs), fs)   # 50 ms < MIN
    held = _sine(midi_to_freq(60), int(0.5 * fs), fs)
    notes = audio_to_notes(np.concatenate([blip, held]), fs)
    assert all(n.pitch != 67 for n in notes)


def test_octave_preference_picks_fundamental():
    from src.note_codec import midi_to_freq
    from src.pitch_detect import detect_window
    fs = SAMPLE_RATE
    f0 = midi_to_freq(50)                      # fundamental ~147 Hz
    n = 1000
    t = np.arange(n) / fs
    # 2nd harmonic slightly louder than the fundamental (a voice-like signal):
    # the bare bank would pick the octave up; the fundamental is still strong.
    sig = 0.5 * np.sin(2 * np.pi * f0 * t) + 0.6 * np.sin(2 * np.pi * 2 * f0 * t)
    assert detect_window(sig, fs) == 50        # not 62 (the octave up)


def test_adaptive_threshold_detects_a_quiet_tone():
    from src.note_codec import midi_to_freq
    fs = SAMPLE_RATE
    quiet = 0.02 * np.sin(2 * np.pi * midi_to_freq(64) * np.arange(int(0.6 * fs)) / fs)
    notes = audio_to_notes(quiet, fs)          # silence_rms=None -> adaptive
    assert any(n.pitch == 64 for n in notes)   # a fixed 0.01 floor would miss it


def test_audio_tx_module_imports():
    import src.audio_tx as atx
    assert hasattr(atx, "notes_to_serial")
    assert hasattr(atx, "main")
