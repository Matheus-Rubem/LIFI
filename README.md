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

Run as a module so relative imports resolve:

```
# Terminal 1 (TX): python -m src.tx --port /dev/ttyUSB0
# Terminal 2 (RX): python -m src.rx --mode color
```

## Live demo (mode white, phone flashlight via Termux)

```
# On the notebook: python -m src.tx --out frame.bin
# Transfer frame.bin to phone (adb push frame.bin /sdcard/)
# On phone in Termux: bash scripts/tx_phone.sh /sdcard/frame.bin
# Back on notebook: python -m src.rx --mode white
```

## Hardware bring-up

When hardware is available, follow the step-by-step checklist in
`docs/HARDWARE_VERIFICATION.md`. It covers Arduino upload, LED wiring,
bench checks, phone flashlight / Termux setup, and live validation for
both modes.

## Validation results

_Fill in after running the hardware checklist._

| Mode  | TX             | Attempts | OK  | BER~ | Notes |
|-------|----------------|----------|-----|------|-------|
| color | Arduino + LED  | -        | -   | -    | TBD   |
| white | Phone Termux   | -        | -   | -    | TBD   |
