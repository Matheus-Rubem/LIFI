"""Live receiver: webcam -> OpenCV pipeline -> DSP -> console.

Usage:
  python src/rx.py --mode {color|white} [--camera 0] [--input video.mp4]
                   [--buffer-seconds 12] [--fps 30]

With --input, reads a video file instead of the webcam (for offline validation).
"""
from __future__ import annotations

import argparse
import collections
import sys
from dataclasses import dataclass

import cv2
import numpy as np

from src import cv_pipeline, dsp, frame  # noqa: F401 — frame used via dsp


@dataclass
class RxStats:
    frames_received: int = 0
    frames_ok: int = 0
    frames_bad_crc: int = 0
    total_payload_bytes: int = 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="LiFi RX (webcam + OpenCV + DSP)")
    ap.add_argument("--mode", choices=list(cv_pipeline.MODES), default="color")
    ap.add_argument("--camera", type=int, default=0, help="Camera index (default 0)")
    ap.add_argument("--input", help="Video file to read instead of the camera")
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--buffer-seconds", type=float, default=12.0,
                    help="Length of the sliding 1D-signal buffer in seconds")
    args = ap.parse_args(argv)

    cap = cv2.VideoCapture(args.input if args.input else args.camera)
    if not cap.isOpened():
        print("error: cannot open video source", file=sys.stderr)
        return 2

    buf_len = int(args.buffer_seconds * args.fps)
    signal_buf: collections.deque[float] = collections.deque(maxlen=buf_len)
    tracker = cv_pipeline.ROITracker(smoothing_window=10)
    stats = RxStats()

    try:
        while True:
            ok, frame_bgr = cap.read()
            if not ok:
                break
            roi = cv_pipeline.find_roi(frame_bgr, mode=args.mode)
            roi = tracker.update(roi)
            intensity = cv_pipeline.extract_intensity(frame_bgr, roi) if roi else 0.0
            signal_buf.append(intensity)

            # Attempt decode once per second of new data.
            if len(signal_buf) == buf_len and stats.frames_received % int(args.fps) == 0:
                signal = np.asarray(signal_buf, dtype=float)
                result = dsp.decode_signal(signal, fs=args.fps, bit_rate=5.0)
                if result.crc_ok:
                    stats.frames_ok += 1
                    stats.total_payload_bytes += len(result.payload or b"")
                    text = (result.payload or b"").decode("ascii", errors="replace")
                    print(f"[OK ] '{text}'  (frames_ok={stats.frames_ok})")
                    signal_buf.clear()  # avoid re-decoding the same frame
                elif result.error and "preamble not found" not in result.error:
                    stats.frames_bad_crc += 1
                    print(f"[ERR] {result.error}")

            stats.frames_received += 1
    finally:
        cap.release()

    print(
        f"summary: received={stats.frames_received} ok={stats.frames_ok} "
        f"bad_crc={stats.frames_bad_crc} bytes={stats.total_payload_bytes}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
