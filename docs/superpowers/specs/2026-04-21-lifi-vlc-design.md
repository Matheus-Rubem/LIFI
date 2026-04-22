# LiFi via Câmera — Design de Sistema VLC (Visible Light Communication)

**Data:** 2026-04-21
**Cadeira:** PCOM — Princípios de Comunicação (UABJ, 7º período de Engenharia da Computação)
**Prazo:** 2 semanas (apresentação com demo ao vivo + relatório)
**Status:** Design aprovado, pronto para plano de implementação.

---

## 1. Problema e tese

Construir um link de comunicação unidirecional em luz visível: um Arduino pisca um LED transmitindo texto ASCII arbitrário digitado no teclado; uma webcam + Python/OpenCV recebe a luz e reconstrói o texto.

**Tese para a cadeira:** todo filtro analógico do mundo das comunicações clássicas (LC, RC, comparador de histerese, PLL, detecção de erro por paridade) é **substituído por um equivalente digital em software**. O sistema é um banco de prova dessa equivalência, com BER mensurável ao vivo.

### Objetivos

1. Transmitir texto ASCII arbitrário (até 120 bytes) digitado em tempo real pelo operador.
2. Decodificar na outra ponta com validação de integridade (CRC-8).
3. Apresentar três janelas simultâneas: frame bruto, máscara pós-filtros, gráfico do sinal 1D com bits decodificados.
4. Reportar BER instantânea e acumulada na demo.
5. Amarrar cada bloco do sistema a um conceito explícito de PCOM.

### Fora de escopo

- Full-duplex, múltiplos canais, ECC (códigos corretores), handshake, criptografia.
- Controle de fluxo sofisticado.
- Funcionamento em condições extremas (sol direto, >5 m de distância).

---

## 2. Arquitetura de alto nível

```
┌─────────────────────┐     Serial USB     ┌─────────────────┐
│   HOST-TX (Python)  │ ─────────────────▶ │  ARDUINO (TX)   │
│                     │                     │                 │
│ • Lê input() do     │                     │ • Recebe bytes  │
│   teclado           │                     │   via UART      │
│ • Monta o quadro    │                     │ • Empurra bits  │
│ • Envia bytes       │                     │   para o LED    │
│   serializados      │                     │   (Timer1 ISR)  │
└─────────────────────┘                     └────────┬────────┘
                                                     │
                                                     ▼
                                             ╔═══════════════╗
                                             ║ LED (canal    ║
                                             ║ óptico VLC)   ║
                                             ╚═══════╤═══════╝
                                                     │ luz
                                                     ▼
┌───────────────────────────────────────────────────────────┐
│                 HOST-RX (Python + OpenCV)                 │
│                                                           │
│ 1. Captura de frame (webcam, 30 fps)                      │
│ 2. Pré-processamento: HSV → morfologia → ROI              │
│ 3. Extração de sinal 1D (média de brilho na ROI)          │
│ 4. Filtro passa-baixa digital (média móvel) + AGC         │
│ 5. Detecção de preamble → sincronização de bit-clock      │
│ 6. Amostragem no centro do bit (voto majoritário)         │
│ 7. Desserialização UART → bytes                           │
│ 8. Parser do quadro → validação CRC → payload             │
│ 9. Imprime a string decodificada no terminal              │
└───────────────────────────────────────────────────────────┘
```

**Três blocos, um canal.** O Arduino é mantido "burro" de propósito: só camada física. O HOST-TX faz montagem do quadro. O HOST-RX é um pipeline linear em um único processo Python, cada estágio testável isoladamente com arquivo `.npy` ou vídeo gravado.

**Apresentação — três janelas simultâneas:**

1. Frame bruto da webcam com retângulo marcando a ROI do LED.
2. Máscara pós-filtros de imagem (preto e branco, LED isolado).
3. Gráfico do sinal 1D (brilho vs tempo) com bits decodificados sobrepostos + terminal mostrando o texto.

---

## 3. Protocolo de enquadramento

### UART-over-light (serialização de byte)

Cada byte (incluindo os do cabeçalho) é emitido assim:

- **1 start bit** = 0 (LED apaga por 200 ms) — sinaliza início do byte.
- **8 data bits**, LSB first.
- **1 stop bit** = 1 (LED acende por 200 ms) — garante estado conhecido antes do próximo byte.

Convenção óptica: **1 = LED aceso, 0 = LED apagado**. Estado IDLE = LED aceso.

### Quadro (packet frame)

```
┌─────────────────┬─────┬─────┬──────────────┬───────┬─────┐
│ PREAMBLE (4 B)  │ STX │ LEN │ PAYLOAD (N)  │ CRC-8 │ ETX │
│ 0x55 0x55 0x55  │ 0x02│ 1 B │ N ≤ 120 ASCII│  1 B  │ 0x03│
│ 0x55            │     │     │              │       │     │
└─────────────────┴─────┴─────┴──────────────┴───────┴─────┘
```

Mapeamento dos campos aos conceitos de PCOM:

| Campo | Papel | Conceito PCOM |
|---|---|---|
| PREAMBLE | Onda quadrada alternada para AGC + sync | Sincronização de símbolo / recuperação de clock |
| STX (0x02) | Delimitador de início de quadro | Enquadramento |
| LEN | Tamanho do payload em bytes | Controle de comprimento |
| PAYLOAD | ASCII arbitrário | — |
| CRC-8 (poly 0x07, init 0x00) | Detecção de erro | Codificação de canal |
| ETX (0x03) | Delimitador de fim de quadro | Enquadramento |

**Preamble de 4 bytes de 0x55** com framing UART LSB-first forma uma sequência perfeitamente alternada `0,1,0,1,0,1,...` de 40 bits. Cada byte 0x55 framed = start(0) + `1,0,1,0,1,0,1,0` (LSB-first data) + stop(1) = `0,1,0,1,0,1,0,1,0,1` — 10 bits alternados. Concatenação de 4 bytes preserva a alternação perfeita em todas as transições de byte. Serve para: (a) AGC digital (aprender mín/máx de brilho na sala); (b) estimativa fina do bit-time real da câmera; (c) sincronização de fase (localizar centros de bit).

**Por que 0x55 e não 0xAA:** com LSB-first UART, 0xAA framed = `0,0,1,0,1,0,1,0,1,1` — começa com dois 0s (start+LSB) e termina com dois 1s (MSB+stop). Isso quebra a detecção de "dois bits iguais consecutivos = fim de preamble" (Seção 5 Estado 3). 0x55 é a escolha simétrica correta para LSB-first.

---

## 4. Transmissor — HOST-TX Python + Arduino

### Divisão de responsabilidades

| Camada | Componente | Responsabilidade |
|---|---|---|
| Aplicação | `tx.py` | Ler teclado, montar quadro completo (preamble + STX + LEN + payload + CRC-8 + ETX), enviar bytes ao Arduino via serial USB (115200 baud). |
| Física (PHY) | `firmware/tx.ino` | Receber bytes por USB, bufferizar, emitir cada bit do LED com bit-time preciso de 200 ms usando Timer1 em modo CTC. Manter LED em IDLE (aceso) entre quadros. |

O Arduino **não conhece CRC, preamble, ASCII, nem a noção de "caractere"**. Recebe bytes e pisca com framing UART. Esse limite de abstração é o ponto central da decomposição em camadas exigida pela cadeira.

### `tx.py` — pseudocódigo do caminho principal

```python
loop:
    texto = input("> ")
    payload = texto.encode('ascii')
    assert len(payload) <= 120
    quadro = bytearray()
    quadro += bytes([0x55]) * 4        # PREAMBLE
    quadro += bytes([0x02])            # STX
    quadro += bytes([len(payload)])    # LEN
    quadro += payload                  # PAYLOAD
    quadro += bytes([crc8(payload)])   # CRC-8 (poly 0x07, init 0x00)
    quadro += bytes([0x03])            # ETX
    serial_link.write(quadro)
```

### `firmware/tx.ino`

- **Timer1 em CTC**, interrupção a 5 Hz (200 ms). Dentro da ISR, máquina de estados pequena emite os 10 bits de um byte (start 0 → 8 data LSB-first → stop 1), então consome o próximo byte do buffer circular.
- **Buffer circular** de 128 bytes entre `loop()` (leitura USB) e ISR. Buffer cheio → `loop()` bloqueia leitura USB; controle de fluxo vem do próprio bloqueio.
- **IDLE = LED aceso** quando buffer está vazio. Isso dá ao receptor a garantia de que, após ETX, a luz fica constante alta — o que marca "fim de transmissão" sem ambiguidade.
- **Sem bibliotecas terceiras** para emitir bits. Apenas `digitalWrite` direto do timer, controlado por máscara de bit.

### Link Python ↔ Arduino

USB serial 115200 baud. Python escreve os bytes na ordem exata em que devem piscar. Sem protocolo extra — é um pipe FIFO. O buffer circular de 128 bytes no Arduino foi dimensionado para acomodar exatamente um quadro máximo (preamble 4 + STX 1 + LEN 1 + payload 120 + CRC 1 + ETX 1 = 128 bytes). Transmitir o buffer cheio leva 128 × 10 bits × 200 ms = 256 s (≈ 4 min 16 s). Controle de fluxo vem naturalmente do bloqueio de leitura USB quando o buffer enche.

### Hardware

- LED verde ou azul, ânodo em D8 do Arduino.
- Resistor limitador 220 Ω em série com o LED para GND.
- (Opcional) LED vermelho em D13 como indicador de "quadro em transmissão".

---

## 5. Receptor — HOST-RX Python + OpenCV

Pipeline linear: cada estágio recebe o output do anterior, produz um tipo de dado claro e pode ser testado isoladamente.

### Estágio 1 — Pré-processamento espacial (`cv_pipeline.py`)

Objetivo: isolar a ROI do LED no frame e descartar o resto da cena.

1. **Conversão BGR → HSV**. Filtragem por matiz (faixa de verde ou azul conforme o LED). Atua como um **filtro passa-faixa óptico**: a sala tem luz branca/amarela que cai fora da faixa do LED colorido.
2. **Operações morfológicas**: `cv2.dilate` seguido de `cv2.erode` (fechamento) com kernel 3×3, para eliminar pontos brilhantes isolados (ruído visual).
3. **ROI**: identificar o maior "blob" da máscara em cada frame. Trackar centróide entre frames com pequena inércia (média móvel sobre as últimas 10 posições) para estabilizar.
4. **Threshold dinâmico** é aplicado no estágio 3 (sinal 1D), não aqui — manter esse estágio puramente espacial.

### Estágio 2 — Extração do sinal 1D

Para cada frame `t`:
```python
sinal_bruto[t] = np.mean(frame_hsv_masked[roi_y:roi_y+h, roi_x:roi_x+w, 2])
# canal V (valor/brilho) pois queremos intensidade, não matiz
```

Produz um array `sinal_bruto[]` unidimensional indexado por frame.

### Estágio 3 — Filtragem DSP (`dsp.py`)

**Média móvel M=3** como filtro FIR passa-baixa:
```python
sinal_filtrado = np.convolve(sinal_bruto, np.ones(3)/3, mode='same')
```

Primeiro zero de resposta em `Fs/M = 30/3 = 10 Hz`. Preserva a fundamental do preamble (2.5 Hz) intacta, atenua ruído de sensor e componentes acima de 10 Hz (incluindo flicker de 60 Hz aliasado).

No relatório vendemos como **filtro FIR de janela retangular** (nome técnico correto). Equivalente digital de um RC passa-baixa com τ ≈ 100 ms.

### Estágio 4 — AGC digital (threshold dinâmico)

Durante o preamble:
```python
high_level = np.percentile(sinal_filtrado_preamble, 90)
low_level  = np.percentile(sinal_filtrado_preamble, 10)
threshold  = (high_level + low_level) / 2
```

Percentis (não mín/máx) para ser robusto a spikes isolados. **Substituto digital do AGC analógico** com capacitor e comparador com histerese.

### Estágio 5 — Clock recovery (4 estados)

```
Estado 1 — Busca de preamble:
  Calcular correlação do sinal filtrado com onda quadrada de 2.5 Hz em
  janelas deslizantes de ~1 s (30 frames). Correlação > limiar → preamble.

Estado 2 — Tracking do preamble:
  Estimar fase (posição dos centros de bit) via cruzamentos de zero
  (transições entre high e low). Estimar Tb_medido a partir do espaçamento
  médio das transições. Tb_medido pode diferir ligeiramente de 200 ms por
  jitter de fps da webcam.

Estado 3 — Detecção de fim de preamble:
  Amostrar o bit no centro de cada bit-slot esperado. Preamble produz
  uma sequência perfeitamente alternada ...1,0,1,0,1,0,1,0... terminando
  em 1 (stop bit do 4º byte 0x55).

  Ao encontrar DOIS bits iguais consecutivos (ex: ...1,0,1,0,1,0,0,...),
  o PRIMEIRO dos dois é o START BIT do STX (= 0), e o SEGUNDO é o LSB do
  byte STX (0x02, LSB first = 01000000 → primeiro data bit = 0). Na
  implementação, a violação é detectada no slot do segundo bit, então
  recuar um bit-time para localizar o start bit. Travar sincronização
  com bit_center[0] = centro do start bit do STX.

Estado 4 — Decodificação:
  A partir do start bit do STX, amostrar cada bit no seu centro:
      bit_center[n] = start_bit_STX_center + n * Tb_medido
  Desserializar UART (descartar start/stop bits, coletar 8 data bits
  LSB-first), acumular bytes, parsear quadro, validar CRC.
```

**Voto majoritário** na amostragem: em vez de ler 1 frame no centro do bit, ler 3 frames ao redor e votar. Equivalente digital de integrate-and-dump.

### Estágio 6 — Parser do quadro (`frame.py`)

Lógica:
1. Aguarda STX (0x02).
2. Lê LEN (1 byte).
3. Lê LEN bytes de payload.
4. Lê CRC-8. Computa CRC local do payload e compara. Incrementa contador de BER em caso de falha.
5. Lê ETX (0x03). Se não for 0x03, descarta o quadro (sincronização perdida) e volta ao estado 1.

### Mapeamento PCOM (relatório)

| Componente | Conceito PCOM |
|---|---|
| LED piscando | Modulação em banda base (OOK) |
| Fs câmera vs Rb | Critério de Nyquist / ausência de ISI |
| Preamble 0x55 × 4 | Sincronização de símbolo / clock recovery |
| Média móvel M=3 | Filtro FIR passa-baixa |
| Threshold 10/90 | Decisão por limiar / quantização |
| CRC-8 | Codificação de canal (detecção de erro) |
| Voto majoritário | Integrate-and-dump |

---

## 6. Parâmetros do sistema

| Parâmetro | Valor | Justificativa |
|---|---|---|
| Frame rate da webcam (Fs) | 30 fps | Padrão universal. Mensurado em runtime, não assumido. |
| Bit-rate óptico (Rb) | 5 bps | = Fs/6. Cada bit em 6 frames. |
| Bit-time (Tb) | 200 ms | = 1/Rb. Timer Arduino a 5 Hz. |
| Frequência fundamental do preamble | 2.5 Hz | = Rb/2. |
| Frequência de Nyquist | 15 Hz | = Fs/2. |
| Margem Nyquist (Fs / 2·Rb) | 3× | Folga contra aliasing. |
| M da média móvel | 3 frames | Corte em 10 Hz, preserva preamble, atenua flicker. |
| Preamble | 4 bytes (40 bits) | Janela suficiente para AGC e estimativa de Tb. |
| Payload máximo | 120 bytes | Limite do buffer do Arduino (128 bytes - 8 de overhead = 120 de payload). |

---

## 7. Tratamento de erros e métricas

### BER (Bit Error Rate)

Computada a cada quadro:
```
BER_quadro = bits_errados / bits_totais_do_quadro
BER_acumulada = sum(bits_errados) / sum(bits_totais)
```

Como o RX não conhece o payload original, "bits errados" é inferido indiretamente via CRC: quadro com CRC ok ⇒ 0 erros reconhecidos; CRC fail ⇒ quadro inteiro contabilizado como perdido (pessimista, mas honesto e mensurável). Para medir BER fina, sessão de teste pode transmitir payload conhecido ("test vector") e comparar byte-a-byte no RX.

### Modos de falha e recuperação

| Falha | Detecção | Resposta |
|---|---|---|
| CRC inválido | comparação | Descarta quadro, incrementa contador |
| ETX ausente | parse | Descarta, volta ao estado 1 (busca de preamble) |
| Preamble não detectado em 5 s | timeout | Log "no signal", mantém procurando |
| LEN > 120 | parse | Descarta, volta ao estado 1 |
| Webcam desconectada | exceção de captura | Erro fatal, encerra com mensagem clara |

Nenhum retry é implementado — canal é unidirecional. Detectar e descartar é suficiente para o escopo.

---

## 8. Estrutura de arquivos

```
LIFI/
├── firmware/
│   └── tx.ino                  # Arduino: Timer1 ISR + UART-over-light
├── src/
│   ├── tx.py                   # Host TX: teclado → quadro → serial
│   ├── rx.py                   # Host RX: main loop, orquestra pipeline
│   ├── frame.py                # build_frame, parse_frame, crc8
│   ├── cv_pipeline.py          # HSV + morfologia + ROI + sinal 1D
│   └── dsp.py                  # média móvel, AGC, clock recovery
├── tests/
│   ├── test_frame.py           # roundtrip, CRC, corrupções
│   └── test_dsp.py             # clock recovery em sinais sintéticos
├── assets/
│   └── videos_gravados/        # vídeos de teste para debug offline
├── docs/
│   ├── superpowers/specs/
│   │   └── 2026-04-21-lifi-vlc-design.md   (este documento)
│   └── relatorio.md            # relatório final para a cadeira
└── requirements.txt            # opencv-python, numpy, pyserial, crcmod
```

Cada módulo em `src/` testável isoladamente. O RX pode ser desenvolvido sem hardware rodando, a partir de vídeo gravado ou sinais sintéticos em `numpy`.

---

## 9. Plano de validação

Quatro camadas, cada uma gate para a próxima:

| Camada | Escopo | Ferramenta |
|---|---|---|
| 1. Unitário — frame | `build_frame`/`parse_frame`/`crc8` são inversos; CRC detecta flip de 1 bit | `pytest`, 100% cobertura |
| 2. Unitário — DSP | Clock recovery decodifica sinal 1D sintético com ruído gaussiano controlado; afere BER em função do SNR | `pytest`, `numpy` |
| 3. Integração offline | Pipeline completo em vídeo gravado de LED piscando payload conhecido | `rx.py --input video.mp4` |
| 4. Live (hardware) | Sistema completo em tempo real | Arduino + webcam + notebook |

---

## 10. Cronograma de 2 semanas

### Semana 1 — Construção

| Dia | Tarefa | Entregável |
|---|---|---|
| 1 | Setup: repositório, `requirements.txt`, Arduino IDE, LED/resistor montado | LED piscando a 1 Hz com `delay()` (proof-of-life) |
| 2 | `frame.py` + `test_frame.py` (CRC, build, parse) | Testes passando, cobertura 100% do módulo |
| 3 | `firmware/tx.ino` com Timer1 ISR a 5 Hz + buffer USB | LED piscando 0x55 contínuo, verificável com app de osciloscópio no celular |
| 4 | `tx.py`: integração teclado → serial → Arduino | Digitar "OI" e ver LED executar o quadro completo |
| 5 | `cv_pipeline.py`: captura webcam + HSV + ROI + sinal 1D | Gráfico `matplotlib` do sinal bruto mostrando onda quadrada do preamble |
| 6 | `dsp.py`: média móvel + AGC (threshold 10/90) | Sinal quantizado em 0/1 alinhado visualmente com as piscadas |
| 7 | **CHECKPOINT 1** — detecção de preamble end-to-end | Script imprime "PREAMBLE DETECTADO" ao ver 0x55×4 |

### Semana 2 — Decodificação + polimento

| Dia | Tarefa | Entregável |
|---|---|---|
| 8 | Clock recovery estados 3 e 4: detectar fim de preamble + amostrar no centro | Decodifica STX + LEN + 1 caractere ASCII |
| 9 | Parser de quadro completo + validação CRC | Decodifica mensagem completa, mostra "CRC OK/FAIL" |
| 10 | Contador de BER + display instantâneo | Terminal mostra BER após cada quadro |
| 11 | Três janelas (frame bruto + máscara + gráfico 1D) em layout apresentável | Interface pronta para demo |
| 12 | Testes de robustez: luz ambiente, distância, ângulo → medir BER | Tabela no relatório com BER × condição |
| 13 | **CHECKPOINT 2** — demo funcional + rascunho do relatório | Dry-run de apresentação (5 min) |
| 14 | Buffer — ajustes de iluminação na sala real, ensaio final | Pronto |

---

## 11. Plano de contingência

Ordem de corte, do menos doloroso ao mais:

1. **Dia 12 atrasou?** Cortar tabela de BER × condição. Apresentar só 1 condição (sala escura).
2. **Dia 10 atrasou?** Cortar display de BER em tempo real. Mostrar apenas "CRC OK/FAIL".
3. **Dia 9 atrasou?** Voltar a payload fixo hardcoded. Perde "chat ao vivo", mantém toda a PHY/DSP.
4. **Dia 8 atrasou (clock recovery travou)?** Usar bit-time fixo confiando no Arduino (sem tracking dinâmico). Perde rigor mas demo roda.

**Regra absoluta:** nunca cortar CRC, preamble ou as três janelas — carregam a narrativa PCOM do "10".

---

## 12. Riscos residuais

| Risco | Probabilidade | Mitigação |
|---|---|---|
| Webcam com fps variável (28-32 fps) | Média | Medir fps real no setup, estimar Tb localmente a partir do preamble |
| Luz fluorescente com flicker a 120 Hz | Alta | Filtragem HSV corta primeiro; M=3 atenua 120 Hz aliasado |
| LED saturando câmera (ROI inteira branca) | Média | Ajustar resistor para LED mais dim, ou aumentar distância |
| Arduino buffer overflow em payload longo | Baixa | LEN ≤ 120 bytes é o exato limite do buffer de 128 bytes (com overhead de 8 bytes); validar assertion em `tx.py` antes do `serial_link.write()` |

---

## 13. Critérios de aceitação

O projeto é considerado "pronto para apresentação" quando:

1. Camadas de validação 1, 2 e 3 passam.
2. Um operador digita uma string curta (5-10 caracteres) e ela aparece no notebook receptor com CRC OK. Tempo esperado: ≈ (preamble 4 + STX 1 + LEN 1 + N + CRC 1 + ETX 1) × 2 s/byte, ou seja, ~26 s para 5 chars e ~36 s para 10 chars. Demonstração com até 40 caracteres leva ≈ 1 min 36 s e é usada apenas em dry-run.
3. As três janelas funcionam simultaneamente sem travamento visível.
4. BER acumulada é reportada na tela após cada quadro.
5. Narrativa PCOM (tabela de mapeamento da Seção 5) é consistente entre código, relatório e fala da apresentação.
