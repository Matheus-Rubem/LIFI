"""Live receiver: webcam -> OpenCV pipeline -> DSP -> three-window UI + console.

Usage:
  python src/rx.py --mode {color|white} [--camera 0] [--input video.mp4]
                   [--buffer-seconds 12] [--fps 30] [--no-gui]

With --input, reads a video file instead of the webcam (for offline validation).
With --no-gui, skips all OpenCV windows (useful for tests and headless runs).
"""
from __future__ import annotations

import argparse
import collections
import sys
import time
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
    total_frames_attempted: int = 0  # decodes that reached CRC (ok or fail)

    @property
    def ber(self) -> float:
        if self.total_frames_attempted == 0:
            return 0.0
        return self.frames_bad_crc / self.total_frames_attempted


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="LiFi RX (webcam + OpenCV + DSP)")
    ap.add_argument("--mode", choices=list(cv_pipeline.MODES), default="color")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--input", help="Video file to read instead of the camera")
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--buffer-seconds", type=float, default=30.0,
                    help="Sliding buffer length. At 5 bps, 30 s = 150 bits = "
                         "enough for preamble + ~5-byte frame. Increase for "
                         "longer payloads.")
    ap.add_argument("--no-gui", action="store_true", help="Console only (for CI/tests)")
    ap.add_argument("--display-every", type=int, default=3,
                    help="Render the GUI windows every Nth frame. Sampling still "
                         "happens every frame; this only lightens the display so "
                         "the capture loop keeps a higher fps. Raise it if fps is low.")
    args = ap.parse_args(argv)

    cap = cv2.VideoCapture(args.input if args.input else args.camera)
    if not cap.isOpened():
        print("error: cannot open video source", file=sys.stderr)
        return 2
    if not args.input:
        # More frames per 200 ms bit = more reliable decode. Decoding needs
        # roughly >=4 samples/bit, i.e. >=20 fps at 5 bps. Best-effort: the
        # webcam may ignore these (and dark rooms drop fps via long exposure).
        cap.set(cv2.CAP_PROP_FPS, 30)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    buf_len = int(args.buffer_seconds * args.fps)
    signal_buf: collections.deque[float] = collections.deque(maxlen=buf_len)
    # Wall-clock timestamp per sample. The display loop is usually slower than
    # the nominal --fps, and the decoder's bit timing depends on the REAL rate,
    # so we measure it from these timestamps instead of trusting args.fps.
    ts_buf: collections.deque[float] = collections.deque(maxlen=buf_len)
    tracker = cv_pipeline.ROITracker(smoothing_window=10)
    stats = RxStats()
    fs_eff = args.fps

    if not args.no_gui:
        cv2.namedWindow("LiFi RX — raw", cv2.WINDOW_NORMAL)
        cv2.namedWindow("LiFi RX — mask", cv2.WINDOW_NORMAL)
        cv2.namedWindow("LiFi RX — signal 1D", cv2.WINDOW_NORMAL)

    try:
        while True:
            ok, frame_bgr = cap.read()
            if not ok:
                break
            mask = cv_pipeline.compute_mask(frame_bgr, mode=args.mode)
            roi = cv_pipeline.find_roi(frame_bgr, mode=args.mode)
            roi = tracker.update(roi)
            intensity = cv_pipeline.extract_intensity(frame_bgr, roi) if roi else 0.0
            signal_buf.append(intensity)
            # Only a LIVE camera samples in real time; a video file is read as
            # fast as the CPU allows, so wall-clock would misreport its fps.
            if not args.input:
                ts_buf.append(time.monotonic())
                if len(ts_buf) >= 2 and (ts_buf[-1] - ts_buf[0]) > 0:
                    fs_eff = (len(ts_buf) - 1) / (ts_buf[-1] - ts_buf[0])

            if not args.no_gui and stats.frames_received % max(1, args.display_every) == 0:
                display = frame_bgr.copy()
                if roi:
                    x, y, w, h = roi
                    cv2.rectangle(display, (x, y), (x + w, y + h), (0, 0, 255), 2)
                cv2.putText(
                    display,
                    f"mode={args.mode}  fps~{fs_eff:.1f}  ok={stats.frames_ok}  "
                    f"bad={stats.frames_bad_crc}  BER~{stats.ber*100:.1f}%",
                    (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (0, 255, 0), 2, cv2.LINE_AA,
                )
                cv2.imshow("LiFi RX — raw", display)
                cv2.imshow("LiFi RX — mask", mask)
                _draw_signal_plot(list(signal_buf), mode_label=args.mode)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

            if len(signal_buf) == buf_len and stats.frames_received % int(args.fps) == 0:
                signal = np.asarray(signal_buf, dtype=float)
                result = dsp.decode_signal(signal, fs=fs_eff, bit_rate=5.0)
                if result.crc_ok:
                    stats.frames_ok += 1
                    stats.total_frames_attempted += 1
                    stats.total_payload_bytes += len(result.payload or b"")
                    text = (result.payload or b"").decode("ascii", errors="replace")
                    print(
                        f"[OK ] '{text}'  ok={stats.frames_ok}  "
                        f"BER~{stats.ber*100:.1f}%"
                    )
                    signal_buf.clear()
                elif result.error and "preamble not found" not in result.error:
                    stats.frames_bad_crc += 1
                    stats.total_frames_attempted += 1
                    print(
                        f"[ERR] {result.error}  bad_crc={stats.frames_bad_crc}  "
                        f"BER~{stats.ber*100:.1f}%"
                    )

            stats.frames_received += 1
    finally:
        cap.release()
        if not args.no_gui:
            cv2.destroyAllWindows()

    print(
        f"summary: received={stats.frames_received} ok={stats.frames_ok} "
        f"bad_crc={stats.frames_bad_crc} bytes={stats.total_payload_bytes}"
    )
    return 0


def _draw_signal_plot(signal: list[float], mode_label: str) -> None:
    """Render the 1D signal as a third OpenCV window.

    Draws directly into a numpy canvas — no matplotlib to avoid thread issues
    when OpenCV's main loop already owns the display.
    """
    h, w = 200, 800
    canvas = np.full((h, w, 3), 255, dtype=np.uint8)
    if not signal:
        cv2.imshow("LiFi RX — signal 1D", canvas)
        return
    arr = np.asarray(signal, dtype=float)
    lo, hi = float(arr.min()), float(arr.max()) + 1e-9
    span = max(hi - lo, 1.0)
    # Downsample to width
    if len(arr) > w:
        idx = np.linspace(0, len(arr) - 1, w).astype(int)
        arr = arr[idx]
    xs = np.linspace(0, w - 1, len(arr)).astype(int)
    ys = (h - 10 - (arr - lo) / span * (h - 20)).astype(int)
    for i in range(1, len(xs)):
        cv2.line(canvas, (xs[i - 1], ys[i - 1]), (xs[i], ys[i]), (0, 0, 0), 1)
    cv2.putText(
        canvas, f"mode={mode_label}  samples={len(signal)}",
        (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA,
    )
    cv2.imshow("LiFi RX — signal 1D", canvas)


if __name__ == "__main__":
    sys.exit(main())
