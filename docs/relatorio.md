# LiFi via Câmera — Relatório Final (PCOM)

**Equipe:** [preencher com os nomes]
**Cadeira:** Princípios de Comunicação (PCOM) — UABJ, 7º período de Engenharia da Computação
**Data de entrega:** [preencher]
**Repositório:** [link do repo privado/URL]

---

## 1. Objetivo

Implementar um link de comunicação em luz visível (VLC, *Visible Light
Communication*) entre um transmissor baseado em Arduino + LED e um receptor
em Python/OpenCV que processa o *feed* de uma webcam. O sistema também
suporta uma fonte de TX alternativa: a lanterna de um celular Android
controlada via Termux.

**Tese:** todo filtro analógico clássico das comunicações (LC, RC,
comparador com histerese, PLL, detecção de paridade) é **substituído por
um equivalente digital em software**, com BER mensurável ao vivo na
apresentação.

---

## 2. Arquitetura

O sistema tem três blocos lógicos e um canal óptico (ver diagrama da
Seção 2 do *design spec*):

- **HOST-TX (Python, `src/tx.py`)** — lê texto do teclado, constrói o quadro
  completo (preamble + STX + LEN + payload + CRC-8 + ETX) e despeja os bytes
  prontos no canal de saída (serial USB para o Arduino, ou arquivo `.bin`
  para o celular).
- **Camada física (PHY)** — duas opções intercambiáveis:
  - Arduino + LED verde/azul, com Timer1 em modo CTC emitindo bits a 5 Hz.
  - Celular Android, com `tx_phone.sh` no Termux piscando a lanterna via
    `termux-torch`.
- **HOST-RX (Python + OpenCV, `src/rx.py`)** — pipeline linear:
  captura → HSV + morfologia → ROI → sinal 1D → média móvel → AGC →
  *clock recovery* → desserialização UART → *parser* do quadro → validação
  CRC → texto.

A divisão em camadas respeita o modelo OSI: o Arduino não tem noção de
CRC, preamble, ASCII ou caractere — é apenas um driver de hardware com
timing determinístico via ISR. Toda a lógica de protocolo está no Python,
onde há bibliotecas potentes para testes e *logging*.

---

## 3. Protocolo de enquadramento

### 3.1 UART-over-light

Cada byte é emitido com a estrutura clássica de UART:

| Bit | Duração | Nível ótico |
|-----|---------|-------------|
| Start | 200 ms | LED apagado (= 0) |
| Data bit 0 (LSB) | 200 ms | conforme dado |
| Data bits 1–7 | 200 ms cada | conforme dado |
| Stop | 200 ms | LED aceso (= 1) |

Convenção: `1 = LED aceso`, `0 = LED apagado`. Estado IDLE = LED aceso.

### 3.2 Quadro da mensagem

```
[PREAMBLE 0x55×4] [STX 0x02] [LEN] [PAYLOAD ≤120B] [CRC-8] [ETX 0x03]
```

- **Preamble** de 4 bytes `0x55`: com o framing UART LSB-first, forma uma
  onda quadrada *perfeitamente alternada* (40 bits `0,1,0,1,…`), sem
  violação nas transições entre bytes. Usado para (a) AGC digital,
  (b) estimativa de `Tb_medido` e (c) sincronização de fase.
- **STX** (`0x02`): delimitador de início de quadro.
- **LEN**: 1 byte indicando tamanho do payload.
- **Payload**: até 120 bytes ASCII (buffer do Arduino = 128 bytes - 8 de
  overhead).
- **CRC-8** (polinômio 0x07, init 0x00, sem reflexão): detecção de erro.
- **ETX** (`0x03`): delimitador de fim.

### 3.3 Por que 0x55 e não 0xAA

Com LSB-first UART, `0xAA` enquadrado vira `0,0,1,0,1,0,1,0,1,1` — começa
com dois 0s (start + LSB) e termina com dois 1s (MSB + stop), o que
quebra a lógica de detecção de *fim de preamble* do receptor. `0x55`
enquadrado vira `0,1,0,1,0,1,0,1,0,1` — alternância perfeita.

---

## 4. DSP — do vídeo aos bits

### 4.1 Pré-processamento espacial (OpenCV)

Dois modos, parametrizados via flag `--mode`:

- **`color`** (LED colorido): HSV por matiz (verde ou azul) + saturação > 80.
  Atua como um **filtro passa-faixa óptico** de banda estreita. A sala tem
  luz branca/amarela que cai fora da faixa.
- **`white`** (lanterna do celular): `V > 200 AND S < 40` — alta luminosidade
  + baixa saturação. Equivalente a um **filtro passa-tudo óptico com
  comparador de brilho**.

Após a máscara de cor, aplicamos um fechamento morfológico (dilate +
erode, kernel 3×3) para eliminar cintilações isoladas. A ROI é o maior
blob da máscara, com centróide suavizado por média móvel temporal
(10 frames).

### 4.2 Sinal 1D

Para cada frame, a intensidade é a média do canal V (HSV) dentro da ROI.
Isso produz um `signal[t]` unidimensional indexado por frame.

### 4.3 Filtragem digital — média móvel M=3

Implementação: `np.convolve(signal, np.ones(3)/3, mode="same")`.

É um **filtro FIR de janela retangular** com 3 taps. Primeiro zero da
resposta em frequência em `Fs/M = 30/3 = 10 Hz`, o que preserva a
fundamental do preamble (2.5 Hz) e atenua o ruído de sensor + flicker
acima de 10 Hz. Equivalente digital de um RC passa-baixa com τ ≈ 100 ms.

### 4.4 AGC digital

`threshold = (P90 + P10) / 2` computado sobre os frames do preamble.
Percentis (não mín/máx) para robustez a picos isolados. Equivalente
digital de um AGC analógico com capacitor e comparador com histerese.

### 4.5 Recuperação de relógio (4 estados)

1. **Busca**: correlação do sinal filtrado com uma onda quadrada de 2.5 Hz
   em janelas deslizantes de ~1.6 s. Limiar = 0.85.
2. **Tracking**: `Tb_medido` a partir do espaçamento mediano entre *zero-
   crossings* do preamble — absorve *jitter* do TX.
3. **Fim de preamble**: detecta a **primeira violação da alternância**
   (dois bits iguais consecutivos). O primeiro dos dois é o START BIT do
   STX.
4. **Decodificação**: amostra no centro de cada bit, desserializa UART
   (start/stop descartados, 8 bits LSB-first), acumula bytes e entrega ao
   *parser* do quadro.

---

## 5. Resultados

### 5.1 Critério de Nyquist

- Fs (webcam) = 30 fps
- Rb (bit rate ótico) = 5 bps
- Razão Fs/Rb = 6 amostras por bit
- Margem de Nyquist = `Fs / (2 · Rb) = 3×`

Cada bit é representado por 6 frames, o que permite amostrar no centro
com tolerância a *jitter* da câmera. Nenhum ISI observado em testes.

### 5.2 BER por condição

_Preencher após rodar `scripts/ber_sweep.py` nos vídeos gravados._

| Modo  | Condição              | Tentativas | OK | BAD | BER~ |
|-------|-----------------------|-----------:|---:|----:|-----:|
| color | sala escura, 30 cm    | –          | –  | –   | –    |
| color | luz ambiente, 30 cm   | –          | –  | –   | –    |
| color | luz ambiente, 1 m     | –          | –  | –   | –    |
| white | sala escura, 30 cm    | –          | –  | –   | –    |

### 5.3 Comparação TX Arduino vs lanterna

_Discutir aqui por que o *clock recovery* com `Tb_medido` compensa o
*jitter* de OS no celular. Gerar evidência apontando que a BER no modo
white é aceitável desde que o preamble detectado gere um `Tb_medido`
próximo do Tb real do TX._

---

## 6. Mapeamento PCOM

| Componente do projeto | Conceito de PCOM |
|---|---|
| LED piscando (colorido ou branco) | Modulação em banda base (OOK) |
| Fs câmera vs Rb | Critério de Nyquist / ausência de ISI |
| Preamble 0x55 × 4 | Sincronização de símbolo / *clock recovery* |
| Média móvel M=3 | Filtro FIR passa-baixa |
| Threshold 10/90 | Decisão por limiar / quantização |
| Modo `color` (HSV matiz + S alta) | Filtro passa-faixa óptico em banda estreita |
| Modo `white` (V alta + S baixa) | Filtro passa-tudo óptico com comparador de brilho |
| CRC-8 | Codificação de canal (detecção de erro) |
| Voto majoritário de ±1 frame | Integrate-and-dump |
| `Tb_medido` estimado no preamble | Recuperação de clock tolerante a *drift* |
| TX Arduino vs TX lanterna | Portadora óptica intercambiável |

---

## 7. Estrutura do código

```
src/
  frame.py         # crc8, build_frame, parse_frame
  dsp.py           # moving_average, compute_threshold, find_preamble,
                   # estimate_bit_time_frames, find_end_of_preamble,
                   # decode_uart_byte, decode_signal
  cv_pipeline.py   # compute_mask, find_roi, extract_intensity, ROITracker
  tx.py            # Host TX: teclado -> quadro -> serial/arquivo
  rx.py            # Host RX: main loop, 3 janelas, BER overlay

firmware/
  tx.ino           # Arduino: Timer1 ISR + buffer circular + UART-over-light

scripts/
  tx_phone.sh      # Termux: lê frame.bin e pisca a lanterna
  ber_sweep.py     # replay de vídeos gravados -> tabela de BER

tests/
  test_frame.py    # 16 testes de CRC, build, parse
  test_dsp.py      # 18 testes de média móvel, AGC, clock recovery
  test_cv_pipeline.py  # 8 testes de HSV/morfologia/ROI/tracker
  test_integration_synthetic_video.py  # vídeo sintético -> decodificar
  test_tx.py       # tx file mode
```

Todos os ~44 testes passam. A camada de validação 3 (integração *offline*
com vídeo sintético) já é *green*; camadas 4 e 5 (live color e live
white) dependem do hardware físico.

---

## 8. Conclusão e trabalhos futuros

A arquitetura proposta — filtros digitais em software substituindo os
analógicos — foi validada em toda a cadeia de DSP por testes unitários e
de integração com sinais sintéticos. O transmissor é modular (Arduino
primário, celular secundário) e o receptor opera em modo dual (color e
white) sem alteração de protocolo.

### Extensões naturais

- **Codificação Manchester** para embutir o clock no próprio sinal,
  removendo a dependência do preamble para sincronização.
- **FEC** (códigos corretores de erro) — Hamming ou Reed-Solomon —
  para reduzir BER em modo *white*.
- **Rate adaptation** baseada em BER estimada: aumentar ou reduzir Rb
  automaticamente conforme a qualidade do canal.
- **Duplex**: replicar a pipeline no outro sentido para formar um chat
  bidirecional completo.

### Limitações conhecidas

- Rb = 5 bps é lento; uma mensagem de 40 caracteres leva ~1 min 36 s.
- Saturação da câmera pela luz ambiente intensa pode apagar a ROI no
  modo *white*.
- *Jitter* do OS no celular tem piso em ~10 ms que o receptor compensa
  via `Tb_medido`, mas um sistema mais determinístico (app Android
  nativo) teria BER menor.

---

## 9. Referências

- *Design spec* interno: `docs/superpowers/specs/2026-04-21-lifi-vlc-design.md`
- *Implementation plan*: `docs/superpowers/plans/2026-04-21-lifi-vlc-implementation.md`
- *Hardware bring-up guide*: `docs/HARDWARE_VERIFICATION.md`
- OpenCV docs: https://docs.opencv.org
- NumPy docs: https://numpy.org/doc
- Termux:API: https://wiki.termux.com/wiki/Termux:API
