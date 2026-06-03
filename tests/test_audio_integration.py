# tests/test_audio_integration.py
import numpy as np

from src import dsp, frame
from src.note_codec import Note, encode, decode
from src.audio_synth import synthesize, PLAYBACK_RATE
from tests.conftest import uart_bits_for_byte


def _led_signal(payload, fs=30.0, bit_rate=2.5):
    full = frame.build_frame(payload)
    bits = [1] * 20
    for byte in full:
        bits += uart_bits_for_byte(byte)
    bits += [1] * 20
    frames_per_bit = int(round(fs / bit_rate))
    sig = []
    for b in bits:
        sig += [float(b)] * frames_per_bit
    return np.array(sig) * 200 + 20


def test_notes_survive_the_full_light_channel():
    notes = [Note(60, 6), Note(64, 6), Note(67, 6)]
    payload = encode(notes)
    sig = _led_signal(payload)
    result = dsp.decode_signal(sig, fs=30.0, bit_rate=2.5)
    assert result.crc_ok, f"decode failed: {result.error}"
    assert decode(result.payload) == notes


def test_decoded_notes_synthesize_to_correct_pitches():
    notes = [Note(69, 20)]                    # A4
    payload = encode(notes)
    sig = _led_signal(payload)
    result = dsp.decode_signal(sig, fs=30.0, bit_rate=2.5)
    out = synthesize(decode(result.payload))
    spec = np.abs(np.fft.rfft(out))
    freqs = np.fft.rfftfreq(len(out), 1 / PLAYBACK_RATE)
    assert abs(freqs[int(np.argmax(spec))] - 440.0) < 5.0
