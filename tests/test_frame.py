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
