"""OpenCV spatial pipeline: HSV + morphology + ROI + intensity extraction.

Two modes (spec §5.1):
  color: HSV hue range (green/blue) + saturation > 80.
  white: V > 200 AND S < 40 (bright + achromatic).
"""
from __future__ import annotations

from collections import deque

import cv2
import numpy as np

MODES = ("color", "white")

# Hue ranges in OpenCV (0-179). Green LED around ~50-70; blue around ~100-130.
HUE_GREEN = (40, 80)
HUE_BLUE = (90, 135)

# Active color hue range. Default to GREEN — adjust at runtime per hardware.
DEFAULT_HUE_RANGE = HUE_GREEN
DEFAULT_SAT_MIN_COLOR = 80
DEFAULT_V_MIN_WHITE = 200
DEFAULT_S_MAX_WHITE = 40
KERNEL_3 = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))


def _mask_color(hsv: np.ndarray, hue_range=DEFAULT_HUE_RANGE) -> np.ndarray:
    lo = np.array([hue_range[0], DEFAULT_SAT_MIN_COLOR, 40], dtype=np.uint8)
    hi = np.array([hue_range[1], 255, 255], dtype=np.uint8)
    return cv2.inRange(hsv, lo, hi)


def _mask_white(hsv: np.ndarray) -> np.ndarray:
    lo = np.array([0, 0, DEFAULT_V_MIN_WHITE], dtype=np.uint8)
    hi = np.array([179, DEFAULT_S_MAX_WHITE, 255], dtype=np.uint8)
    return cv2.inRange(hsv, lo, hi)


def _apply_morphology(mask: np.ndarray) -> np.ndarray:
    # Closing: dilate then erode to consolidate the blob.
    mask = cv2.dilate(mask, KERNEL_3, iterations=1)
    mask = cv2.erode(mask, KERNEL_3, iterations=1)
    return mask


def compute_mask(frame_bgr: np.ndarray, mode: str) -> np.ndarray:
    """Produce a binary mask of the light source for the given mode."""
    if mode not in MODES:
        raise ValueError(f"unknown mode: {mode!r}; must be one of {MODES}")
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    mask = _mask_color(hsv) if mode == "color" else _mask_white(hsv)
    return _apply_morphology(mask)


def find_roi(
    frame_bgr: np.ndarray, mode: str, min_area: int = 50
) -> tuple[int, int, int, int] | None:
    """Return (x, y, w, h) of the BRIGHTEST qualifying blob, or None if absent.

    We pick the brightest blob (highest mean V) rather than the largest because
    a lit room makes a white breadboard/reflections pass the white mask with a
    LARGER area than the LED itself — but the LED saturates to V~255, so it wins
    on brightness. This keeps the ROI locked on the light source, not the
    background.
    """
    mask = compute_mask(frame_bgr, mode)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = [c for c in contours if cv2.contourArea(c) >= min_area]
    if not candidates:
        return None
    value = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)[:, :, 2]

    def mean_brightness(contour) -> float:
        # Mean V over the blob's actual (masked) pixels, NOT its bounding box:
        # a round LED's bbox includes dark corners that would drag the mean
        # below a large, merely-bright background rectangle.
        x, y, w, h = cv2.boundingRect(contour)
        sub_v = value[y : y + h, x : x + w]
        sub_m = mask[y : y + h, x : x + w]
        vals = sub_v[sub_m > 0]
        return float(vals.mean()) if vals.size else 0.0

    brightest = max(candidates, key=mean_brightness)
    return cv2.boundingRect(brightest)


def extract_intensity(
    frame_bgr: np.ndarray, roi: tuple[int, int, int, int]
) -> float:
    """Mean of HSV V-channel inside the ROI (the spec's 1D brightness sample)."""
    x, y, w, h = roi
    patch = frame_bgr[y : y + h, x : x + w]
    if patch.size == 0:
        return 0.0
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    return float(hsv[:, :, 2].mean())


class ROITracker:
    """Smooth centroid jitter over a sliding window of recent ROIs."""

    def __init__(self, smoothing_window: int = 10) -> None:
        self._history: deque[tuple[int, int, int, int]] = deque(maxlen=smoothing_window)

    def update(
        self, roi: tuple[int, int, int, int] | None
    ) -> tuple[int, int, int, int] | None:
        if roi is None:
            if not self._history:
                return None
            return self._smoothed()
        self._history.append(roi)
        return self._smoothed()

    def _smoothed(self) -> tuple[int, int, int, int]:
        arr = np.array(self._history, dtype=float)
        x = int(round(arr[:, 0].mean()))
        y = int(round(arr[:, 1].mean()))
        w = int(round(arr[:, 2].mean()))
        h = int(round(arr[:, 3].mean()))
        return (x, y, w, h)
