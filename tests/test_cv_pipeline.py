"""Tests for cv_pipeline.py — HSV masking, morphology, ROI."""
from __future__ import annotations

import numpy as np
import pytest

from src import cv_pipeline


def _synth_frame_with_colored_blob(
    h: int = 240, w: int = 320,
    blob_center: tuple[int, int] = (160, 120),
    blob_radius: int = 12,
    blob_bgr: tuple[int, int, int] = (0, 255, 0),  # pure green
    ambient_bgr: tuple[int, int, int] = (80, 80, 80),
) -> np.ndarray:
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[:, :] = ambient_bgr
    y, x = np.ogrid[:h, :w]
    mask = (x - blob_center[0]) ** 2 + (y - blob_center[1]) ** 2 <= blob_radius ** 2
    frame[mask] = blob_bgr
    return frame


class TestFindRoiColor:
    def test_finds_green_blob(self):
        frame = _synth_frame_with_colored_blob(
            blob_center=(200, 100), blob_radius=10, blob_bgr=(0, 255, 0),
        )
        roi = cv_pipeline.find_roi(frame, mode="color")
        assert roi is not None
        x, y, w, h = roi
        # Center of bounding box should be near (200, 100), within 5 px
        cx, cy = x + w // 2, y + h // 2
        assert abs(cx - 200) <= 5
        assert abs(cy - 100) <= 5

    def test_returns_none_when_no_green(self):
        frame = _synth_frame_with_colored_blob(
            blob_bgr=(0, 0, 255),  # red, not green
        )
        roi = cv_pipeline.find_roi(frame, mode="color")
        assert roi is None

    def test_rejects_invalid_mode(self):
        frame = _synth_frame_with_colored_blob()
        with pytest.raises(ValueError):
            cv_pipeline.find_roi(frame, mode="bogus")


class TestFindRoiWhite:
    def test_finds_bright_white_blob(self):
        frame = _synth_frame_with_colored_blob(
            blob_center=(50, 50), blob_radius=15, blob_bgr=(250, 250, 250),
        )
        roi = cv_pipeline.find_roi(frame, mode="white")
        assert roi is not None
        x, y, w, h = roi
        cx, cy = x + w // 2, y + h // 2
        assert abs(cx - 50) <= 5
        assert abs(cy - 50) <= 5

    def test_white_mode_ignores_green(self):
        frame = _synth_frame_with_colored_blob(
            blob_bgr=(0, 255, 0),  # saturated green, not white
        )
        roi = cv_pipeline.find_roi(frame, mode="white")
        assert roi is None


class TestExtractIntensity:
    def test_extract_matches_manual_mean(self):
        frame = _synth_frame_with_colored_blob(
            blob_center=(100, 60), blob_radius=10, blob_bgr=(0, 255, 0),
        )
        roi = cv_pipeline.find_roi(frame, mode="color")
        assert roi is not None
        intensity = cv_pipeline.extract_intensity(frame, roi)
        # ROI is mostly pure green, V channel ≈ 255 there, some ambient edges
        assert 180.0 <= intensity <= 256.0
