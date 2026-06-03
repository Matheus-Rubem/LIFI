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
    ap.add_argument("--bit-rate", type=float, default=5.0,
                    help="Optical bit rate in bps. MUST match the firmware: the "
                         "current tx.ino runs at 2.5 Hz, so use --bit-rate 2.5.")
    ap.add_argument("--buffer-seconds", type=float, default=75.0,
                    help="Sliding time window (seconds). Must be longer than one "
                         "full transmission: a ~10-byte frame at 2.5 bps lasts "
                         "~56 s, so the default is 75 s. Raise for longer payloads "
                         "or lower bit rates.")
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

    # Time-windowed sliding buffers, trimmed by wall-clock seconds (not sample
    # count) so the window holds a fixed DURATION regardless of the webcam's
    # variable frame rate. The parallel timestamp buffer also lets us measure
    # the real sample rate, which the decoder's bit timing depends on.
    max_samples = int(args.buffer_seconds * 60) + 64  # memory safety cap
    signal_buf: collections.deque[float] = collections.deque(maxlen=max_samples)
    ts_buf: collections.deque[float] = collections.deque(maxlen=max_samples)
    tracker = cv_pipeline.ROITracker(smoothing_window=10)
    stats = RxStats()
    fs_eff = args.fps
    last_status: float | None = None

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
            # A live camera is timestamped by the wall clock; a video file is read
            # as fast as the CPU allows, so we synthesize uniform timestamps from
            # its nominal fps. Either way the buffer is trimmed by elapsed time.
            now_t = time.monotonic() if not args.input else stats.frames_received / args.fps
            ts_buf.append(now_t)
            while len(ts_buf) >= 2 and (ts_buf[-1] - ts_buf[0]) > args.buffer_seconds:
                ts_buf.popleft()
                signal_buf.popleft()
            if not args.input and len(ts_buf) >= 2 and (ts_buf[-1] - ts_buf[0]) > 0:
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

            # Try to decode once per ~second of capture, as long as we have a few
            # seconds of data. Early/empty attempts fail harmlessly; we suppress
            # their errors (they would flood the console) and instead print a
            # periodic "listening" heartbeat so the user sees it is alive.
            if (len(signal_buf) >= int(args.fps) * 4
                    and stats.frames_received % int(max(1, args.fps)) == 0):
                signal, decode_fs = _resample_uniform(
                    signal_buf, ts_buf, fallback_fs=args.fps,
                    live=not args.input,
                )
                result = dsp.decode_signal(signal, fs=decode_fs, bit_rate=args.bit_rate)
                if result.crc_ok:
                    stats.frames_ok += 1
                    stats.total_frames_attempted += 1
                    stats.total_payload_bytes += len(result.payload or b"")
                    text = (result.payload or b"").decode("ascii", errors="replace")
                    print(f"[OK ] '{text}'  ok={stats.frames_ok}  BER~{stats.ber*100:.1f}%")
                    signal_buf.clear()
                    ts_buf.clear()
                elif result.error and result.error.startswith("CRC mismatch"):
                    # Only a real corrupted frame counts toward BER. Partial reads
                    # while the buffer fills ("truncated", "STX not found", ...)
                    # are not transmission errors and must not inflate the stat.
                    stats.frames_bad_crc += 1
                    stats.total_frames_attempted += 1

            if last_status is None:
                last_status = now_t
            elif now_t - last_status >= 8.0:
                last_status = now_t
                span = (ts_buf[-1] - ts_buf[0]) if len(ts_buf) >= 2 else 0.0
                print(
                    f"... ouvindo  fps~{fs_eff:.1f}  buffer~{span:.0f}s  "
                    f"ok={stats.frames_ok}  tentativas={stats.total_frames_attempted}"
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


def _resample_uniform(
    signal_buf, ts_buf, fallback_fs: float, live: bool,
    grid_fs: float = 60.0,
):
    """Resample the sampled intensities onto a uniform time grid.

    A webcam's real frame rate drifts (dark scenes lengthen exposure, CPU load
    varies), so consecutive samples are NOT equally spaced in time. The decoder
    assumes uniform spacing, so we use the per-sample timestamps to interpolate
    onto a fixed `grid_fs` Hz grid. This removes timing jitter AND lifts the
    effective samples-per-bit, both of which the decoder needs.

    For video-file input (not live) timestamps are meaningless, so we return the
    raw signal at the nominal fps unchanged.
    """
    raw = np.asarray(signal_buf, dtype=float)
    if not live or len(ts_buf) != len(raw):
        return raw, fallback_fs
    ts = np.asarray(ts_buf, dtype=float)
    span = ts[-1] - ts[0]
    if span <= 0:
        return raw, fallback_fs
    n = max(2, int(span * grid_fs))
    t_uniform = ts[0] + np.arange(n) / grid_fs
    return np.interp(t_uniform, ts, raw), grid_fs


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
