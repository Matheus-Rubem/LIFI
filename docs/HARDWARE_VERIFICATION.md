# Hardware Verification Checklist

This doc covers the manual steps that require physical hardware and cannot be
automated from the plan. All software layers (Tasks 0-19 of the implementation
plan) are already passing unit + integration tests in CI-like conditions. What
follows are the checks you need to run when you have the Arduino + LED + phone
in hand.

---

## 0. Configuração final que funcionou ⭐ (leia primeiro)

Depois do *bring-up* real, esta é a configuração validada (Arduino Uno + LED
**branco** + webcam de notebook, no Windows nativo):

```
# Janela 1 — RX
python -m src.rx --mode white --bit-rate 2.5 --exposure -6 --buffer-seconds 140

# Janela 2 — TX
python -m src.tx --port COM4
# digite: oi   (ou sou, quero ser feliz, ...)
```

Ajustes descobertos durante o *bring-up* (todos já no código):

- **Bit rate 2,5 bps** (era 5 bps no spec): `tx.ino` agora usa `OCR1A_VAL = 6249`.
  A 5 bps, uma webcam a ~15-20 fps tinha só ~3 amostras/bit e o CRC quase nunca
  fechava. A 2,5 bps são ~7-12 amostras/bit. **O `--bit-rate 2.5` do RX precisa
  casar com o firmware.**
- **`--exposure -6`**: o LED piscando fazia a auto-exposição da webcam oscilar o
  fps (8↔31 fps), corrompendo mensagens longas. Travar a exposição fixa o fps em
  ~30. Se a câmera ignorar `-6`, tente `-5`, `-7`, `-4`.
- **Reamostragem por timestamp**: o RX mede o fps real e reamostra o sinal para
  uma grade uniforme antes de decodificar (tolera fps variável).
- **ROI travada no LED**: o detector trava na posição do LED e segura, em vez de
  pular para o fundo claro quando o LED apaga (cada bit 0).
- **LED branco usa `--mode white`** (não `color`). `color` é só para LED verde/azul.

---

## 1. Arduino + LED bench test (mode color)

**Hardware:** Arduino Uno/Nano, green or blue LED, 220 Ω resistor, jumper wires.

**Wiring:**
- Arduino D8 → resistor (220 Ω) → LED anode (long leg)
- LED cathode (short leg) → GND

**Upload:**
1. Open `firmware/tx.ino` in Arduino IDE.
2. Tools → Board: Arduino Uno (or Nano).
3. Tools → Port: the port where Arduino is connected.
4. Sketch → Upload.

**First bench check (no RX yet):**
1. Open the Serial Monitor at 115200 baud, line ending "No line ending".
2. Type `UUUU` and press Enter (four bytes = `0x55` alternating preamble).
3. The LED should blink at 1.25 Hz — a clearly visible slow flicker for about 16 seconds
   (4 bytes × 10 bits × 400 ms each, at the 2.5 bps firmware rate).
4. After blinking stops, LED should remain solid-on (IDLE state).

**If LED stays dark or solid-on during `UUUU`:**
- Wrong polarity on LED? Short leg goes to GND.
- Wrong pin? Must be D8.
- Serial port correct? Check Arduino IDE's port selection.
- Baud rate? Must be 115200.

**Second bench check (tx.py → Arduino):**
1. Close the Arduino IDE Serial Monitor (only one process can hold the port).
2. Activate the Python venv: `source .venv/bin/activate`.
3. Run: `python -m src.tx --port /dev/ttyUSB0` (or `/dev/ttyACM0` — check `ls /dev/tty*`).
4. Type `OI` + Enter.
5. Terminal should print: `(sent 10 bytes: 2 payload + 8 overhead)`.
6. Observe LED: 40 fast alternating blinks (preamble), then a slower "dot-dash"-like pattern (STX, LEN, 'O', 'I', CRC, ETX).
7. Total visible sequence ~20 seconds.

---

## 2. RX — mode color live (Arduino → webcam)

**Hardware:** Notebook with a working webcam.

**Setup:**
- Place the Arduino LED 20–50 cm from the webcam, pointing roughly at the lens.
- Dim the ambient light slightly (turn off overhead lights if bright).

**Run:**
```bash
# Terminal 1: RX  (--bit-rate 2.5 must match the firmware; --exposure stabilizes fps)
source .venv/bin/activate
python -m src.rx --mode color --bit-rate 2.5 --exposure -6

# Terminal 2: TX  (use COM4 on Windows)
source .venv/bin/activate
python -m src.tx --port /dev/ttyUSB0
> OI
```

**Three windows should appear:** raw frame with red ROI rectangle on the LED;
binary mask (white blob on black); signal 1D plot showing the square wave during
the preamble.

**Success criteria:**
- Within ~20 seconds, the RX terminal prints `[OK ] 'OI'  ok=1  BER~0.0%`.
- Do it 3 times to confirm reliability.

**If CRC fails ([ERR]):**
- LED too bright (ROI saturated): add a second 220 Ω resistor in series, or move further away.
- LED too dim or ambient too bright: dim the room or close the webcam shutter partially (put your hand over the bottom half to block ambient).
- Try `--mode color` with blue LED by editing `src/cv_pipeline.py` DEFAULT_HUE_RANGE = HUE_BLUE.
- If webcam fps is not 30, pass `--fps 60` or the actual value.

---

## 3. TX phone flashlight setup (mode white)

**On your Android phone, one-time setup:**
1. Install [Termux](https://f-droid.org/packages/com.termux/) from F-Droid (NOT the Play Store version — it's outdated).
2. Install [Termux:API](https://f-droid.org/packages/com.termux.api/) from F-Droid.
3. In Termux, run:
   ```bash
   pkg update && pkg install termux-api coreutils
   ```
4. Open the Termux:API app (on the phone's home screen) and grant permissions (particularly Camera/Flashlight).
5. Test: `termux-torch on` should turn the flashlight on; `termux-torch off` turns it off.

**Push the TX script and a frame:**
```bash
# On the notebook
python -m src.tx --out /tmp/frame_hi.bin
> Hi
(sent 10 bytes: 2 payload + 8 overhead)

# Copy to phone via adb (enable USB debugging first) or any file transfer method
adb push /tmp/frame_hi.bin /sdcard/Download/
adb push scripts/tx_phone.sh /sdcard/Download/

# Alternative without adb: email, Telegram, or cloud drive
```

**On the phone in Termux:**
```bash
cp /sdcard/Download/tx_phone.sh ~
chmod +x ~/tx_phone.sh
~/tx_phone.sh /sdcard/Download/frame_hi.bin
```

Flashlight should blink for ~20 seconds and print `done (10 bytes)`.

---

## 4. RX — mode white live (phone → webcam)

**Run:**
```bash
# Terminal 1 on notebook
python -m src.rx --mode white --bit-rate 2.5 --exposure -6 --buffer-seconds 140
```

Point the phone's flashlight (or the Arduino white LED) at the webcam (30–50 cm,
slightly off-axis so it doesn't saturate). The three windows should appear; the
mask window should show a white blob on the light, and the red ROI box should
**lock onto it and hold** even as it blinks.

**Start the phone TX** (from the previous section).

**Success criteria:** within ~30 seconds (extra 10 s for OS jitter on the phone),
one of 3 attempts of "Hi" prints `[OK ] 'Hi'  ok=1  BER~0.0%`. Per spec §13, the
threshold for this mode is looser: 1 success out of 3 attempts.

**If it fails:**
- OS jitter may be too high. Try putting the phone on airplane mode to reduce
  background scheduling.
- Ambient light too bright. Try a darker room.
- Flashlight too bright (saturating). Cover part of the flashlight with your
  finger to dim it. Or increase distance.

---

## 5. Demo videos

For the apresentação, record screen captures of both modes working. Save to
`assets/videos_gravados/` (gitignored). Suggested recordings:

- `demo_color.mp4` — 60 s of typing `OI`, `PCOM`, `LIFI` into tx.py with Arduino TX.
- `demo_white.mp4` — 60 s of a `Hi` transmission via phone flashlight.

These become evidence in the relatorio.md. Without the recorded videos the
contingency plan §11 items 2-3 kick in.

---

## 6. Populate `README.md` validation table

After a successful run, update `README.md` section "Validation results" with
your real BER numbers. Template:

```markdown
## Validation results

| Mode  | TX             | Attempts | OK  | BER~ | Notes         |
|-------|----------------|----------|-----|------|---------------|
| color | Arduino + LED  | 3        | 3   | 0%   | sala escura   |
| white | Phone Termux   | 3        | 1   | 66%  | sala escura   |
```

Replace with actual numbers.

---

## 7. Optional — BER sweep across conditions

Record 30-s clips for different conditions:
- `assets/videos_gravados/color_dark_close.mp4` — sala escura, LED a 30 cm
- `assets/videos_gravados/color_ambient_close.mp4` — luz ambiente, LED a 30 cm
- `assets/videos_gravados/color_ambient_far.mp4` — luz ambiente, LED a 1 m
- `assets/videos_gravados/white_dark_close.mp4` — sala escura, lanterna a 30 cm

While recording, the TX is sending repeated `OI` messages via `tx.py`.

Then run the sweep:
```bash
for v in assets/videos_gravados/color_*.mp4; do
    python scripts/ber_sweep.py "$v" --mode color
done
python scripts/ber_sweep.py assets/videos_gravados/white_dark_close.mp4 --mode white
```

Record the results in the relatorio.md §5.2 table.
