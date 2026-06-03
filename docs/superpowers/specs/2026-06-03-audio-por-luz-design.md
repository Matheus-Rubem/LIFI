# Etapa 2 — Áudio (melodia) por Luz — Design Spec

**Data:** 2026-06-03
**Status:** aprovado para planejamento
**Branch:** `etapa2-audio-por-luz`
**Depende de:** Etapa 1 (LiFi via câmera) — `docs/superpowers/specs/2026-04-21-lifi-vlc-design.md`

---

## 1. Objetivo

Estender o link LiFi da etapa 1 para transmitir **uma melodia reconhecível por
luz**: um microfone captura alguns segundos de som, o sistema extrai a
**sequência de notas** (altura + duração), transmite essas notas como piscadas
do LED (reusando o canal da etapa 1), e do outro lado uma câmera lê as piscadas,
reconstrói as notas e as **sintetiza num alto-falante**.

**Decisão de escopo fundamental:** o canal LiFi por câmera é lento (~2,5 bps,
limitado pela taxa de quadros da webcam). Transmitir áudio PCM cru é inviável
(64 kbps–1,4 Mbps). Portanto **não transmitimos a forma de onda**, e sim a
**descrição simbólica da música** — a lista de notas. Cada nota ocupa ~2 bytes,
o que cabe no canal lento e **reaproveita integralmente a cadeia da etapa 1**.

Alinhamento com a tese (filtros digitais substituem analógicos): a detecção de
altura usa um **banco de filtros digitais de Goertzel** (um filtro estreito por
nota musical) — não um circuito analógico ressonante.

---

## 2. Arquitetura

```
[mic] → audio_tx.py → note_codec → payload(bytes) → frame.build_frame → serial → Arduino → LED
                                                                                              ↓ luz
[alto-falante] ← audio_rx.py ← note_codec ← payload(bytes) ← rx.decoded_payloads ← câmera ← (etapa 1)
                  (síntese)      (decode)
```

A etapa 1 (`frame.py`, `dsp.py`, `cv_pipeline.py`, `firmware/tx.ino`) é
**reusada sem alteração**. O único ajuste na etapa 1 é um **refactor mínimo e
preservador de comportamento** no `rx.py` (Seção 6).

### 2.1 Componentes novos

| Módulo | Responsabilidade | Depende de |
|--------|------------------|------------|
| `src/note_codec.py` | Converte `lista de notas ↔ bytes`. Puro, sem I/O. | — |
| `src/pitch_detect.py` | Banco de Goertzel: áudio → nota dominante por janela. | numpy |
| `src/audio_tx.py` | Mic → `pitch_detect` → segmenta notas → `note_codec` → envia pelo serial. | sounddevice, frame, note_codec, pitch_detect |
| `src/audio_rx.py` | Payload decodificado → `note_codec` → síntese → alto-falante. | sounddevice, note_codec, rx |

Cada módulo tem um propósito único, interface bem definida e é testável
isoladamente.

---

## 3. Formato das notas (o "contrato")

Cada nota é **2 bytes**:

| Byte | Campo | Significado |
|------|-------|-------------|
| 0 | `pitch` | Número MIDI da nota (48–72). **0 = silêncio (pausa)**. |
| 1 | `dur` | Duração em passos de 50 ms (1–255 → 50 ms a 12,75 s). |

O *payload* é a concatenação dos pares de uma melodia:
`[p0,d0, p1,d1, ..., pN,dN]`. Esse payload entra no quadro da etapa 1
exatamente como um texto entrava (`[PREAMBLE][STX][LEN][payload][CRC-8][ETX]`).

- **Faixa de notas:** MIDI 48 (Dó3, 130,81 Hz) a 72 (Dó5, 523,25 Hz) — 25 semitons.
- **Frequência de uma nota MIDI `m`:** `f = 440 · 2^((m − 69)/12)` Hz.
- **Pausa:** `pitch = 0` (fora da faixa válida) representa silêncio.

`note_codec` valida: payload com número ímpar de bytes é truncado ao último par
completo (robustez a quadro parcial); `pitch` fora de `{0} ∪ [48,72]` é tratado
como pausa.

---

## 4. TX — do microfone às notas (`audio_tx.py` + `pitch_detect.py`)

1. **Captura:** grava `--seconds` (padrão 5 s) do microfone a **8 kHz** mono
   (Nyquist 4 kHz cobre a faixa com folga).
2. **Janelamento:** passo (*hop*) de **50 ms** (granularidade de tempo), com
   **janela de análise de 125 ms** (1000 amostras a 8 kHz). A janela maior dá
   resolução de frequência ~8 Hz, suficiente para separar semitons graves
   (Dó3≈131 Hz tem semitons ~8 Hz); 50 ms (20 Hz) confundiria notas vizinhas.
3. **Banco de Goertzel** (`pitch_detect.py`): para cada janela, calcula a
   energia em cada uma das 25 frequências-alvo (uma por semitom), usando a
   forma generalizada (avalia exatamente em `f`, sem arredondar para *bin*). A
   nota vencedora é a de maior energia.
   - **Silêncio:** se a energia máxima ficar abaixo de um limiar (relativo ao
     piso de ruído da gravação), a janela é classificada como pausa.
4. **Segmentação:** junta janelas consecutivas de mesma nota numa única nota,
   somando as durações. Descarta notas com duração < **100 ms** (anti-blip).
5. **Codificação:** `note_codec.encode(notas)` → payload de bytes.
6. **Envio:** monta o quadro com `frame.build_frame(payload)` e escreve no
   serial (`--port`), reusando a lógica da etapa 1. **Não altera `tx.py`.**

`audio_tx` imprime a lista de notas detectadas (ex.: `Dó4 0.40s | Mi4 0.40s | …`)
antes de transmitir, para conferência.

### 4.1 Goertzel (por que, e como)

O algoritmo de Goertzel é um detector de energia numa única frequência — um
**filtro IIR de 2ª ordem** sintonizado. Um banco com um filtro por nota é um
**banco de filtros passa-faixa digitais**, o equivalente direto de um conjunto
de circuitos LC ressonantes — exatamente a substituição analógico→digital da
tese. É mais barato que uma FFT completa quando só interessam 25 frequências.

---

## 5. RX — das notas ao som (`audio_rx.py`)

1. Recebe cada payload decodificado pela etapa 1 (via `rx.decoded_payloads`,
   Seção 6).
2. `note_codec.decode(payload)` → lista de notas `(pitch, dur)`.
3. **Síntese:** para cada nota gera uma **senoide** na frequência da nota, com
   duração `dur·50 ms`, a 44,1 kHz, aplicando um **envelope de 10 ms** de
   ataque/decaimento (anti-clique). Pausa = silêncio do tamanho da duração.
4. Concatena os trechos e **toca pelo alto-falante** (sounddevice).
5. Imprime a melodia recebida (mesma notação do TX) para conferência.

---

## 6. Refactor mínimo no `rx.py` (preservador de comportamento)

Hoje `rx.main()` decodifica e **imprime** o payload no laço. Para o `audio_rx`
consumir os payloads sem duplicar o laço de câmera, extrai-se um gerador:

```python
def decoded_payloads(args) -> Iterator[bytes]:
    """Itera o laço de captura/decodificação e entrega cada payload decodificado."""
    ...  # o miolo atual de main(), dando `yield result.payload` em cada [OK]
```

- `rx.main()` passa a consumir `decoded_payloads(...)` e imprime, como hoje
  (comportamento idêntico — mesma saída no terminal).
- `audio_rx.py` consome o mesmo gerador e sintetiza.

Esse é o **único** toque na etapa 1; é aditivo/estrutural e ganha cobertura de
teste para o `rx.py` (hoje 0%).

---

## 7. Restrições conhecidas (canal lento)

- Cada nota = 2 bytes = ~8 s piscando. Tempo total ≈ `(2·notas + 8) bytes` à
  taxa de 2,5 bps. **Recomendação: melodias de ~6–8 notas** (um trecho
  reconhecível). Tabela:

  | Notas | Bytes | Tempo ~ | `--buffer-seconds` no RX |
  |------:|------:|---------|-------------------------:|
  | 4 | 16 | ~100 s | 120 |
  | 6 | 20 | ~120 s | 140 |
  | 8 | 24 | ~150 s | 180 |

- Melodias maiores exigiriam **fragmentar em vários quadros** — fora do escopo
  desta etapa (trabalho futuro).
- A captura usa a faixa Dó3–Dó5; notas fora dela são quantizadas ao extremo
  mais próximo (ou viram pausa se muito fracas).
- O canal/exposição da câmera continua exigindo os cuidados da etapa 1
  (`--bit-rate 2.5 --exposure -6` e iluminação estável).

---

## 8. Plano de testes (TDD, sem hardware)

| Alvo | Teste |
|------|-------|
| `note_codec` | Ida-e-volta `notas → bytes → notas`; pausas; lista vazia; payload de tamanho ímpar (trunca). |
| `pitch_detect` | Senoide sintética em frequência conhecida → nota MIDI correta; sequência de tons → sequência correta; silêncio → pausa; tom + ruído → robusto. |
| `audio_rx` (síntese) | Notas → áudio: pico de FFT na frequência esperada (tolerância de ½ semitom); duração total = Σ durações; sem estouro (clipping). |
| Integração ponta a ponta | `notas → codec → build_frame → sinal de LED sintético → dsp.decode_signal (etapa 1 real) → payload → codec → notas → síntese`; confere picos de FFT. |
| `rx.decoded_payloads` | Vídeo sintético (reusa helper da etapa 1) → entrega o payload correto. |

Captura de microfone e reprodução em alto-falante são verificação **manual de
hardware** (como a etapa 1), documentadas num checklist.

---

## 9. Dependências novas

- **`sounddevice`** — captura de microfone e reprodução, multiplataforma
  (PortAudio). Adicionar ao `requirements.txt`.
- `numpy` — já presente.

> Os testes automatizados **não** dependem de `sounddevice` em runtime: a
> síntese gera arrays numpy (testáveis); apenas a reprodução/captura ao vivo
> usam o dispositivo de áudio. A injeção de áudio nos testes é feita por arrays,
> sem abrir o dispositivo.

---

## 10. Estrutura de arquivos (nova)

```
src/
  note_codec.py        # encode/decode lista de notas <-> bytes
  pitch_detect.py      # banco de Goertzel: audio -> notas
  audio_tx.py          # mic -> notas -> serial (reusa frame.build_frame)
  audio_rx.py          # payload -> notas -> sintese -> alto-falante
  rx.py                # + decoded_payloads() (refactor preservador)

tests/
  test_note_codec.py
  test_pitch_detect.py
  test_audio_rx.py
  test_audio_integration.py   # laço completo reusando dsp da etapa 1

requirements.txt       # + sounddevice
docs/
  HARDWARE_VERIFICATION_AUDIO.md   # checklist manual (mic + alto-falante)
```

---

## 11. Mapeamento PCOM

| Componente | Conceito de PCOM |
|------------|------------------|
| Mic → tensão → janelas | Amostragem / sinal em banda base |
| Banco de Goertzel | Banco de filtros passa-faixa digitais (substitui LC ressonante) |
| Nota → frequência (`440·2^…`) | Quantização em frequência / FSK simbólico |
| `(pitch, dur)` em 2 bytes | Codificação de fonte (representação compacta do áudio) |
| Reuso do quadro CRC da etapa 1 | Codificação de canal (detecção de erro) |
| Síntese senoidal + envelope | Reconstrução do sinal (DAC + filtro de reconstrução) |
| Melodia curta por canal lento | Compromisso vazão × robustez |

---

## 12. Fora de escopo (trabalho futuro)

- Fragmentar melodias longas em múltiplos quadros.
- Polifonia (mais de uma nota simultânea).
- Detecção de andamento/dinâmica (volume).
- TX em tempo real nota-a-nota (rejeitado: canal lento demais).
- Timbres além de senoide (harmônicos, ADSR completo).
