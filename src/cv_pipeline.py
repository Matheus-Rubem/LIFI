"""OpenCV spatial pipeline: HSV + morphology + ROI + intensity extraction.

Two modes (spec §5.1):
  color: HSV hue range (green/blue) + saturation > 80.
  white: V > 200 AND S < 40 (bright + achromatic).
"""
from __future__ import annotations

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
    """Return (x, y, w, h) of the largest blob for the mode, or None if absent."""
    mask = compute_mask(frame_bgr, mode)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    largest = max(contours, key=cv2.contourArea)
    if cv2.contourArea(largest) < min_area:
        return None
    return cv2.boundingRect(largest)
