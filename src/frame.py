"""Frame encoding/decoding: CRC-8, build_frame, parse_frame.

Protocol (see docs/superpowers/specs/2026-04-21-lifi-vlc-design.md §3):
    PREAMBLE (4 x 0x55) | STX 0x02 | LEN (1B) | PAYLOAD (<=120B) | CRC-8 | ETX 0x03
CRC-8 polynomial 0x07, init 0x00, no input/output reflection.
"""
from __future__ import annotations

from dataclasses import dataclass

PREAMBLE_BYTE = 0x55
PREAMBLE_LEN = 4
STX = 0x02
ETX = 0x03
MAX_PAYLOAD = 120


def crc8(data: bytes) -> int:
    """CRC-8, polynomial 0x07, init 0x00, non-reflected (CCITT/SMBus style)."""
    crc = 0x00
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x07) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


def build_frame(payload: bytes) -> bytes:
    """Assemble a full optical frame from the given payload.

    Frame layout: PREAMBLE(4) | STX | LEN | PAYLOAD | CRC-8(payload) | ETX
    """
    if len(payload) > MAX_PAYLOAD:
        raise ValueError(
            f"payload too large: {len(payload)} bytes (max {MAX_PAYLOAD})"
        )
    return (
        bytes([PREAMBLE_BYTE] * PREAMBLE_LEN)
        + bytes([STX, len(payload)])
        + payload
        + bytes([crc8(payload), ETX])
    )


@dataclass(frozen=True)
class ParsedFrame:
    ok: bool
    payload: bytes | None
    error: str | None


def parse_frame(body: bytes) -> ParsedFrame:
    """Parse a frame body (bytes starting at STX, preamble already stripped).

    Returns a ParsedFrame with ok=True and .payload if valid; otherwise
    ok=False and .error describing the first failure found.
    """
    if len(body) < 4:  # STX + LEN + CRC + ETX minimum
        return ParsedFrame(False, None, "truncated: need >=4 bytes")
    if body[0] != STX:
        return ParsedFrame(False, None, f"bad STX: got 0x{body[0]:02X}")

    length = body[1]
    if length > MAX_PAYLOAD:
        return ParsedFrame(False, None, f"LEN too large: {length} > {MAX_PAYLOAD}")

    expected_total = 1 + 1 + length + 1 + 1  # STX+LEN+payload+CRC+ETX
    if len(body) < expected_total:
        return ParsedFrame(
            False, None,
            f"truncated: need {expected_total} bytes, got {len(body)}",
        )

    payload = body[2 : 2 + length]
    received_crc = body[2 + length]
    if body[2 + length + 1] != ETX:
        return ParsedFrame(
            False, None,
            f"bad ETX: got 0x{body[2 + length + 1]:02X}",
        )

    computed_crc = crc8(payload)
    if received_crc != computed_crc:
        return ParsedFrame(
            False, None,
            f"CRC mismatch: got 0x{received_crc:02X}, expected 0x{computed_crc:02X}",
        )

    return ParsedFrame(True, payload, None)
