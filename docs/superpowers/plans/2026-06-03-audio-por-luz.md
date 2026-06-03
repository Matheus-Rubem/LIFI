# Áudio (melodia) por Luz — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transmitir uma melodia curta por luz reusando o canal LiFi da etapa 1, enviando a sequência simbólica de notas (altura+duração) em vez de áudio PCM cru.

**Architecture:** Microfone → banco de filtros de Goertzel → notas `(pitch, dur)` → 2 bytes/nota → quadro da etapa 1 → LED → câmera → decodificação da etapa 1 → notas → síntese senoidal → alto-falante. A etapa 1 é reusada sem alteração, exceto a extração (preservadora de comportamento) de um gerador `decoded_payloads()` no `rx.py`.

**Tech Stack:** Python 3.11, numpy, sounddevice (mic/alto-falante), pytest. Reusa `src/frame.py`, `src/dsp.py`, `src/cv_pipeline.py` da etapa 1.

**Spec:** `docs/superpowers/specs/2026-06-03-audio-por-luz-design.md`

---

## File Structure

| Arquivo | Responsabilidade |
|---------|------------------|
| `src/note_codec.py` (criar) | `Note`, `encode`, `decode`, `midi_to_freq`. Puro, sem I/O. |
| `src/pitch_detect.py` (criar) | Goertzel + `audio_to_notes` (áudio → notas). |
| `src/audio_synth.py` (criar) | `synthesize` (notas → array de áudio). Puro, sem I/O. |
| `src/audio_rx.py` (criar) | CLI: `decoded_payloads` → `decode` → `synthesize` → playback. |
| `src/audio_tx.py` (criar) | CLI: captura mic → `audio_to_notes` → `encode` → serial. |
| `src/rx.py` (modificar) | Extrair `decoded_payloads()` + `_parse_args()`; comportamento idêntico. |
| `requirements.txt` (modificar) | + `sounddevice`. |
| `tests/test_note_codec.py` (criar) | round-trip, pausas, payload ímpar. |
| `tests/test_pitch_detect.py` (criar) | Goertzel + detecção de notas a partir de senoides. |
| `tests/test_audio_synth.py` (criar) | síntese: pico de FFT e duração. |
| `tests/test_audio_integration.py` (criar) | laço completo reusando `dsp`. |
| `tests/test_rx_payloads.py` (criar) | `decoded_payloads` em vídeo sintético. |
| `docs/HARDWARE_VERIFICATION_AUDIO.md` (criar) | checklist manual (mic + alto-falante). |

> **Nota de síntese:** o spec menciona a síntese dentro do `audio_rx.py`; para mantê-la pura e testável sem dispositivo de áudio, ela vive em `src/audio_synth.py` e o `audio_rx.py` (CLI) apenas a chama e toca o resultado.

---

## Task 1: `note_codec` — contrato notas ↔ bytes

**Files:**
- Create: `src/note_codec.py`
- Test: `tests/test_note_codec.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_note_codec.py
from src.note_codec import Note, encode, decode, midi_to_freq, REST


def test_roundtrip_simple_melody():
    notes = [Note(60, 8), Note(64, 8), Note(67, 4)]
    assert decode(encode(notes)) == notes


def test_rest_roundtrips():
    notes = [Note(60, 4), Note(REST, 2), Note(62, 4)]
    assert decode(encode(notes)) == notes


def test_encode_is_two_bytes_per_note():
    assert len(encode([Note(60, 8), Note(62, 8)])) == 4


def test_decode_truncates_odd_trailing_byte():
    # An incomplete final pair (from a partial frame) is dropped.
    assert decode(b"\x3c\x08\x40") == [Note(60, 8)]


def test_decode_out_of_range_pitch_becomes_rest():
    # 0x05 (=5) is outside {0} U [48,72] -> treated as a rest.
    assert decode(b"\x05\x04") == [Note(REST, 4)]


def test_encode_clamps_steps_to_1_255():
    assert encode([Note(60, 0)]) == b"\x3c\x01"
    assert encode([Note(60, 999)]) == b"\x3c\xff"


def test_midi_to_freq_a4_is_440():
    assert abs(midi_to_freq(69) - 440.0) < 1e-6
    assert abs(midi_to_freq(60) - 261.6256) < 1e-3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_note_codec.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.note_codec'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/note_codec.py
"""Codec for a melody as a list of notes <-> bytes (the payload contract).

Each note is 2 bytes: [pitch][steps].
  pitch : MIDI note number in [48, 72], or REST (0) for silence.
  steps : duration in 50 ms steps, clamped to [1, 255].
"""
from __future__ import annotations

from dataclasses import dataclass

REST = 0
MIDI_MIN = 48
MIDI_MAX = 72


@dataclass(frozen=True)
class Note:
    pitch: int   # MIDI number, or REST for silence
    steps: int   # duration in 50 ms steps


def midi_to_freq(midi: int) -> float:
    """Frequency in Hz of a MIDI note number (A4 = 69 = 440 Hz)."""
    return 440.0 * 2.0 ** ((midi - 69) / 12.0)


def encode(notes: list[Note]) -> bytes:
    out = bytearray()
    for n in notes:
        pitch = n.pitch if (n.pitch == REST or MIDI_MIN <= n.pitch <= MIDI_MAX) else REST
        steps = max(1, min(255, n.steps))
        out.append(pitch)
        out.append(steps)
    return bytes(out)


def decode(payload: bytes) -> list[Note]:
    notes: list[Note] = []
    for i in range(0, len(payload) - 1, 2):  # drop an odd trailing byte
        pitch = payload[i]
        steps = payload[i + 1]
        if pitch != REST and not (MIDI_MIN <= pitch <= MIDI_MAX):
            pitch = REST
        notes.append(Note(pitch, steps))
    return notes
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_note_codec.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add src/note_codec.py tests/test_note_codec.py
git commit -m "feat(etapa2): note_codec — notes <-> bytes contract"
```

---

## Task 2: `pitch_detect` — potência de Goertzel numa frequência

**Files:**
- Create: `src/pitch_detect.py`
- Test: `tests/test_pitch_detect.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pitch_detect.py
import numpy as np

from src.pitch_detect import goertzel_power


def _sine(freq, n, fs):
    t = np.arange(n) / fs
    return 0.5 * np.sin(2 * np.pi * freq * t)


def test_goertzel_peaks_at_the_present_tone():
    fs = 8000
    sig = _sine(440.0, 1000, fs)
    p_on = goertzel_power(sig, 440.0, fs)
    p_off = goertzel_power(sig, 660.0, fs)  # a different (absent) frequency
    assert p_on > 50 * p_off


def test_goertzel_near_zero_for_silence():
    fs = 8000
    assert goertzel_power(np.zeros(1000), 440.0, fs) < 1e-6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pitch_detect.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.pitch_detect'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/pitch_detect.py
"""Pitch detection via a bank of Goertzel filters (one per musical note).

Goertzel computes the power at a single frequency with a 2nd-order IIR filter —
a narrow digital band-pass. A bank of them (one per semitone) is the digital
equivalent of a set of resonant LC circuits.
"""
from __future__ import annotations

import numpy as np

from src.note_codec import MIDI_MAX, MIDI_MIN, REST, Note, midi_to_freq

SAMPLE_RATE = 8000
HOP_MS = 50           # time granularity (also the note duration step)
WINDOW_MS = 125       # analysis window — wide enough to resolve low semitones
MIN_NOTE_STEPS = 2    # >= 100 ms to drop blips
SILENCE_RMS = 0.01    # below this RMS the window is silence


def goertzel_power(samples: np.ndarray, freq: float, fs: float) -> float:
    """Power at exactly `freq` (generalized Goertzel — no bin rounding)."""
    w = 2.0 * np.pi * freq / fs
    coeff = 2.0 * np.cos(w)
    s1 = 0.0
    s2 = 0.0
    for x in np.asarray(samples, dtype=float):
        s0 = x + coeff * s1 - s2
        s2 = s1
        s1 = s0
    return float(s1 * s1 + s2 * s2 - coeff * s1 * s2)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_pitch_detect.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/pitch_detect.py tests/test_pitch_detect.py
git commit -m "feat(etapa2): goertzel_power single-frequency detector"
```

---

## Task 3: `pitch_detect` — janela → nota e áudio → notas

**Files:**
- Modify: `src/pitch_detect.py`
- Test: `tests/test_pitch_detect.py`

- [ ] **Step 1: Write the failing test (append)**

```python
# tests/test_pitch_detect.py (append)
from src.note_codec import Note, REST
from src.pitch_detect import audio_to_notes, detect_window, SAMPLE_RATE


def test_detect_window_returns_correct_midi():
    from src.note_codec import midi_to_freq
    win = _sine(midi_to_freq(60), 1000, SAMPLE_RATE)  # C4
    assert detect_window(win, SAMPLE_RATE) == 60


def test_detect_window_silence_is_rest():
    assert detect_window(np.zeros(1000), SAMPLE_RATE) == REST


def test_audio_to_notes_segments_two_held_notes():
    from src.note_codec import midi_to_freq
    fs = SAMPLE_RATE
    # 0.5 s of C4 then 0.5 s of E4
    a = _sine(midi_to_freq(60), int(0.5 * fs), fs)
    b = _sine(midi_to_freq(64), int(0.5 * fs), fs)
    notes = audio_to_notes(np.concatenate([a, b]), fs)
    pitches = [n.pitch for n in notes]
    assert 60 in pitches and 64 in pitches
    assert pitches.index(60) < pitches.index(64)
    # ~0.5 s each => ~10 steps of 50 ms (allow tolerance)
    for n in notes:
        if n.pitch in (60, 64):
            assert 7 <= n.steps <= 12


def test_audio_to_notes_drops_blips():
    from src.note_codec import midi_to_freq
    fs = SAMPLE_RATE
    blip = _sine(midi_to_freq(67), int(0.05 * fs), fs)   # 50 ms < MIN
    held = _sine(midi_to_freq(60), int(0.5 * fs), fs)
    notes = audio_to_notes(np.concatenate([blip, held]), fs)
    assert all(n.pitch != 67 for n in notes)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pitch_detect.py -v`
Expected: FAIL with `ImportError: cannot import name 'audio_to_notes'`

- [ ] **Step 3: Write minimal implementation (append to `src/pitch_detect.py`)**

```python
# src/pitch_detect.py (append)
_CANDIDATES = list(range(MIDI_MIN, MIDI_MAX + 1))
_FREQS = {m: midi_to_freq(m) for m in _CANDIDATES}


def detect_window(window: np.ndarray, fs: float = SAMPLE_RATE,
                  silence_rms: float = SILENCE_RMS) -> int:
    """Return the dominant MIDI note in `window`, or REST if it is silence."""
    window = np.asarray(window, dtype=float)
    rms = float(np.sqrt(np.mean(window ** 2))) if window.size else 0.0
    if rms < silence_rms:
        return REST
    best_m = REST
    best_p = 0.0
    for m in _CANDIDATES:
        p = goertzel_power(window, _FREQS[m], fs)
        if p > best_p:
            best_p = p
            best_m = m
    return best_m


def audio_to_notes(audio: np.ndarray, fs: float = SAMPLE_RATE,
                   silence_rms: float = SILENCE_RMS) -> list[Note]:
    """Segment a float audio array ([-1,1]) into a list of Notes."""
    audio = np.asarray(audio, dtype=float)
    hop = int(round(fs * HOP_MS / 1000.0))
    win = int(round(fs * WINDOW_MS / 1000.0))
    if hop <= 0 or audio.size < hop:
        return []

    # Per-hop pitch over a trailing analysis window.
    pitches: list[int] = []
    for start in range(0, audio.size - hop + 1, hop):
        w0 = max(0, start + hop - win)
        pitches.append(detect_window(audio[w0:start + hop], fs, silence_rms))

    # Merge consecutive equal pitches into notes (steps = hop count).
    notes: list[Note] = []
    run_pitch = pitches[0]
    run_len = 1
    for p in pitches[1:]:
        if p == run_pitch:
            run_len += 1
        else:
            notes.append(Note(run_pitch, run_len))
            run_pitch, run_len = p, 1
    notes.append(Note(run_pitch, run_len))

    # Drop blips (too-short non-rest notes) and merge neighbours if a blip
    # sat between two equal notes would over-split; keep it simple: just drop.
    kept = [n for n in notes if n.pitch == REST or n.steps >= MIN_NOTE_STEPS]
    return kept
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_pitch_detect.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/pitch_detect.py tests/test_pitch_detect.py
git commit -m "feat(etapa2): audio_to_notes — Goertzel bank + segmentation"
```

---

## Task 4: `audio_synth` — notas → áudio

**Files:**
- Create: `src/audio_synth.py`
- Test: `tests/test_audio_synth.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_audio_synth.py
import numpy as np

from src.note_codec import Note, REST, midi_to_freq
from src.audio_synth import synthesize, PLAYBACK_RATE


def _dominant_freq(sig, fs):
    spec = np.abs(np.fft.rfft(sig))
    freqs = np.fft.rfftfreq(len(sig), 1 / fs)
    return freqs[int(np.argmax(spec))]


def test_synthesize_length_matches_duration():
    out = synthesize([Note(60, 8)])           # 8 * 50 ms = 0.4 s
    assert abs(len(out) - int(0.4 * PLAYBACK_RATE)) <= 2


def test_synthesize_dominant_frequency_matches_note():
    out = synthesize([Note(69, 20)])          # A4 = 440 Hz, 1 s
    f = _dominant_freq(out, PLAYBACK_RATE)
    assert abs(f - 440.0) < 5.0


def test_rest_is_silence():
    out = synthesize([Note(REST, 4)])
    assert np.max(np.abs(out)) < 1e-9


def test_no_clipping():
    out = synthesize([Note(60, 8), Note(64, 8), Note(67, 8)])
    assert np.max(np.abs(out)) <= 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_audio_synth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.audio_synth'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/audio_synth.py
"""Synthesize a list of Notes into a float audio waveform (the DAC stage)."""
from __future__ import annotations

import numpy as np

from src.note_codec import REST, Note, midi_to_freq

PLAYBACK_RATE = 44100
STEP_MS = 50
ENVELOPE_MS = 10
AMPLITUDE = 0.3


def synthesize(notes: list[Note], rate: int = PLAYBACK_RATE) -> np.ndarray:
    segments: list[np.ndarray] = []
    env_n = int(rate * ENVELOPE_MS / 1000.0)
    for note in notes:
        n = int(rate * note.steps * STEP_MS / 1000.0)
        if note.pitch == REST or n <= 0:
            segments.append(np.zeros(max(n, 0)))
            continue
        t = np.arange(n) / rate
        seg = AMPLITUDE * np.sin(2 * np.pi * midi_to_freq(note.pitch) * t)
        if env_n > 0 and n >= 2 * env_n:        # fade in/out — no clicks
            ramp = np.linspace(0.0, 1.0, env_n)
            seg[:env_n] *= ramp
            seg[-env_n:] *= ramp[::-1]
        segments.append(seg)
    return np.concatenate(segments) if segments else np.zeros(0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_audio_synth.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/audio_synth.py tests/test_audio_synth.py
git commit -m "feat(etapa2): audio_synth — notes -> waveform"
```

---

## Task 5: Teste de integração ponta a ponta (reusa `dsp` da etapa 1)

**Files:**
- Test: `tests/test_audio_integration.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_audio_integration.py
import numpy as np

from src import dsp, frame
from src.note_codec import Note, encode, decode
from src.audio_synth import synthesize, PLAYBACK_RATE
from tests.conftest import uart_bits_for_byte


def _led_signal(payload, fs=30.0, bit_rate=2.5):
    full = frame.build_frame(payload)
    bits = [1] * 20
    for byte in full:
        bits += uart_bits_for_byte(byte)
    bits += [1] * 20
    frames_per_bit = int(round(fs / bit_rate))
    sig = []
    for b in bits:
        sig += [float(b)] * frames_per_bit
    return np.array(sig) * 200 + 20


def test_notes_survive_the_full_light_channel():
    notes = [Note(60, 6), Note(64, 6), Note(67, 6)]
    payload = encode(notes)
    sig = _led_signal(payload)
    result = dsp.decode_signal(sig, fs=30.0, bit_rate=2.5)
    assert result.crc_ok, f"decode failed: {result.error}"
    assert decode(result.payload) == notes


def test_decoded_notes_synthesize_to_correct_pitches():
    notes = [Note(69, 20)]                    # A4
    payload = encode(notes)
    sig = _led_signal(payload)
    result = dsp.decode_signal(sig, fs=30.0, bit_rate=2.5)
    out = synthesize(decode(result.payload))
    spec = np.abs(np.fft.rfft(out))
    freqs = np.fft.rfftfreq(len(out), 1 / PLAYBACK_RATE)
    assert abs(freqs[int(np.argmax(spec))] - 440.0) < 5.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_audio_integration.py -v`
Expected: FAIL only if a prior task is incomplete; otherwise this should PASS once Tasks 1 & 4 exist. Run it to confirm the full loop holds.

- [ ] **Step 3: (no new implementation)**

This task adds no production code — it verifies Tasks 1–4 compose with the etapa-1 decoder. If it fails, fix the offending module from its own task.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_audio_integration.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add tests/test_audio_integration.py
git commit -m "test(etapa2): end-to-end notes->light->notes->synth"
```

---

## Task 6: Refactor `rx.py` — extrair `decoded_payloads()` (preserva comportamento)

**Files:**
- Modify: `src/rx.py` (function `main`)
- Test: `tests/test_rx_payloads.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_rx_payloads.py
import cv2
import numpy as np

from src import frame, rx
from tests.conftest import uart_bits_for_byte


def _write_blink_video(path, payload, fps=30.0, frames_per_bit=12):
    full = frame.build_frame(payload)
    bits = [1] * 20
    for byte in full:
        bits += uart_bits_for_byte(byte)
    bits += [1] * 20
    h, w = 240, 320
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    for b in bits:
        f = np.full((h, w, 3), 60, np.uint8)
        if b == 1:
            cv2.circle(f, (160, 120), 12, (0, 255, 0), -1)
        for _ in range(frames_per_bit):
            vw.write(f)
    vw.release()


def test_decoded_payloads_yields_payload_from_video(tmp_path):
    payload = b"\x3c\x06\x40\x06"             # two notes
    video = tmp_path / "blink.mp4"
    _write_blink_video(video, payload)
    args = rx._parse_args([
        "--mode", "color", "--input", str(video),
        "--fps", "30", "--bit-rate", "2.5", "--buffer-seconds", "80", "--no-gui",
    ])
    got = list(rx.decoded_payloads(args))
    assert payload in got
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_rx_payloads.py -v`
Expected: FAIL with `AttributeError: module 'src.rx' has no attribute '_parse_args'`

- [ ] **Step 3: Refactor `src/rx.py`**

In `src/rx.py`, split `main()` into an argument parser, a payload generator, and a thin `main`. Move the entire current body of `main()` (from `cap = cv2.VideoCapture(...)` through the `finally:`/`summary` print) into `decoded_payloads(args)`, changing the success branch to **also `yield`** the payload. Keep every existing `print(...)` exactly as-is (identical terminal output).

```python
# src/rx.py — replace the def main(...) signature/parsing section
def _parse_args(argv: list[str] | None = None):
    ap = argparse.ArgumentParser(description="LiFi RX (webcam + OpenCV + DSP)")
    ap.add_argument("--mode", choices=list(cv_pipeline.MODES), default="color")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--input", help="Video file to read instead of the camera")
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--bit-rate", type=float, default=5.0,
                    help="Optical bit rate in bps. MUST match the firmware: the "
                         "current tx.ino runs at 2.5 Hz, so use --bit-rate 2.5.")
    ap.add_argument("--buffer-seconds", type=float, default=75.0,
                    help="Sliding time window (seconds). Must be longer than one "
                         "full transmission.")
    ap.add_argument("--exposure", type=float, default=None,
                    help="Fix the camera exposure to keep fps stable. Try -5, -6, -7.")
    ap.add_argument("--no-gui", action="store_true", help="Console only (for CI/tests)")
    ap.add_argument("--display-every", type=int, default=3,
                    help="Render the GUI windows every Nth frame.")
    return ap.parse_args(argv)


def decoded_payloads(args):
    """Run the capture/decode loop, yielding each successfully decoded payload.

    Same side effects as the old main() (prints [OK], heartbeats, summary).
    """
    cap = cv2.VideoCapture(args.input if args.input else args.camera)
    if not cap.isOpened():
        print("error: cannot open video source", file=sys.stderr)
        return
    # ... (entire existing main() body, unchanged) ...
    # In the crc_ok branch, after the print(...) and signal_buf.clear()/ts_buf.clear():
    #     yield result.payload


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    for _ in decoded_payloads(args):
        pass
    return 0
```

> **Cuidado:** o corpo movido é o atual de `main()` sem mudanças, EXCETO: (1) trocar `return 2` por `return` (gerador não retorna valor), e (2) adicionar `yield result.payload` logo após `ts_buf.clear()` no ramo `if result.crc_ok:`. O `print` final de `summary:` permanece após o laço, dentro do `decoded_payloads`.

- [ ] **Step 4: Run test + full suite to verify behavior preserved**

Run: `pytest tests/test_rx_payloads.py -v && pytest -q`
Expected: PASS (the new test passes; all previous tests still pass).

- [ ] **Step 5: Commit**

```bash
git add src/rx.py tests/test_rx_payloads.py
git commit -m "refactor(rx): extract decoded_payloads() generator (behavior-preserving)"
```

---

## Task 7: `requirements.txt` + `audio_rx.py` (CLI: luz → som)

**Files:**
- Modify: `requirements.txt`
- Create: `src/audio_rx.py`
- Test: `tests/test_audio_synth.py` (add a CLI import smoke test)

- [ ] **Step 1: Add the dependency**

Append to `requirements.txt`:

```
sounddevice==0.4.6
```

- [ ] **Step 2: Write the failing smoke test (append to `tests/test_audio_synth.py`)**

```python
# tests/test_audio_synth.py (append)
def test_audio_rx_module_imports_and_has_play():
    import src.audio_rx as arx
    assert hasattr(arx, "play_payload")
    assert hasattr(arx, "main")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_audio_synth.py::test_audio_rx_module_imports_and_has_play -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.audio_rx'`

- [ ] **Step 4: Write `src/audio_rx.py`**

```python
# src/audio_rx.py
"""RX side: decode payloads from light (etapa 1), turn them into a melody, play it.

Usage:
  python -m src.audio_rx --mode white --bit-rate 2.5 --exposure -6 --buffer-seconds 140
"""
from __future__ import annotations

import sys

import numpy as np

from src import rx
from src.audio_synth import PLAYBACK_RATE, synthesize
from src.note_codec import decode, midi_to_freq


def _describe(notes) -> str:
    parts = []
    for n in notes:
        name = "pausa" if n.pitch == 0 else f"MIDI{n.pitch}~{midi_to_freq(n.pitch):.0f}Hz"
        parts.append(f"{name} {n.steps * 0.05:.2f}s")
    return " | ".join(parts)


def play_payload(payload: bytes) -> np.ndarray:
    """Decode a payload to notes, synthesize, and play. Returns the waveform."""
    notes = decode(payload)
    print(f"[MELODIA] {_describe(notes)}")
    wave = synthesize(notes)
    try:
        import sounddevice as sd
        sd.play(wave, PLAYBACK_RATE)
        sd.wait()
    except Exception as e:  # headless / no audio device
        print(f"(playback indisponível: {e})", file=sys.stderr)
    return wave


def main(argv: list[str] | None = None) -> int:
    args = rx._parse_args(argv)
    for payload in rx.decoded_payloads(args):
        play_payload(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run test + full suite**

Run: `pytest tests/test_audio_synth.py -v && pytest -q`
Expected: PASS. (The import test passes; `sounddevice` import is lazy inside `play_payload`, so the suite does not require an audio device.)

- [ ] **Step 6: Commit**

```bash
git add requirements.txt src/audio_rx.py tests/test_audio_synth.py
git commit -m "feat(etapa2): audio_rx CLI — light -> notes -> speaker"
```

---

## Task 8: `audio_tx.py` (CLI: mic → luz)

**Files:**
- Create: `src/audio_tx.py`
- Test: `tests/test_pitch_detect.py` (add a CLI import smoke test)

- [ ] **Step 1: Write the failing smoke test (append to `tests/test_pitch_detect.py`)**

```python
# tests/test_pitch_detect.py (append)
def test_audio_tx_module_imports():
    import src.audio_tx as atx
    assert hasattr(atx, "notes_to_serial")
    assert hasattr(atx, "main")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pitch_detect.py::test_audio_tx_module_imports -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.audio_tx'`

- [ ] **Step 3: Write `src/audio_tx.py`**

```python
# src/audio_tx.py
"""TX side: record the mic, detect the melody, send the notes over the LED.

Usage:
  python -m src.audio_tx --port COM4 --seconds 5
The receiver must run with the matching bit rate (the firmware is 2.5 bps):
  python -m src.audio_rx --mode white --bit-rate 2.5 --exposure -6 --buffer-seconds 140
"""
from __future__ import annotations

import argparse
import sys

import numpy as np

from src import frame
from src.audio_rx import _describe
from src.note_codec import encode
from src.pitch_detect import SAMPLE_RATE, audio_to_notes


def notes_to_serial(payload: bytes, port: str, baud: int = 115200) -> None:
    """Frame the payload and write it to the serial port (reuses etapa-1 frame)."""
    import serial  # pyserial, already a dependency
    full = frame.build_frame(payload)
    with serial.Serial(port, baud, timeout=1) as ser:
        ser.write(full)
    print(f"(enviados {len(full)} bytes: {len(payload)} payload + "
          f"{len(full) - len(payload)} overhead)")


def record(seconds: float, fs: int = SAMPLE_RATE) -> np.ndarray:
    import sounddevice as sd
    print(f"Gravando {seconds:.0f}s... cante/assovie a melodia agora.")
    audio = sd.rec(int(seconds * fs), samplerate=fs, channels=1, dtype="float32")
    sd.wait()
    return audio.flatten()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="LiFi audio TX (mic -> notes -> LED)")
    ap.add_argument("--port", required=True, help="Serial port (e.g. COM4)")
    ap.add_argument("--seconds", type=float, default=5.0)
    ap.add_argument("--max-notes", type=int, default=8,
                    help="Cap the melody length (the link is slow ~2.5 bps).")
    args = ap.parse_args(argv)

    audio = record(args.seconds)
    notes = audio_to_notes(audio, SAMPLE_RATE)[: args.max_notes]
    if not notes:
        print("Nenhuma nota detectada (silêncio?). Tente de novo.", file=sys.stderr)
        return 1
    print(f"[MELODIA] {_describe(notes)}")
    notes_to_serial(encode(notes), args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test + full suite**

Run: `pytest tests/test_pitch_detect.py -v && pytest -q`
Expected: PASS. (`sounddevice`/`serial` imports are lazy inside functions, so the suite needs neither a mic nor a serial port.)

- [ ] **Step 5: Commit**

```bash
git add src/audio_tx.py tests/test_pitch_detect.py
git commit -m "feat(etapa2): audio_tx CLI — mic -> notes -> LED"
```

---

## Task 9: Docs — checklist de hardware e README

**Files:**
- Create: `docs/HARDWARE_VERIFICATION_AUDIO.md`
- Modify: `README.md`

- [ ] **Step 1: Write `docs/HARDWARE_VERIFICATION_AUDIO.md`**

```markdown
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
```

- [ ] **Step 2: Add a section to `README.md`** (after the "Validation results" section)

```markdown
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
```

- [ ] **Step 3: Run full suite (sanity)**

Run: `pytest -q`
Expected: PASS (all tests green).

- [ ] **Step 4: Commit**

```bash
git add docs/HARDWARE_VERIFICATION_AUDIO.md README.md
git commit -m "docs(etapa2): hardware checklist + README for audio-over-light"
```

---

## Done

All tasks complete: melody-over-light end-to-end, with the etapa-1 pipeline reused and the full decode loop verified by automated tests (no hardware needed for CI). Mic capture and speaker playback are validated by the manual checklist in `docs/HARDWARE_VERIFICATION_AUDIO.md`.
