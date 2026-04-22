"""Replay a recorded video through the RX pipeline and log frames_ok/bad_crc.

Usage: python scripts/ber_sweep.py path/to/video.mp4 --mode color
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make `src` importable regardless of CWD when invoked as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from src import cv_pipeline, dsp  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--mode", choices=list(cv_pipeline.MODES), default="color")
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--buffer-seconds", type=float, default=30.0)
    args = ap.parse_args()

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print("error: cannot open video", file=sys.stderr)
        return 2

    tracker = cv_pipeline.ROITracker(smoothing_window=10)
    buf_len = int(args.buffer_seconds * args.fps)
    signal_buf: list[float] = []
    ok = 0
    bad = 0
    while True:
        r, f = cap.read()
        if not r:
            break
        roi = tracker.update(cv_pipeline.find_roi(f, mode=args.mode))
        signal_buf.append(cv_pipeline.extract_intensity(f, roi) if roi else 0.0)

    cap.release()

    arr = np.asarray(signal_buf, dtype=float)
    if len(arr) < buf_len:
        print(
            f"{args.video}: video too short ({len(arr)} < {buf_len} samples); "
            f"decoding the full signal as one attempt."
        )
        result = dsp.decode_signal(arr, fs=args.fps, bit_rate=5.0)
        if result.crc_ok:
            ok += 1
        elif result.error and "preamble not found" not in result.error:
            bad += 1
    else:
        step = int(args.fps)
        for start in range(0, len(arr) - buf_len + 1, step):
            result = dsp.decode_signal(
                arr[start : start + buf_len], fs=args.fps, bit_rate=5.0
            )
            if result.crc_ok:
                ok += 1
            elif result.error and "preamble not found" not in result.error:
                bad += 1

    total = ok + bad
    ber = (bad / total) if total else 0.0
    print(f"{args.video}: ok={ok} bad={bad} BER~{ber*100:.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
