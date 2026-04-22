"""End-to-end test: synthesize a video of a blinking LED, run the full pipeline.

This exercises cv_pipeline + dsp + frame together. No hardware required.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from src import cv_pipeline, dsp, frame
from tests.conftest import uart_bits_for_byte


def _synth_blinking_video(
    path: Path,
    bits: list[int],
    frames_per_bit: int = 6,
    size: tuple[int, int] = (240, 320),  # h, w
    led_center: tuple[int, int] = (160, 120),  # x, y
    led_radius: int = 12,
    fps: float = 30.0,
) -> None:
    h, w = size
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, fps, (w, h))
    for b in bits:
        for _ in range(frames_per_bit):
            frame_bgr = np.full((h, w, 3), 60, dtype=np.uint8)  # ambient gray
            if b == 1:
                cv2.circle(frame_bgr, led_center, led_radius, (0, 255, 0), -1)
            writer.write(frame_bgr)
    writer.release()


def test_synthetic_video_decode_roundtrip(tmp_path):
    payload = b"Hi"
    full_frame = frame.build_frame(payload)
    bits = [1] * 30  # IDLE before
    for byte in full_frame:
        bits.extend(uart_bits_for_byte(byte))
    bits.extend([1] * 30)  # IDLE after

    video_path = tmp_path / "blink.mp4"
    _synth_blinking_video(video_path, bits)

    cap = cv2.VideoCapture(str(video_path))
    assert cap.isOpened()
    tracker = cv_pipeline.ROITracker(smoothing_window=5)
    intensities = []
    while True:
        ok, frame_bgr = cap.read()
        if not ok:
            break
        roi = cv_pipeline.find_roi(frame_bgr, mode="color")
        roi = tracker.update(roi)
        if roi:
            intensities.append(cv_pipeline.extract_intensity(frame_bgr, roi))
        else:
            intensities.append(0.0)
    cap.release()

    signal = np.asarray(intensities, dtype=float)
    result = dsp.decode_signal(signal, fs=30.0, bit_rate=5.0)
    assert result.crc_ok, f"decode failed: {result.error}"
    assert result.payload == payload
