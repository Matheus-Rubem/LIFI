"""Tests for frame.py (CRC-8, build_frame, parse_frame)."""
from __future__ import annotations

import pytest

from src import frame


class TestCrc8:
    def test_crc8_empty(self):
        assert frame.crc8(b"") == 0x00

    def test_crc8_single_byte_vector(self):
        # Reference vector for CRC-8 poly 0x07, init 0x00, no reflection:
        # crc8(b"\x00") = 0x00
        # crc8(b"\x01") = 0x07
        assert frame.crc8(b"\x01") == 0x07

    def test_crc8_ascii_A(self):
        # CRC-8 (poly 0x07, init 0x00, no reflection) of b"A" (0x41) = 0xC0
        assert frame.crc8(b"A") == 0xC0

    def test_crc8_known_vector_123456789(self):
        # "123456789" is a classic CRC test string. For CRC-8 poly 0x07 it's 0xF4.
        assert frame.crc8(b"123456789") == 0xF4

    def test_crc8_detects_single_bit_flip(self):
        original = b"Hello, PCOM!"
        crc_a = frame.crc8(original)
        corrupted = bytearray(original)
        corrupted[3] ^= 0x01  # flip one bit in byte 3
        assert frame.crc8(bytes(corrupted)) != crc_a


class TestBuildFrame:
    def test_build_frame_structure_empty_payload(self):
        result = frame.build_frame(b"")
        expected = (
            bytes([0x55] * 4)   # preamble
            + bytes([0x02])     # STX
            + bytes([0x00])     # LEN = 0
            + b""               # payload
            + bytes([frame.crc8(b"")])  # CRC (= 0x00)
            + bytes([0x03])     # ETX
        )
        assert result == expected

    def test_build_frame_structure_with_payload(self):
        payload = b"AB"
        result = frame.build_frame(payload)
        assert result[:4] == bytes([0x55] * 4)
        assert result[4] == 0x02  # STX
        assert result[5] == 2     # LEN
        assert result[6:8] == b"AB"
        assert result[8] == frame.crc8(payload)
        assert result[9] == 0x03  # ETX
        assert len(result) == 4 + 1 + 1 + 2 + 1 + 1

    def test_build_frame_max_payload(self):
        payload = b"X" * 120
        result = frame.build_frame(payload)
        assert len(result) == 128  # 4 + 1 + 1 + 120 + 1 + 1
        assert result[5] == 120

    def test_build_frame_rejects_oversize_payload(self):
        with pytest.raises(ValueError, match="payload too large"):
            frame.build_frame(b"X" * 121)
