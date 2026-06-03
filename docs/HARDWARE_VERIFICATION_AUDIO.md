# Verificação de Hardware — Etapa 2 (áudio por luz)

Pré-requisito: etapa 1 funcionando (LED + câmera) e firmware a 2,5 bps.
Dependência nova: `pip install -r requirements.txt` (inclui `sounddevice`).

## 1. Teste só de áudio (sem luz)
1. Grave e sintetize localmente para validar mic + alto-falante:
   - `python -c "from src.pitch_detect import *; from src.audio_synth import *; import sounddevice as sd, numpy as np; a=sd.rec(int(3*8000),samplerate=8000,channels=1); sd.wait(); n=audio_to_notes(a.flatten()); print(n); w=synthesize(n); sd.play(w,44100); sd.wait()"`
   - Cante/assobie uma nota por ~1 s; confira que a nota detectada bate e o
     alto-falante reproduz.

## 2. Fim a fim (mic → luz → alto-falante)
Duas máquinas/janelas, como na etapa 1 (mesma webcam + LED):

```
# RX (recebe e toca)
python -m src.audio_rx --mode white --bit-rate 2.5 --exposure -6 --buffer-seconds 140

# TX (grava e transmite)
python -m src.audio_tx --port COM4 --seconds 5
```

1. No TX, cante 4–6 notas distintas (~0,5 s cada). Ele imprime a melodia
   detectada e transmite (~2 min piscando).
2. No RX, aguarde o buffer encher; ao decodificar, ele imprime `[MELODIA]` e
   toca os tons.
3. Sucesso: a sequência de notas tocada no RX corresponde à cantada no TX.

## Dicas
- Mantenha as notas distintas e sustentadas (≥ 0,4 s) e dentro de Dó3–Dó5.
- Limite a ~6–8 notas (canal lento). Para mais notas, aumente `--seconds`,
  `--max-notes` e `--buffer-seconds`.
- Sala iluminada + LED bem enquadrado (mesmos cuidados da etapa 1).
