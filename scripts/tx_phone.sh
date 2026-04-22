#!/data/data/com.termux/files/usr/bin/bash
# LiFi TX via phone flashlight (Termux).
# Usage: ./tx_phone.sh frame.bin
#
# Reads bytes from frame.bin (produced by `python -m src.tx --out frame.bin`)
# and emits them as UART-over-light via termux-torch at 200 ms per bit.
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: $0 frame.bin" >&2
  exit 2
fi

FRAME="$1"
BIT_TIME=0.2   # 200 ms

emit_bit() {
  if [ "$1" = "1" ]; then
    termux-torch on >/dev/null 2>&1
  else
    termux-torch off >/dev/null 2>&1
  fi
  sleep "$BIT_TIME"
}

# Start IDLE high
termux-torch on >/dev/null 2>&1
sleep 0.5

# Read byte-by-byte. `od -An -vtu1 -w1` prints one decimal byte per line.
while IFS= read -r byte; do
  byte=${byte## }
  [ -z "$byte" ] && continue
  emit_bit 0                                    # start bit
  for i in 0 1 2 3 4 5 6 7; do
    bit=$(( (byte >> i) & 1 ))                  # LSB-first
    emit_bit "$bit"
  done
  emit_bit 1                                    # stop bit
done < <(od -An -vtu1 -w1 "$FRAME")

# IDLE high after transmission
termux-torch on >/dev/null 2>&1
echo "done ($(wc -c <"$FRAME") bytes)"
