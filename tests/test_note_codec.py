# tests/test_note_codec.py
from src.note_codec import Note, encode, decode, midi_to_freq, REST


def test_roundtrip_simple_melody():
    notes = [Note(60, 8), Note(64, 8), Note(67, 4)]
    assert decode(encode(notes)) == notes


def test_rest_roundtrips():
    notes = [Note(60, 4), Note(REST, 2), Note(62, 4)]
    assert decode(encode(notes)) == notes


def test_encode_is_two_bytes_per_note():
    assert len(encode([Note(60, 8), Note(62, 8)])) == 4


def test_decode_truncates_odd_trailing_byte():
    # An incomplete final pair (from a partial frame) is dropped.
    assert decode(b"\x3c\x08\x40") == [Note(60, 8)]


def test_decode_out_of_range_pitch_becomes_rest():
    # 0x05 (=5) is outside {0} U [48,72] -> treated as a rest.
    assert decode(b"\x05\x04") == [Note(REST, 4)]


def test_encode_clamps_steps_to_1_255():
    assert encode([Note(60, 0)]) == b"\x3c\x01"
    assert encode([Note(60, 999)]) == b"\x3c\xff"


def test_midi_to_freq_a4_is_440():
    assert abs(midi_to_freq(69) - 440.0) < 1e-6
    assert abs(midi_to_freq(60) - 261.6256) < 1e-3
