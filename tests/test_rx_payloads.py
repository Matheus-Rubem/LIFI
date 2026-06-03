# tests/test_rx_payloads.py
import cv2
import numpy as np

from src import frame, rx
from tests.conftest import uart_bits_for_byte


def _write_blink_video(path, payload, fps=30.0, frames_per_bit=12):
    full = frame.build_frame(payload)
    bits = [1] * 20
    for byte in full:
        bits += uart_bits_for_byte(byte)
    bits += [1] * 20
    h, w = 240, 320
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    for b in bits:
        f = np.full((h, w, 3), 60, np.uint8)
        if b == 1:
            cv2.circle(f, (160, 120), 12, (0, 255, 0), -1)
        for _ in range(frames_per_bit):
            vw.write(f)
    vw.release()


def test_decoded_payloads_yields_payload_from_video(tmp_path):
    payload = b"\x3c\x06\x40\x06"             # two notes
    video = tmp_path / "blink.mp4"
    _write_blink_video(video, payload)
    args = rx._parse_args([
        "--mode", "color", "--input", str(video),
        "--fps", "30", "--bit-rate", "2.5", "--buffer-seconds", "80", "--no-gui",
    ])
    got = list(rx.decoded_payloads(args))
    assert payload in got
