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

## Demo ao vivo — comandos que funcionam ⭐

O TX e o RX rodam **na máquina que tem o Arduino e a webcam** (no nosso
caso, Windows nativo — a porta COM e a câmera não aparecem no WSL). Use
**duas janelas** (PowerShell/terminal), cada uma com o venv ativado.

**Janela 1 — RX (recebe pela webcam):**

```
python -m src.rx --mode white --bit-rate 2.5 --exposure -6 --buffer-seconds 140
```

**Janela 2 — TX (envia pro Arduino):**

```
python -m src.tx --port COM4
```

…e digite a mensagem + Enter (ex.: `oi`, `sou`, `quero ser feliz`).
No Linux a porta costuma ser `/dev/ttyUSB0` ou `/dev/ttyACM0` em vez de `COM4`.

### O que cada flag faz (e por que importam)

| Flag | Para quê |
|------|----------|
| `--mode white` | LED **branco** (saturado). Use `--mode color` só para LED verde/azul. |
| `--bit-rate 2.5` | Tem que **casar com o firmware** (`tx.ino` roda a 2,5 bps). Mais amostras por bit ⇒ decodificação confiável mesmo a ~15-30 fps. |
| `--exposure -6` | **Trava a exposição** da webcam. Sem isso o LED piscando faz o fps oscilar (8↔31) e corrompe mensagens longas. Se a câmera ignorar, tente `-5`, `-7`, `-4`. |
| `--buffer-seconds 140` | Janela longa o bastante para caber uma frase inteira (a 2,5 bps, ~16 caracteres ≈ 116 s). |

### Receita rápida

1. Grave o `firmware/tx.ino` no Arduino (Arduino IDE → Upload). Fie o LED:
   **D8 → resistor 220–330 Ω → perna longa do LED → perna curta → GND**.
2. Sala **iluminada** (mantém o fps alto) e LED apontado pra webcam, ~20–40 cm.
3. Rode os dois comandos acima. O RX imprime `... ouvindo  fps~... preambulos=...`
   enquanto escuta, e `[OK ] 'sua mensagem'  BER~0.0%` ao decodificar.

> ⚠️ Só **um** programa por vez pode usar a `COM4`. Feche o Serial Monitor /
> o `tx.py` antes de **gravar** o firmware, e vice-versa.

## TX alternativo — lanterna do celular (Termux, modo white)

```
# No notebook: python -m src.tx --out frame.bin
# Transfira frame.bin pro celular (adb push frame.bin /sdcard/)
# No celular, no Termux: bash scripts/tx_phone.sh /sdcard/frame.bin
# De volta no notebook: python -m src.rx --mode white --bit-rate 2.5 --exposure -6
```

## Hardware bring-up

When hardware is available, follow the step-by-step checklist in
`docs/HARDWARE_VERIFICATION.md`. It covers Arduino upload, LED wiring,
bench checks, phone flashlight / Termux setup, and live validation for
both modes.

## Validation results

Validado no hardware (Arduino Uno + LED branco + webcam de notebook), modo
white a 2,5 bps com exposição travada (`--exposure -6`):

| Modo  | TX            | Mensagens decodificadas               | BER~ | Observações |
|-------|---------------|---------------------------------------|------|-------------|
| white | Arduino + LED | `oi` (×3), `li`, `sou`, `quero ser feliz` | 0%   | fps estável ~30 com `--exposure -6`; sala iluminada |

Notas das condições reais:
- **Sem `--exposure`**, o fps oscilava 8–31 fps e só mensagens curtas (~2 letras)
  fechavam o CRC. Com a exposição travada, o fps fixou em ~30 e frases inteiras
  passaram com BER 0%.
- Cada caractere leva ~4 s a 2,5 bps; `quero ser feliz` (16 chars) ≈ 2 min de
  transmissão. Mensagens > ~7 caracteres exigem `--buffer-seconds` maior.
- O receptor mede o **fps real** quadro a quadro e **reamostra o sinal para uma
  grade de tempo uniforme** antes de decodificar, tolerando o fps variável da webcam.

## Etapa 2 — melodia por luz (áudio)

Transmite uma melodia curta pelo mesmo canal de luz: microfone → notas
(banco de Goertzel) → LED → câmera → síntese → alto-falante. Detalhes em
`docs/superpowers/specs/2026-06-03-audio-por-luz-design.md`.

```
# RX (recebe e toca a melodia)
python -m src.audio_rx --mode white --bit-rate 2.5 --exposure -6 --buffer-seconds 140

# TX (grava do microfone e transmite)
python -m src.audio_tx --port COM4 --seconds 5
```

O receptor precisa do `--bit-rate 2.5` (casa com o firmware). Cada nota leva
~8 s no canal lento, então use melodias de ~6–8 notas. Checklist de hardware:
`docs/HARDWARE_VERIFICATION_AUDIO.md`.
