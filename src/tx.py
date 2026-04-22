"""Host transmitter: read text from keyboard, build a frame, push it to Arduino.

Two modes:
  --port DEVICE    Write bytes to the given serial port (default for Arduino TX).
  --out PATH       Write bytes to a file; use with `scripts/tx_phone.sh` on Termux.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src import frame


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="LiFi TX: keyboard -> frame -> hardware")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--port", help="Serial port for Arduino TX (e.g. /dev/ttyUSB0)")
    group.add_argument("--out", help="Write frame bytes to this file (for phone TX)")
    ap.add_argument("--baud", type=int, default=115200, help="Serial baud (default 115200)")
    args = ap.parse_args(argv)

    writer = _open_writer(args)
    try:
        print("Type a message and press Enter. Ctrl+D (EOF) or Ctrl+C to quit.")
        while True:
            try:
                text = input("> ")
            except (EOFError, KeyboardInterrupt):
                print("\nbye")
                return 0
            try:
                payload = text.encode("ascii")
            except UnicodeEncodeError:
                print("error: message must be pure ASCII", file=sys.stderr)
                continue
            try:
                data = frame.build_frame(payload)
            except ValueError as e:
                print(f"error: {e}", file=sys.stderr)
                continue
            writer.write(data)
            if hasattr(writer, "flush"):
                writer.flush()
            print(f"(sent {len(data)} bytes: {len(payload)} payload + 8 overhead)")
            if args.out:
                return 0  # file mode writes one frame and exits
    finally:
        if hasattr(writer, "close"):
            writer.close()


def _open_writer(args: argparse.Namespace):
    if args.port:
        import serial  # imported here so tests can mock it
        return serial.Serial(args.port, args.baud, timeout=1)
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.open("wb")


if __name__ == "__main__":
    sys.exit(main())
