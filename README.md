# LiFi via Câmera — VLC Course Project

PCOM course project (UABJ). Design spec: `docs/superpowers/specs/2026-04-21-lifi-vlc-design.md`.

## Install

```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run tests

```
pytest
```

## Live demo (mode color, Arduino + LED)

```
# Terminal 1 (TX): python src/tx.py --port /dev/ttyUSB0
# Terminal 2 (RX): python src/rx.py --mode color
```

## Live demo (mode white, phone flashlight via Termux)

```
# On the notebook: python src/tx.py --out frame.bin
# Transfer frame.bin to phone (adb push frame.bin /sdcard/)
# On phone in Termux: bash scripts/tx_phone.sh /sdcard/frame.bin
# Back on notebook: python src/rx.py --mode white
```
