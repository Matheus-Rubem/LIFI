# src/audio_tx.py
"""TX side: record the mic, detect the melody, send the notes over the LED.

Usage:
  python -m src.audio_tx --port COM4 --seconds 5
The receiver must run with the matching bit rate (the firmware is 2.5 bps):
  python -m src.audio_rx --mode white --bit-rate 2.5 --exposure -6 --buffer-seconds 140
"""
from __future__ import annotations

import argparse
import sys

import numpy as np

from src import frame
from src.audio_rx import _describe
from src.note_codec import encode
from src.pitch_detect import SAMPLE_RATE, audio_to_notes


def notes_to_serial(payload: bytes, port: str, baud: int = 115200) -> None:
    """Frame the payload and write it to the serial port (reuses etapa-1 frame)."""
    import serial  # pyserial, already a dependency
    full = frame.build_frame(payload)
    with serial.Serial(port, baud, timeout=1) as ser:
        ser.write(full)
    print(f"(enviados {len(full)} bytes: {len(payload)} payload + "
          f"{len(full) - len(payload)} overhead)")


def record(seconds: float, fs: int = SAMPLE_RATE) -> np.ndarray:
    import sounddevice as sd
    print(f"Gravando {seconds:.0f}s... cante/assovie a melodia agora.")
    audio = sd.rec(int(seconds * fs), samplerate=fs, channels=1, dtype="float32")
    sd.wait()
    return audio.flatten()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="LiFi audio TX (mic -> notes -> LED)")
    ap.add_argument("--port", required=True, help="Serial port (e.g. COM4)")
    ap.add_argument("--seconds", type=float, default=5.0)
    ap.add_argument("--max-notes", type=int, default=6,
                    help="Cap the melody length (the link is slow ~2.5 bps). "
                         "6 notes fit the recommended RX --buffer-seconds 140; "
                         "raise both together for longer melodies.")
    args = ap.parse_args(argv)

    audio = record(args.seconds)
    notes = audio_to_notes(audio, SAMPLE_RATE)[: args.max_notes]
    if not notes:
        print("Nenhuma nota detectada (silêncio?). Tente de novo.", file=sys.stderr)
        return 1
    print(f"[MELODIA] {_describe(notes)}")
    notes_to_serial(encode(notes), args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
