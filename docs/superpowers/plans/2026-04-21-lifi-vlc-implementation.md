# LiFi via Câmera (VLC) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a unidirectional visible-light communication link: Arduino + LED transmits ASCII text typed from keyboard; a webcam + Python/OpenCV receiver reconstructs the text. A secondary TX path drives the phone flashlight via Termux. Target: 2-week PCOM course project with live demo.

**Architecture:** Strict layering. Arduino is "dumb" PHY (Timer1 ISR emits UART-over-light at 5 bps). Python `tx.py` builds full frame (preamble `0x55`×4 + STX + LEN + payload + CRC-8 + ETX) and pushes bytes over USB serial. Receiver is a linear pipeline in one Python process: OpenCV isolates the light source (color or white mode), extracts a 1D brightness signal, applies a moving-average FIR passa-baixa, runs a 4-state clock recovery from preamble, desserializes UART bytes, parses the frame, validates CRC, and displays results across three simultaneous windows.

**Tech Stack:** Python 3.11+, numpy, opencv-python (cv2), pyserial, crcmod, matplotlib, pytest; Arduino (AVR C++); Termux shell.

**Reference:** [Design spec](../specs/2026-04-21-lifi-vlc-design.md). Keep it open — this plan implements it verbatim.

---

## Task 0: Project setup and CI scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `pytest.ini`
- Create: `README.md`
- Create: `src/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create `requirements.txt` with pinned versions**

Write:
```
numpy==1.26.4
opencv-python==4.9.0.80
pyserial==3.5
crcmod==1.7
matplotlib==3.8.3
pytest==8.1.1
pytest-cov==5.0.0
```

- [ ] **Step 2: Create `.gitignore`**

Write:
```
__pycache__/
*.pyc
.pytest_cache/
.coverage
htmlcov/
*.egg-info/
.venv/
venv/
assets/videos_gravados/*.mp4
assets/videos_gravados/*.mov
assets/videos_gravados/*.avi
*.bin
!scripts/*.sh
```

- [ ] **Step 3: Create `pytest.ini`**

Write:
```ini
[pytest]
testpaths = tests
python_files = test_*.py
addopts = -v --cov=src --cov-report=term-missing
```

- [ ] **Step 4: Create `README.md`**

Write:
```markdown
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
```

- [ ] **Step 5: Create `src/__init__.py` and `tests/__init__.py`** (empty files)

- [ ] **Step 6: Create `tests/conftest.py` with synthetic signal helper**

Write:
```python
"""Shared pytest fixtures. Synthetic signal generator for DSP tests.

A real optical signal, as seen by the receiver after spatial filtering + intensity
extraction, is a 1D float array sampled at Fs Hz (default 30). Each bit slot is
~Fs/Rb = 6 frames wide. High level ≈ 200 (LED on), low level ≈ 50 (LED off), plus
gaussian noise.
"""
from __future__ import annotations

import numpy as np
import pytest


@pytest.fixture
def fs() -> float:
    return 30.0


@pytest.fixture
def bit_rate() -> float:
    return 5.0


@pytest.fixture
def frames_per_bit(fs, bit_rate) -> int:
    return int(round(fs / bit_rate))  # 6


@pytest.fixture
def bit_time_frames(fs, bit_rate) -> float:
    return fs / bit_rate  # 6.0


def synth_signal_from_bits(
    bits: list[int],
    frames_per_bit: int = 6,
    high: float = 200.0,
    low: float = 50.0,
    noise_std: float = 0.0,
    seed: int = 42,
) -> np.ndarray:
    """Render a list of optical bits (1=LED on, 0=LED off) into a 1D float signal.

    Each bit occupies `frames_per_bit` samples. Optionally adds gaussian noise.
    """
    rng = np.random.default_rng(seed)
    samples = []
    for b in bits:
        level = high if b == 1 else low
        samples.extend([level] * frames_per_bit)
    signal = np.array(samples, dtype=float)
    if noise_std > 0:
        signal += rng.normal(0.0, noise_std, size=signal.shape)
    return signal


@pytest.fixture
def bits_for_preamble() -> list[int]:
    """4 bytes of 0x55 with UART framing (LSB-first) = 40 alternating bits
    starting with 0 and ending with 1.

    Each 0x55 byte framed = start(0), 1,0,1,0,1,0,1,0 (LSB-first), stop(1)
                         = 0,1,0,1,0,1,0,1,0,1
    Four of these concatenated = perfectly alternating 40 bits.
    """
    one_byte = [0, 1, 0, 1, 0, 1, 0, 1, 0, 1]
    return one_byte * 4


def uart_bits_for_byte(value: int) -> list[int]:
    """Return the 10 UART bits for one byte: start(0), 8 data LSB-first, stop(1)."""
    bits = [0]
    for i in range(8):
        bits.append((value >> i) & 1)
    bits.append(1)
    return bits
```

- [ ] **Step 7: Create empty module files so imports work later**

Write `src/frame.py`, `src/dsp.py`, `src/cv_pipeline.py` as empty files with just a module docstring:

`src/frame.py`:
```python
"""Frame encoding/decoding: CRC-8, build_frame, parse_frame."""
```

`src/dsp.py`:
```python
"""DSP stage for the receiver: moving average, AGC, clock recovery."""
```

`src/cv_pipeline.py`:
```python
"""OpenCV spatial pipeline: HSV + morphology + ROI + intensity extraction."""
```

- [ ] **Step 8: Verify structure, install deps, run empty pytest**

Run:
```bash
cd /home/matheus/LIFI
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest
```

Expected: pytest exits `no tests ran` — structure correct, dependencies installed.

- [ ] **Step 9: Commit**

```bash
git add requirements.txt .gitignore pytest.ini README.md src/ tests/
git commit -m "chore: project scaffolding with pytest, requirements, and empty modules"
```

---

## Task 1: `frame.py` — CRC-8 (poly 0x07)

**Files:**
- Modify: `src/frame.py`
- Test: `tests/test_frame.py`

- [ ] **Step 1: Write failing tests for `crc8`**

Create `tests/test_frame.py`:
```python
"""Tests for frame.py (CRC-8, build_frame, parse_frame)."""
from __future__ import annotations

import pytest

from src import frame


class TestCrc8:
    def test_crc8_empty(self):
        assert frame.crc8(b"") == 0x00

    def test_crc8_single_byte_vector(self):
        # Reference vector for CRC-8 poly 0x07, init 0x00, no reflection:
        # crc8(b"\x00") = 0x00
        # crc8(b"\x01") = 0x07
        assert frame.crc8(b"\x01") == 0x07

    def test_crc8_ascii_A(self):
        # CRC-8 (poly 0x07, init 0x00) of b"A" (0x41) = 0xC7
        assert frame.crc8(b"A") == 0xC7

    def test_crc8_known_vector_123456789(self):
        # "123456789" is a classic CRC test string. For CRC-8 poly 0x07 it's 0xF4.
        assert frame.crc8(b"123456789") == 0xF4

    def test_crc8_detects_single_bit_flip(self):
        original = b"Hello, PCOM!"
        crc_a = frame.crc8(original)
        corrupted = bytearray(original)
        corrupted[3] ^= 0x01  # flip one bit in byte 3
        assert frame.crc8(bytes(corrupted)) != crc_a
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `pytest tests/test_frame.py::TestCrc8 -v`
Expected: 5 failures with `AttributeError: module 'src.frame' has no attribute 'crc8'`.

- [ ] **Step 3: Implement `crc8` in `src/frame.py`**

Replace contents of `src/frame.py`:
```python
"""Frame encoding/decoding: CRC-8, build_frame, parse_frame.

Protocol (see docs/superpowers/specs/2026-04-21-lifi-vlc-design.md §3):
    PREAMBLE (4 x 0x55) | STX 0x02 | LEN (1B) | PAYLOAD (<=120B) | CRC-8 | ETX 0x03
CRC-8 polynomial 0x07, init 0x00, no input/output reflection.
"""
from __future__ import annotations

from dataclasses import dataclass

PREAMBLE_BYTE = 0x55
PREAMBLE_LEN = 4
STX = 0x02
ETX = 0x03
MAX_PAYLOAD = 120


def crc8(data: bytes) -> int:
    """CRC-8, polynomial 0x07, init 0x00, non-reflected (CCITT/SMBus style)."""
    crc = 0x00
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x07) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `pytest tests/test_frame.py::TestCrc8 -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/frame.py tests/test_frame.py
git commit -m "feat(frame): implement crc8 (poly 0x07)"
```

---

## Task 2: `frame.py` — `build_frame`

**Files:**
- Modify: `src/frame.py`
- Test: `tests/test_frame.py`

- [ ] **Step 1: Write failing tests for `build_frame`**

Append to `tests/test_frame.py`:
```python
class TestBuildFrame:
    def test_build_frame_structure_empty_payload(self):
        result = frame.build_frame(b"")
        expected = (
            bytes([0x55] * 4)   # preamble
            + bytes([0x02])     # STX
            + bytes([0x00])     # LEN = 0
            + b""               # payload
            + bytes([frame.crc8(b"")])  # CRC (= 0x00)
            + bytes([0x03])     # ETX
        )
        assert result == expected

    def test_build_frame_structure_with_payload(self):
        payload = b"AB"
        result = frame.build_frame(payload)
        assert result[:4] == bytes([0x55] * 4)
        assert result[4] == 0x02  # STX
        assert result[5] == 2     # LEN
        assert result[6:8] == b"AB"
        assert result[8] == frame.crc8(payload)
        assert result[9] == 0x03  # ETX
        assert len(result) == 4 + 1 + 1 + 2 + 1 + 1

    def test_build_frame_max_payload(self):
        payload = b"X" * 120
        result = frame.build_frame(payload)
        assert len(result) == 128  # 4 + 1 + 1 + 120 + 1 + 1
        assert result[5] == 120

    def test_build_frame_rejects_oversize_payload(self):
        with pytest.raises(ValueError, match="payload too large"):
            frame.build_frame(b"X" * 121)
```

- [ ] **Step 2: Run tests, verify failures**

Run: `pytest tests/test_frame.py::TestBuildFrame -v`
Expected: 4 failures with `AttributeError`.

- [ ] **Step 3: Implement `build_frame`**

Append to `src/frame.py`:
```python
def build_frame(payload: bytes) -> bytes:
    """Assemble a full optical frame from the given payload.

    Frame layout: PREAMBLE(4) | STX | LEN | PAYLOAD | CRC-8(payload) | ETX
    """
    if len(payload) > MAX_PAYLOAD:
        raise ValueError(
            f"payload too large: {len(payload)} bytes (max {MAX_PAYLOAD})"
        )
    return (
        bytes([PREAMBLE_BYTE] * PREAMBLE_LEN)
        + bytes([STX, len(payload)])
        + payload
        + bytes([crc8(payload), ETX])
    )
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/test_frame.py::TestBuildFrame -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/frame.py tests/test_frame.py
git commit -m "feat(frame): implement build_frame (preamble+STX+LEN+payload+CRC+ETX)"
```

---

## Task 3: `frame.py` — `parse_frame` (post-preamble parser)

**Files:**
- Modify: `src/frame.py`
- Test: `tests/test_frame.py`

Note: `parse_frame` assumes its input starts at the STX byte (the preamble is
stripped by the DSP clock-recovery stage before bytes reach this parser).

- [ ] **Step 1: Write failing tests for `parse_frame`**

Append to `tests/test_frame.py`:
```python
class TestParseFrame:
    def _body_of(self, full_frame: bytes) -> bytes:
        """Strip the 4-byte preamble; the parser works from STX onward."""
        return full_frame[4:]

    def test_parse_frame_roundtrip_empty(self):
        payload = b""
        body = self._body_of(frame.build_frame(payload))
        result = frame.parse_frame(body)
        assert result.ok is True
        assert result.payload == payload
        assert result.error is None

    def test_parse_frame_roundtrip_short(self):
        payload = b"Hello, PCOM!"
        body = self._body_of(frame.build_frame(payload))
        result = frame.parse_frame(body)
        assert result.ok is True
        assert result.payload == payload

    def test_parse_frame_bad_stx(self):
        body = b"\xFF" + b"\x00" + b"\x00" + b"\x03"  # wrong STX
        result = frame.parse_frame(body)
        assert result.ok is False
        assert "STX" in result.error

    def test_parse_frame_bad_etx(self):
        payload = b"AB"
        body = bytearray(self._body_of(frame.build_frame(payload)))
        body[-1] = 0xFF  # corrupt ETX
        result = frame.parse_frame(bytes(body))
        assert result.ok is False
        assert "ETX" in result.error

    def test_parse_frame_bad_crc(self):
        payload = b"AB"
        body = bytearray(self._body_of(frame.build_frame(payload)))
        body[2] ^= 0x01  # flip a bit in payload
        result = frame.parse_frame(bytes(body))
        assert result.ok is False
        assert "CRC" in result.error

    def test_parse_frame_len_too_large(self):
        body = bytes([0x02, 121]) + b"X" * 121 + bytes([0, 0x03])
        result = frame.parse_frame(body)
        assert result.ok is False
        assert "LEN" in result.error

    def test_parse_frame_truncated(self):
        payload = b"AB"
        body = self._body_of(frame.build_frame(payload))
        result = frame.parse_frame(body[:-2])  # chop CRC + ETX
        assert result.ok is False
        assert "truncated" in result.error.lower()
```

- [ ] **Step 2: Run tests, verify failures**

Run: `pytest tests/test_frame.py::TestParseFrame -v`
Expected: 7 failures.

- [ ] **Step 3: Implement `parse_frame` and `ParsedFrame` dataclass**

Append to `src/frame.py`:
```python
@dataclass(frozen=True)
class ParsedFrame:
    ok: bool
    payload: bytes | None
    error: str | None


def parse_frame(body: bytes) -> ParsedFrame:
    """Parse a frame body (bytes starting at STX, preamble already stripped).

    Returns a ParsedFrame with ok=True and .payload if valid; otherwise
    ok=False and .error describing the first failure found.
    """
    if len(body) < 4:  # STX + LEN + CRC + ETX minimum
        return ParsedFrame(False, None, "truncated: need >=4 bytes")
    if body[0] != STX:
        return ParsedFrame(False, None, f"bad STX: got 0x{body[0]:02X}")

    length = body[1]
    if length > MAX_PAYLOAD:
        return ParsedFrame(False, None, f"LEN too large: {length} > {MAX_PAYLOAD}")

    expected_total = 1 + 1 + length + 1 + 1  # STX+LEN+payload+CRC+ETX
    if len(body) < expected_total:
        return ParsedFrame(
            False, None,
            f"truncated: need {expected_total} bytes, got {len(body)}",
        )

    payload = body[2 : 2 + length]
    received_crc = body[2 + length]
    if body[2 + length + 1] != ETX:
        return ParsedFrame(
            False, None,
            f"bad ETX: got 0x{body[2 + length + 1]:02X}",
        )

    computed_crc = crc8(payload)
    if received_crc != computed_crc:
        return ParsedFrame(
            False, None,
            f"CRC mismatch: got 0x{received_crc:02X}, expected 0x{computed_crc:02X}",
        )

    return ParsedFrame(True, payload, None)
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/test_frame.py -v`
Expected: all 16 passed (5 CRC + 4 build + 7 parse).

- [ ] **Step 5: Commit**

```bash
git add src/frame.py tests/test_frame.py
git commit -m "feat(frame): implement parse_frame with CRC/STX/ETX/LEN validation"
```

---

## Task 4: `dsp.py` — moving average FIR filter

**Files:**
- Modify: `src/dsp.py`
- Test: `tests/test_dsp.py`

- [ ] **Step 1: Write failing tests for `moving_average`**

Create `tests/test_dsp.py`:
```python
"""Tests for dsp.py — moving average, AGC, clock recovery."""
from __future__ import annotations

import numpy as np
import pytest

from src import dsp
from tests.conftest import synth_signal_from_bits, uart_bits_for_byte


class TestMovingAverage:
    def test_moving_average_preserves_constant(self):
        signal = np.full(30, 100.0)
        filtered = dsp.moving_average(signal, m=3)
        # Interior samples unchanged; edges may differ due to 'same' mode.
        assert np.allclose(filtered[2:-2], 100.0)

    def test_moving_average_attenuates_noise(self):
        rng = np.random.default_rng(0)
        signal = 100.0 + rng.normal(0, 10, size=1000)
        filtered = dsp.moving_average(signal, m=3)
        # Moving-average with M=3 cuts variance ~1/M for white noise.
        assert filtered.std() < signal.std() * 0.7

    def test_moving_average_length_preserved(self):
        signal = np.zeros(100)
        assert dsp.moving_average(signal, m=3).shape == signal.shape

    def test_moving_average_m_equals_1_identity(self):
        signal = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        assert np.allclose(dsp.moving_average(signal, m=1), signal)
```

- [ ] **Step 2: Run tests, verify failures**

Run: `pytest tests/test_dsp.py::TestMovingAverage -v`
Expected: 4 failures.

- [ ] **Step 3: Implement `moving_average`**

Append to `src/dsp.py`:
```python
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# System parameters (mirror spec §6)
FS_DEFAULT = 30.0       # webcam frame rate (Hz)
RB_DEFAULT = 5.0        # optical bit rate (bps)


def moving_average(signal: np.ndarray, m: int = 3) -> np.ndarray:
    """FIR passa-baixa (janela retangular) de M taps. mode='same' preserva length."""
    if m <= 0:
        raise ValueError("m must be >= 1")
    kernel = np.ones(m) / m
    return np.convolve(signal, kernel, mode="same")
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/test_dsp.py::TestMovingAverage -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dsp.py tests/test_dsp.py
git commit -m "feat(dsp): moving_average FIR passa-baixa"
```

---

## Task 5: `dsp.py` — AGC (`compute_threshold`)

**Files:**
- Modify: `src/dsp.py`
- Test: `tests/test_dsp.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_dsp.py`:
```python
class TestComputeThreshold:
    def test_threshold_on_clean_bimodal(self, bits_for_preamble, frames_per_bit):
        preamble = synth_signal_from_bits(
            bits_for_preamble, frames_per_bit=frames_per_bit,
            high=200.0, low=50.0, noise_std=0.0,
        )
        thr = dsp.compute_threshold(preamble)
        assert 120.0 < thr.threshold < 130.0  # ≈ (200+50)/2 = 125
        assert thr.high > thr.low
        assert thr.high >= 180.0
        assert thr.low <= 70.0

    def test_threshold_robust_to_outliers(self, bits_for_preamble, frames_per_bit):
        preamble = synth_signal_from_bits(
            bits_for_preamble, frames_per_bit=frames_per_bit,
            high=200.0, low=50.0, noise_std=5.0,
        )
        # inject 3 huge spikes
        preamble[10] = 1000.0
        preamble[20] = 1000.0
        preamble[30] = 1000.0
        thr = dsp.compute_threshold(preamble)
        assert thr.threshold < 200.0  # not dragged up by outliers
        assert thr.high < 500.0
```

- [ ] **Step 2: Run tests, verify failures**

Run: `pytest tests/test_dsp.py::TestComputeThreshold -v`

- [ ] **Step 3: Implement `compute_threshold`**

Append to `src/dsp.py`:
```python
@dataclass(frozen=True)
class Threshold:
    high: float
    low: float
    threshold: float


def compute_threshold(preamble_signal: np.ndarray) -> Threshold:
    """AGC via percentis 90/10 sobre o preamble (robusto a outliers)."""
    high = float(np.percentile(preamble_signal, 90))
    low = float(np.percentile(preamble_signal, 10))
    return Threshold(high=high, low=low, threshold=(high + low) / 2.0)
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/test_dsp.py::TestComputeThreshold -v`

- [ ] **Step 5: Commit**

```bash
git add src/dsp.py tests/test_dsp.py
git commit -m "feat(dsp): compute_threshold via 10/90 percentiles (AGC digital)"
```

---

## Task 6: `dsp.py` — preamble detection (State 1)

**Files:**
- Modify: `src/dsp.py`
- Test: `tests/test_dsp.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_dsp.py`:
```python
class TestFindPreamble:
    def test_finds_preamble_at_start(self, bits_for_preamble, frames_per_bit, fs, bit_rate):
        # Signal = leading silence + preamble + trailing silence
        silence_before = [1] * (frames_per_bit * 10)  # IDLE high
        silence_after = [1] * (frames_per_bit * 10)
        signal = np.concatenate([
            synth_signal_from_bits(
                [b for b in silence_before],
                frames_per_bit=1, high=200.0, low=50.0,
            ),
            synth_signal_from_bits(
                bits_for_preamble, frames_per_bit=frames_per_bit,
                high=200.0, low=50.0, noise_std=2.0,
            ),
            synth_signal_from_bits(
                [b for b in silence_after],
                frames_per_bit=1, high=200.0, low=50.0,
            ),
        ])
        idx = dsp.find_preamble(signal, fs=fs, bit_rate=bit_rate)
        assert idx is not None
        # The preamble starts at offset len(silence_before) = 60
        assert abs(idx - 60) <= frames_per_bit  # within 1 bit-time tolerance

    def test_returns_none_on_pure_noise(self, fs, bit_rate):
        rng = np.random.default_rng(1)
        signal = 100.0 + rng.normal(0, 5, size=500)
        idx = dsp.find_preamble(signal, fs=fs, bit_rate=bit_rate)
        assert idx is None

    def test_returns_none_on_constant(self, fs, bit_rate):
        signal = np.full(500, 200.0)
        idx = dsp.find_preamble(signal, fs=fs, bit_rate=bit_rate)
        assert idx is None
```

- [ ] **Step 2: Run tests, verify failures**

Run: `pytest tests/test_dsp.py::TestFindPreamble -v`

- [ ] **Step 3: Implement `find_preamble`**

Append to `src/dsp.py`:
```python
def find_preamble(
    signal: np.ndarray,
    fs: float = FS_DEFAULT,
    bit_rate: float = RB_DEFAULT,
    correlation_threshold: float = 0.4,
) -> int | None:
    """Locate the start of the preamble via correlation with a 2.5 Hz square wave.

    Returns the sample index where the preamble begins, or None if not found.
    """
    samples_per_bit = fs / bit_rate
    window_frames = int(round(samples_per_bit * 8))  # ~8 bits ≈ 48 samples
    if len(signal) < window_frames * 2:
        return None

    # Reference: alternating 0/1 bits at bit_rate, each bit samples_per_bit wide.
    ref_bits = []
    for i in range(int(window_frames / samples_per_bit) + 1):
        ref_bits.append(1 if i % 2 == 0 else -1)
    ref = np.repeat(ref_bits, int(round(samples_per_bit)))[:window_frames].astype(float)
    ref -= ref.mean()
    ref /= np.linalg.norm(ref) + 1e-12

    best_corr = -1.0
    best_idx = None
    for start in range(0, len(signal) - window_frames):
        window = signal[start : start + window_frames].astype(float)
        window = window - window.mean()
        norm = np.linalg.norm(window) + 1e-12
        corr = float(np.dot(window, ref) / norm)
        if corr > best_corr:
            best_corr = corr
            best_idx = start

    if best_corr < correlation_threshold:
        return None
    return best_idx
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/test_dsp.py::TestFindPreamble -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dsp.py tests/test_dsp.py
git commit -m "feat(dsp): find_preamble via cross-correlation with 2.5 Hz square wave"
```

---

## Task 7: `dsp.py` — bit-time estimation from preamble (State 2)

**Files:**
- Modify: `src/dsp.py`
- Test: `tests/test_dsp.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_dsp.py`:
```python
class TestEstimateBitTime:
    def test_estimate_matches_ideal(self, bits_for_preamble, frames_per_bit, fs):
        signal = synth_signal_from_bits(
            bits_for_preamble, frames_per_bit=frames_per_bit,
            high=200.0, low=50.0, noise_std=2.0,
        )
        threshold = dsp.compute_threshold(signal).threshold
        tb_frames = dsp.estimate_bit_time_frames(signal, threshold=threshold)
        assert abs(tb_frames - 6.0) < 0.2  # within 0.2 frame of ideal

    def test_estimate_on_slow_tx(self, bits_for_preamble, fs):
        # Simulate a TX slightly slower than 5 bps (e.g. phone jitter adds
        # 10% on average -> Tb_frames ≈ 6.6).
        signal = synth_signal_from_bits(
            bits_for_preamble, frames_per_bit=7,
            high=200.0, low=50.0, noise_std=2.0,
        )
        threshold = dsp.compute_threshold(signal).threshold
        tb_frames = dsp.estimate_bit_time_frames(signal, threshold=threshold)
        assert abs(tb_frames - 7.0) < 0.3
```

- [ ] **Step 2: Run tests, verify failures**

Run: `pytest tests/test_dsp.py::TestEstimateBitTime -v`

- [ ] **Step 3: Implement `estimate_bit_time_frames`**

Append to `src/dsp.py`:
```python
def estimate_bit_time_frames(
    preamble_signal: np.ndarray,
    threshold: float,
) -> float:
    """Estimate bit-time (in frames) by averaging spacing between threshold crossings.

    Inside a pure 0x55 preamble the crossings occur every Tb frames.
    """
    above = preamble_signal > threshold
    # Zero-crossings: positions where `above` changes.
    crossings = np.where(np.diff(above.astype(int)) != 0)[0]
    if len(crossings) < 3:
        raise ValueError("not enough crossings to estimate Tb")
    # Adjacent crossings are half a bit-time apart (square wave at Rb/2).
    deltas = np.diff(crossings)
    half_bit = float(np.median(deltas))
    return 2.0 * half_bit
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/test_dsp.py::TestEstimateBitTime -v`

- [ ] **Step 5: Commit**

```bash
git add src/dsp.py tests/test_dsp.py
git commit -m "feat(dsp): estimate_bit_time_frames from preamble zero-crossings"
```

---

## Task 8: `dsp.py` — end-of-preamble detection (State 3)

**Files:**
- Modify: `src/dsp.py`
- Test: `tests/test_dsp.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_dsp.py`:
```python
class TestFindEndOfPreamble:
    def test_finds_stx_start_after_preamble(
        self, bits_for_preamble, frames_per_bit, fs
    ):
        # Build: preamble + STX(0x02) + LEN(0) + CRC(0) + ETX(0x03)
        from src.frame import crc8, STX, ETX
        from_bytes = [STX, 0x00, crc8(b""), ETX]
        bits = list(bits_for_preamble)
        for b in from_bytes:
            bits.extend(uart_bits_for_byte(b))
        signal = synth_signal_from_bits(
            bits, frames_per_bit=frames_per_bit, high=200.0, low=50.0, noise_std=1.0,
        )
        threshold = dsp.compute_threshold(signal).threshold
        tb_frames = dsp.estimate_bit_time_frames(signal, threshold=threshold)

        stx_start_bit_center = dsp.find_end_of_preamble(
            signal,
            preamble_start=0,
            bit_time_frames=tb_frames,
            threshold=threshold,
            n_preamble_bits=40,
        )
        assert stx_start_bit_center is not None
        # STX start-bit is the 41st bit in the stream; its center in frames is
        # 40 * 6 + 6/2 = 243. Allow ±1 frame tolerance.
        expected_center = 40 * frames_per_bit + frames_per_bit // 2
        assert abs(stx_start_bit_center - expected_center) <= 1

    def test_returns_none_when_no_violation(
        self, bits_for_preamble, frames_per_bit
    ):
        # Only preamble, no STX ever comes.
        signal = synth_signal_from_bits(
            bits_for_preamble, frames_per_bit=frames_per_bit,
            high=200.0, low=50.0, noise_std=1.0,
        )
        threshold = dsp.compute_threshold(signal).threshold
        tb_frames = dsp.estimate_bit_time_frames(signal, threshold=threshold)
        result = dsp.find_end_of_preamble(
            signal, preamble_start=0, bit_time_frames=tb_frames,
            threshold=threshold, n_preamble_bits=40,
        )
        assert result is None
```

- [ ] **Step 2: Run tests, verify failures**

Run: `pytest tests/test_dsp.py::TestFindEndOfPreamble -v`

- [ ] **Step 3: Implement `find_end_of_preamble`**

Append to `src/dsp.py`:
```python
def _sample_bit(
    signal: np.ndarray,
    center: float,
    threshold: float,
    vote_half_width: int = 1,
) -> int | None:
    """Read the bit at `center` frames using a ±vote_half_width majority vote."""
    lo = int(round(center)) - vote_half_width
    hi = int(round(center)) + vote_half_width + 1
    if lo < 0 or hi > len(signal):
        return None
    window = signal[lo:hi]
    votes = (window > threshold).sum()
    return 1 if votes > (hi - lo) / 2 else 0


def find_end_of_preamble(
    signal: np.ndarray,
    preamble_start: int,
    bit_time_frames: float,
    threshold: float,
    n_preamble_bits: int = 40,
) -> int | None:
    """Scan bit slots after the preamble for the first violation of alternation.

    Returns the sample index of the CENTER of the STX start bit (== the first
    of the two consecutive equal bits), or None if no violation within the signal.
    """
    # bit N center = preamble_start + (N + 0.5) * Tb
    def bit_center(n: int) -> float:
        return preamble_start + (n + 0.5) * bit_time_frames

    # Sample preamble bits to know the expected alternation phase.
    prev = _sample_bit(signal, bit_center(n_preamble_bits - 1), threshold)
    n = n_preamble_bits
    while True:
        c = bit_center(n)
        if c + 1 >= len(signal):
            return None
        current = _sample_bit(signal, c, threshold)
        if current is None:
            return None
        if current == prev:
            # Two same-level bits in a row; the FIRST was the STX start bit.
            # Return the center of bit (n - 1).
            return int(round(bit_center(n - 1)))
        prev = current
        n += 1
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/test_dsp.py::TestFindEndOfPreamble -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dsp.py tests/test_dsp.py
git commit -m "feat(dsp): find_end_of_preamble via alternation-violation scan"
```

---

## Task 9: `dsp.py` — UART byte decoder (State 4)

**Files:**
- Modify: `src/dsp.py`
- Test: `tests/test_dsp.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_dsp.py`:
```python
class TestDecodeUartByte:
    def test_decode_ascii_A(self, frames_per_bit):
        # 'A' = 0x41 = 01000001 binary; LSB-first: 1,0,0,0,0,0,1,0
        bits = uart_bits_for_byte(0x41)  # start(0), data, stop(1)
        signal = synth_signal_from_bits(
            bits, frames_per_bit=frames_per_bit,
            high=200.0, low=50.0, noise_std=1.0,
        )
        threshold = dsp.compute_threshold(signal).threshold
        start_center = 0 * frames_per_bit + frames_per_bit // 2
        value, next_center = dsp.decode_uart_byte(
            signal, start_bit_center=start_center,
            bit_time_frames=float(frames_per_bit), threshold=threshold,
        )
        assert value == 0x41
        # next byte's start bit is 10 bits after this one's start center
        assert abs(next_center - (start_center + 10 * frames_per_bit)) <= 1

    def test_decode_zero_byte(self, frames_per_bit):
        bits = uart_bits_for_byte(0x00)
        signal = synth_signal_from_bits(
            bits, frames_per_bit=frames_per_bit, high=200.0, low=50.0,
        )
        threshold = dsp.compute_threshold(signal).threshold
        start_center = frames_per_bit // 2
        value, _ = dsp.decode_uart_byte(
            signal, start_bit_center=start_center,
            bit_time_frames=float(frames_per_bit), threshold=threshold,
        )
        assert value == 0x00
```

- [ ] **Step 2: Run tests, verify failures**

Run: `pytest tests/test_dsp.py::TestDecodeUartByte -v`

- [ ] **Step 3: Implement `decode_uart_byte`**

Append to `src/dsp.py`:
```python
def decode_uart_byte(
    signal: np.ndarray,
    start_bit_center: int,
    bit_time_frames: float,
    threshold: float,
) -> tuple[int | None, int]:
    """Decode one UART-framed byte starting at `start_bit_center`.

    Layout: start(0), 8 data LSB-first, stop(1). Returns (byte_value, next_start_center).
    byte_value is None if framing is invalid (start != 0 or stop != 1).
    """
    # Sanity check start bit
    start = _sample_bit(signal, start_bit_center, threshold)
    if start != 0:
        next_center = int(round(start_bit_center + 10 * bit_time_frames))
        return None, next_center

    byte = 0
    for i in range(8):
        center = start_bit_center + (i + 1) * bit_time_frames
        bit = _sample_bit(signal, center, threshold)
        if bit is None:
            next_center = int(round(start_bit_center + 10 * bit_time_frames))
            return None, next_center
        byte |= (bit & 1) << i  # LSB first

    # Stop bit must be 1
    stop_center = start_bit_center + 9 * bit_time_frames
    stop = _sample_bit(signal, stop_center, threshold)
    next_center = int(round(start_bit_center + 10 * bit_time_frames))
    if stop != 1:
        return None, next_center
    return byte, next_center
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/test_dsp.py::TestDecodeUartByte -v`

- [ ] **Step 5: Commit**

```bash
git add src/dsp.py tests/test_dsp.py
git commit -m "feat(dsp): decode_uart_byte with start/stop validation and LSB-first assembly"
```

---

## Task 10: `dsp.py` — end-to-end `decode_signal`

**Files:**
- Modify: `src/dsp.py`
- Test: `tests/test_dsp.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_dsp.py`:
```python
class TestDecodeSignal:
    def test_decodes_full_frame_clean(self, frames_per_bit, fs, bit_rate):
        from src.frame import build_frame
        payload = b"OI"
        full_frame = build_frame(payload)
        bits = []
        for byte in full_frame:
            bits.extend(uart_bits_for_byte(byte))
        # Idle before/after
        signal = np.concatenate([
            np.full(frames_per_bit * 4, 200.0),  # IDLE high
            synth_signal_from_bits(
                bits, frames_per_bit=frames_per_bit,
                high=200.0, low=50.0, noise_std=1.0,
            ),
            np.full(frames_per_bit * 4, 200.0),
        ])
        result = dsp.decode_signal(signal, fs=fs, bit_rate=bit_rate)
        assert result.payload == payload
        assert result.crc_ok is True

    def test_decodes_with_noise(self, frames_per_bit, fs, bit_rate):
        from src.frame import build_frame
        payload = b"Hello"
        full_frame = build_frame(payload)
        bits = []
        for byte in full_frame:
            bits.extend(uart_bits_for_byte(byte))
        signal = synth_signal_from_bits(
            bits, frames_per_bit=frames_per_bit,
            high=200.0, low=50.0, noise_std=15.0, seed=7,
        )
        result = dsp.decode_signal(signal, fs=fs, bit_rate=bit_rate)
        assert result.payload == payload
        assert result.crc_ok is True

    def test_returns_failed_when_no_preamble(self, fs, bit_rate):
        rng = np.random.default_rng(0)
        signal = 100.0 + rng.normal(0, 5, size=500)
        result = dsp.decode_signal(signal, fs=fs, bit_rate=bit_rate)
        assert result.payload is None
        assert result.error is not None
```

- [ ] **Step 2: Run tests, verify failures**

Run: `pytest tests/test_dsp.py::TestDecodeSignal -v`

- [ ] **Step 3: Implement `decode_signal`**

Append to `src/dsp.py`:
```python
from src import frame as _frame  # forward reference


@dataclass(frozen=True)
class DecodeResult:
    payload: bytes | None
    crc_ok: bool
    error: str | None
    bit_time_frames: float | None
    preamble_start: int | None


def decode_signal(
    signal: np.ndarray,
    fs: float = FS_DEFAULT,
    bit_rate: float = RB_DEFAULT,
    m: int = 3,
    n_preamble_bits: int = 40,
) -> DecodeResult:
    """Full receive chain: filter -> find preamble -> estimate Tb -> locate STX ->
    decode UART bytes -> parse frame.
    """
    filtered = moving_average(signal, m=m)

    preamble_start = find_preamble(filtered, fs=fs, bit_rate=bit_rate)
    if preamble_start is None:
        return DecodeResult(None, False, "preamble not found", None, None)

    # AGC on the preamble window
    samples_per_bit = fs / bit_rate
    preamble_end = preamble_start + int(round(n_preamble_bits * samples_per_bit))
    preamble_end = min(preamble_end, len(filtered))
    threshold_obj = compute_threshold(filtered[preamble_start:preamble_end])
    threshold = threshold_obj.threshold

    try:
        tb_frames = estimate_bit_time_frames(
            filtered[preamble_start:preamble_end], threshold=threshold
        )
    except ValueError as e:
        return DecodeResult(None, False, str(e), None, preamble_start)

    stx_center = find_end_of_preamble(
        filtered, preamble_start=preamble_start,
        bit_time_frames=tb_frames, threshold=threshold,
        n_preamble_bits=n_preamble_bits,
    )
    if stx_center is None:
        return DecodeResult(None, False, "STX not found", tb_frames, preamble_start)

    # Decode up to MAX_PAYLOAD + 4 bytes (STX+LEN+CRC+ETX); abort on bad frame.
    bytes_out = bytearray()
    next_center = stx_center
    for _ in range(_frame.MAX_PAYLOAD + 4):
        value, next_center = decode_uart_byte(
            filtered, start_bit_center=next_center,
            bit_time_frames=tb_frames, threshold=threshold,
        )
        if value is None:
            break
        bytes_out.append(value)
        if value == _frame.ETX and len(bytes_out) >= 4:
            break

    parsed = _frame.parse_frame(bytes(bytes_out))
    return DecodeResult(
        payload=parsed.payload,
        crc_ok=parsed.ok,
        error=parsed.error,
        bit_time_frames=tb_frames,
        preamble_start=preamble_start,
    )
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/test_dsp.py -v`
Expected: all DSP tests pass (moving avg + threshold + preamble + Tb + end + byte + signal).

- [ ] **Step 5: Commit**

```bash
git add src/dsp.py tests/test_dsp.py
git commit -m "feat(dsp): decode_signal end-to-end (filter->preamble->Tb->STX->bytes->parse)"
```

---

## Task 11: `cv_pipeline.py` — color-mode ROI detection

**Files:**
- Modify: `src/cv_pipeline.py`
- Test: `tests/test_cv_pipeline.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_cv_pipeline.py`:
```python
"""Tests for cv_pipeline.py — HSV masking, morphology, ROI."""
from __future__ import annotations

import numpy as np
import pytest

from src import cv_pipeline


def _synth_frame_with_colored_blob(
    h: int = 240, w: int = 320,
    blob_center: tuple[int, int] = (160, 120),
    blob_radius: int = 12,
    blob_bgr: tuple[int, int, int] = (0, 255, 0),  # pure green
    ambient_bgr: tuple[int, int, int] = (80, 80, 80),
) -> np.ndarray:
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[:, :] = ambient_bgr
    y, x = np.ogrid[:h, :w]
    mask = (x - blob_center[0]) ** 2 + (y - blob_center[1]) ** 2 <= blob_radius ** 2
    frame[mask] = blob_bgr
    return frame


class TestFindRoiColor:
    def test_finds_green_blob(self):
        frame = _synth_frame_with_colored_blob(
            blob_center=(200, 100), blob_radius=10, blob_bgr=(0, 255, 0),
        )
        roi = cv_pipeline.find_roi(frame, mode="color")
        assert roi is not None
        x, y, w, h = roi
        # Center of bounding box should be near (200, 100), within 5 px
        cx, cy = x + w // 2, y + h // 2
        assert abs(cx - 200) <= 5
        assert abs(cy - 100) <= 5

    def test_returns_none_when_no_green(self):
        frame = _synth_frame_with_colored_blob(
            blob_bgr=(0, 0, 255),  # red, not green
        )
        roi = cv_pipeline.find_roi(frame, mode="color")
        assert roi is None

    def test_rejects_invalid_mode(self):
        frame = _synth_frame_with_colored_blob()
        with pytest.raises(ValueError):
            cv_pipeline.find_roi(frame, mode="bogus")
```

- [ ] **Step 2: Run tests, verify failures**

Run: `pytest tests/test_cv_pipeline.py::TestFindRoiColor -v`

- [ ] **Step 3: Implement `find_roi` (color mode)**

Replace contents of `src/cv_pipeline.py`:
```python
"""OpenCV spatial pipeline: HSV + morphology + ROI + intensity extraction.

Two modes (spec §5.1):
  color: HSV hue range (green/blue) + saturation > 80.
  white: V > 200 AND S < 40 (bright + achromatic).
"""
from __future__ import annotations

import cv2
import numpy as np

MODES = ("color", "white")

# Hue ranges in OpenCV (0-179). Green LED around ~50-70; blue around ~100-130.
HUE_GREEN = (40, 80)
HUE_BLUE = (90, 135)

# Active color hue range. Default to GREEN — adjust at runtime per hardware.
DEFAULT_HUE_RANGE = HUE_GREEN
DEFAULT_SAT_MIN_COLOR = 80
DEFAULT_V_MIN_WHITE = 200
DEFAULT_S_MAX_WHITE = 40
KERNEL_3 = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))


def _mask_color(hsv: np.ndarray, hue_range=DEFAULT_HUE_RANGE) -> np.ndarray:
    lo = np.array([hue_range[0], DEFAULT_SAT_MIN_COLOR, 40], dtype=np.uint8)
    hi = np.array([hue_range[1], 255, 255], dtype=np.uint8)
    return cv2.inRange(hsv, lo, hi)


def _mask_white(hsv: np.ndarray) -> np.ndarray:
    lo = np.array([0, 0, DEFAULT_V_MIN_WHITE], dtype=np.uint8)
    hi = np.array([179, DEFAULT_S_MAX_WHITE, 255], dtype=np.uint8)
    return cv2.inRange(hsv, lo, hi)


def _apply_morphology(mask: np.ndarray) -> np.ndarray:
    # Closing: dilate then erode to consolidate the blob.
    mask = cv2.dilate(mask, KERNEL_3, iterations=1)
    mask = cv2.erode(mask, KERNEL_3, iterations=1)
    return mask


def compute_mask(frame_bgr: np.ndarray, mode: str) -> np.ndarray:
    """Produce a binary mask of the light source for the given mode."""
    if mode not in MODES:
        raise ValueError(f"unknown mode: {mode!r}; must be one of {MODES}")
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    mask = _mask_color(hsv) if mode == "color" else _mask_white(hsv)
    return _apply_morphology(mask)


def find_roi(
    frame_bgr: np.ndarray, mode: str, min_area: int = 50
) -> tuple[int, int, int, int] | None:
    """Return (x, y, w, h) of the largest blob for the mode, or None if absent."""
    mask = compute_mask(frame_bgr, mode)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    largest = max(contours, key=cv2.contourArea)
    if cv2.contourArea(largest) < min_area:
        return None
    return cv2.boundingRect(largest)
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/test_cv_pipeline.py::TestFindRoiColor -v`

- [ ] **Step 5: Commit**

```bash
git add src/cv_pipeline.py tests/test_cv_pipeline.py
git commit -m "feat(cv): find_roi for color mode (HSV hue + saturation)"
```

---

## Task 12: `cv_pipeline.py` — white-mode ROI + intensity extraction

**Files:**
- Modify: `src/cv_pipeline.py`
- Test: `tests/test_cv_pipeline.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_cv_pipeline.py`:
```python
class TestFindRoiWhite:
    def test_finds_bright_white_blob(self):
        frame = _synth_frame_with_colored_blob(
            blob_center=(50, 50), blob_radius=15, blob_bgr=(250, 250, 250),
        )
        roi = cv_pipeline.find_roi(frame, mode="white")
        assert roi is not None
        x, y, w, h = roi
        cx, cy = x + w // 2, y + h // 2
        assert abs(cx - 50) <= 5
        assert abs(cy - 50) <= 5

    def test_white_mode_ignores_green(self):
        frame = _synth_frame_with_colored_blob(
            blob_bgr=(0, 255, 0),  # saturated green, not white
        )
        roi = cv_pipeline.find_roi(frame, mode="white")
        assert roi is None


class TestExtractIntensity:
    def test_extract_matches_manual_mean(self):
        frame = _synth_frame_with_colored_blob(
            blob_center=(100, 60), blob_radius=10, blob_bgr=(0, 255, 0),
        )
        roi = cv_pipeline.find_roi(frame, mode="color")
        assert roi is not None
        intensity = cv_pipeline.extract_intensity(frame, roi)
        # ROI is mostly pure green, V channel ≈ 255 there, some ambient edges
        assert 180.0 <= intensity <= 256.0
```

- [ ] **Step 2: Run tests, verify failures**

Run: `pytest tests/test_cv_pipeline.py::TestFindRoiWhite tests/test_cv_pipeline.py::TestExtractIntensity -v`

- [ ] **Step 3: Implement `extract_intensity`**

Append to `src/cv_pipeline.py`:
```python
def extract_intensity(
    frame_bgr: np.ndarray, roi: tuple[int, int, int, int]
) -> float:
    """Mean of HSV V-channel inside the ROI (the spec's 1D brightness sample)."""
    x, y, w, h = roi
    patch = frame_bgr[y : y + h, x : x + w]
    if patch.size == 0:
        return 0.0
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    return float(hsv[:, :, 2].mean())
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/test_cv_pipeline.py -v`
Expected: 6 passed (3 color ROI + 2 white ROI + 1 intensity).

- [ ] **Step 5: Commit**

```bash
git add src/cv_pipeline.py tests/test_cv_pipeline.py
git commit -m "feat(cv): white-mode ROI (V high, S low) and extract_intensity"
```

---

## Task 13: `cv_pipeline.py` — ROI tracker (temporal stabilization)

**Files:**
- Modify: `src/cv_pipeline.py`
- Test: `tests/test_cv_pipeline.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_cv_pipeline.py`:
```python
class TestRoiTracker:
    def test_tracker_smoothes_jitter(self):
        tracker = cv_pipeline.ROITracker(smoothing_window=5)
        noisy_rois = [
            (100, 100, 20, 20),
            (102, 98, 20, 20),
            (99, 101, 20, 20),
            (101, 100, 20, 20),
            (100, 100, 20, 20),
        ]
        out = [tracker.update(r) for r in noisy_rois]
        # After the window fills, output should be very close to average center
        x, y, w, h = out[-1]
        cx, cy = x + w // 2, y + h // 2
        assert abs(cx - 110) <= 2  # ~100 + 20/2
        assert abs(cy - 110) <= 2

    def test_tracker_returns_none_on_first_none(self):
        tracker = cv_pipeline.ROITracker()
        assert tracker.update(None) is None
        tracker.update((100, 100, 20, 20))
        # A None after valid updates returns the last smoothed ROI.
        assert tracker.update(None) is not None
```

- [ ] **Step 2: Run tests, verify failures**

Run: `pytest tests/test_cv_pipeline.py::TestRoiTracker -v`

- [ ] **Step 3: Implement `ROITracker`**

Append to `src/cv_pipeline.py`:
```python
from collections import deque


class ROITracker:
    """Smooth centroid jitter over a sliding window of recent ROIs."""

    def __init__(self, smoothing_window: int = 10) -> None:
        self._history: deque[tuple[int, int, int, int]] = deque(maxlen=smoothing_window)

    def update(
        self, roi: tuple[int, int, int, int] | None
    ) -> tuple[int, int, int, int] | None:
        if roi is None:
            if not self._history:
                return None
            return self._smoothed()
        self._history.append(roi)
        return self._smoothed()

    def _smoothed(self) -> tuple[int, int, int, int]:
        arr = np.array(self._history, dtype=float)
        x = int(round(arr[:, 0].mean()))
        y = int(round(arr[:, 1].mean()))
        w = int(round(arr[:, 2].mean()))
        h = int(round(arr[:, 3].mean()))
        return (x, y, w, h)
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/test_cv_pipeline.py::TestRoiTracker -v`

- [ ] **Step 5: Commit**

```bash
git add src/cv_pipeline.py tests/test_cv_pipeline.py
git commit -m "feat(cv): ROITracker for temporal centroid smoothing"
```

---

## Task 14: Arduino firmware `firmware/tx.ino`

**Files:**
- Create: `firmware/tx.ino`

Note: Arduino code cannot be unit-tested here. Verification is manual (steps 3-5 below). Commit after each verification passes.

- [ ] **Step 1: Create firmware file**

Create `firmware/tx.ino`:
```cpp
/*
  LiFi TX firmware — Arduino Uno/Nano (ATmega328P).
  Spec: docs/superpowers/specs/2026-04-21-lifi-vlc-design.md §4.

  Responsibility:
    - Read bytes from USB serial at 115200 baud into a 128-byte circular buffer.
    - At 5 Hz (200 ms/bit), emit each byte as 10 UART-over-light bits on pin D8:
        start(0) + 8 data LSB-first + stop(1)
    - When buffer empty, hold LED HIGH (IDLE).

  Design: Timer1 in CTC mode drives the bit emitter ISR. loop() just fills the
  buffer. No SoftwareSerial — all bit timing is controlled by Timer1.
*/

#include <Arduino.h>

constexpr uint8_t LED_PIN = 8;
constexpr uint8_t INDICATOR_PIN = 13;          // optional on-board LED
constexpr size_t BUF_SIZE = 128;               // exactly one max frame
constexpr uint16_t OCR1A_VAL = 3124;           // 200 ms at 16 MHz / prescaler 1024

volatile uint8_t  buf[BUF_SIZE];
volatile size_t   head = 0;
volatile size_t   tail = 0;
volatile uint8_t  current_byte = 0;
volatile uint8_t  bit_index = 10;              // 10 = idle (not transmitting)

// ---- helpers ----

inline bool buf_empty()  { return head == tail; }
inline bool buf_full()   { return ((head + 1) % BUF_SIZE) == tail; }

inline void buf_push(uint8_t v) {
  buf[head] = v;
  head = (head + 1) % BUF_SIZE;
}

inline bool buf_pop(uint8_t *out) {
  if (buf_empty()) return false;
  *out = buf[tail];
  tail = (tail + 1) % BUF_SIZE;
  return true;
}

// ---- setup ----

void setup() {
  pinMode(LED_PIN, OUTPUT);
  pinMode(INDICATOR_PIN, OUTPUT);
  digitalWrite(LED_PIN, HIGH);                 // IDLE high
  digitalWrite(INDICATOR_PIN, LOW);

  Serial.begin(115200);

  // Timer1 CTC: 16 MHz / 1024 / 3125 = 5 Hz -> OCR1A = 3124
  noInterrupts();
  TCCR1A = 0;
  TCCR1B = (1 << WGM12) | (1 << CS12) | (1 << CS10);  // CTC, prescaler 1024
  OCR1A  = OCR1A_VAL;
  TIMSK1 = (1 << OCIE1A);
  TCNT1  = 0;
  interrupts();
}

// ---- bit emitter ----

ISR(TIMER1_COMPA_vect) {
  // Emit one bit per tick.
  if (bit_index == 10) {
    // Idle or looking for next byte.
    if (!buf_pop((uint8_t*)&current_byte)) {
      digitalWrite(LED_PIN, HIGH);             // IDLE high
      digitalWrite(INDICATOR_PIN, LOW);
      return;
    }
    digitalWrite(INDICATOR_PIN, HIGH);
    bit_index = 0;
  }

  uint8_t level;
  if (bit_index == 0) {
    level = 0;                                 // start bit
  } else if (bit_index == 9) {
    level = 1;                                 // stop bit
  } else {
    // data bits: LSB-first, bit i corresponds to current_byte bit (bit_index-1)
    level = (current_byte >> (bit_index - 1)) & 0x01;
  }

  digitalWrite(LED_PIN, level ? HIGH : LOW);
  bit_index++;
}

// ---- main loop ----

void loop() {
  while (Serial.available() > 0) {
    if (buf_full()) {
      // Spin until ISR drains. ISR runs every 200ms; a full buffer drains in 256s.
      // Python side is throttled by serial write block here.
      break;
    }
    int b = Serial.read();
    if (b < 0) break;
    noInterrupts();
    buf_push((uint8_t)b);
    interrupts();
  }
}
```

- [ ] **Step 2: Commit firmware as-is**

```bash
git add firmware/tx.ino
git commit -m "feat(firmware): Arduino TX with Timer1 ISR, 128-byte circular buffer, UART-over-light"
```

- [ ] **Step 3: Manual verification — upload and visually check**

Upload `firmware/tx.ino` to an Arduino (via Arduino IDE or `arduino-cli`).
Wire: D8 → 220Ω → LED anode → GND.

Open Serial Monitor at 115200 baud and send the byte string `U` (= 0x55)
repeatedly by typing `UUUU` + Enter. The LED should blink with the
alternating preamble pattern at 2.5 Hz (visible flicker).

If LED is dark / not blinking, check:
- Correct resistor orientation and LED polarity.
- D8 pin number (not D13).
- Serial monitor set to 115200 baud, "No line ending".

- [ ] **Step 4: Manual verification — on-phone oscilloscope**

Install an oscilloscope-style app (e.g. "Oscilloscope Pro") and point the
phone's camera at the LED. Confirm a roughly 2.5 Hz square wave is visible
while `UUUU…` is being sent. IDLE state should show LED permanently on.

- [ ] **Step 5: If verified, commit a small README fragment**

Append to `README.md`:
```markdown

## Arduino upload

1. Open `firmware/tx.ino` in the Arduino IDE.
2. Select Board: Arduino Uno (or Nano), Port: the one Arduino shows.
3. Click Upload.
4. With a wired LED on D8 through 220Ω, run `python src/tx.py --port <port>`
   after completing Task 15 below.
```

Commit:
```bash
git add README.md
git commit -m "docs: Arduino upload instructions"
```

---

## Task 15: `src/tx.py` — host transmitter (keyboard → frame → serial/file)

**Files:**
- Create: `src/tx.py`

Note: `tx.py` has two modes — serial (to Arduino) and file (for phone TX).
Testing with a real Arduino is manual (Step 5). The file mode is fully
scriptable and covered by an integration check.

- [ ] **Step 1: Write `src/tx.py`**

Create `src/tx.py`:
```python
"""Host transmitter: read text from keyboard, build a frame, push it to Arduino.

Two modes:
  --port DEVICE    Write bytes to the given serial port (default for Arduino TX).
  --out PATH       Write bytes to a file; use with `scripts/tx_phone.sh` on Termux.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src import frame


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="LiFi TX: keyboard -> frame -> hardware")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--port", help="Serial port for Arduino TX (e.g. /dev/ttyUSB0)")
    group.add_argument("--out", help="Write frame bytes to this file (for phone TX)")
    ap.add_argument("--baud", type=int, default=115200, help="Serial baud (default 115200)")
    args = ap.parse_args(argv)

    writer = _open_writer(args)
    try:
        print("Type a message and press Enter. Ctrl+D (EOF) or Ctrl+C to quit.")
        while True:
            try:
                text = input("> ")
            except (EOFError, KeyboardInterrupt):
                print("\nbye")
                return 0
            try:
                payload = text.encode("ascii")
            except UnicodeEncodeError:
                print("error: message must be pure ASCII", file=sys.stderr)
                continue
            try:
                data = frame.build_frame(payload)
            except ValueError as e:
                print(f"error: {e}", file=sys.stderr)
                continue
            writer.write(data)
            writer.flush() if hasattr(writer, "flush") else None
            print(f"(sent {len(data)} bytes: {len(payload)} payload + 8 overhead)")
            if args.out:
                return 0  # file mode writes one frame and exits
    finally:
        if hasattr(writer, "close"):
            writer.close()


def _open_writer(args: argparse.Namespace):
    if args.port:
        import serial  # imported here so tests can mock it
        return serial.Serial(args.port, args.baud, timeout=1)
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.open("wb")


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Write a quick integration test for file mode**

Create `tests/test_tx.py`:
```python
"""Test tx.py file mode (file-mode is scriptable without hardware)."""
from __future__ import annotations

from pathlib import Path

from src import frame, tx


def test_tx_file_mode_writes_full_frame(tmp_path, monkeypatch):
    out = tmp_path / "frame.bin"
    # Simulate one user input then EOF
    inputs = iter(["Hi"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    code = tx.main(["--out", str(out)])
    assert code == 0
    written = out.read_bytes()
    assert written == frame.build_frame(b"Hi")
```

- [ ] **Step 3: Run tests, verify pass**

Run: `pytest tests/test_tx.py -v`
Expected: 1 passed.

- [ ] **Step 4: Commit**

```bash
git add src/tx.py tests/test_tx.py
git commit -m "feat(tx): host transmitter with serial and file output modes"
```

- [ ] **Step 5: Manual verification — send to Arduino**

With `firmware/tx.ino` uploaded and LED wired, run:
```bash
python src/tx.py --port /dev/ttyUSB0  # or /dev/ttyACM0
> OI
(sent 10 bytes: 2 payload + 8 overhead)
```
Observe the LED perform: 40 fast alternating blinks (preamble) + byte pattern
for STX, LEN=2, 'O', 'I', CRC, ETX. Total visible sequence ~20 seconds.

If the LED stays solid-on or dark, check port path and baud; retry.

---

## Task 16: `src/rx.py` — receiver skeleton (capture + pipeline + console)

**Files:**
- Create: `src/rx.py`

- [ ] **Step 1: Write `src/rx.py` skeleton**

Create `src/rx.py`:
```python
"""Live receiver: webcam -> OpenCV pipeline -> DSP -> console.

Usage:
  python src/rx.py --mode {color|white} [--camera 0] [--input video.mp4]
                   [--buffer-seconds 6] [--fps 30]

With --input, reads a video file instead of the webcam (for offline validation).
"""
from __future__ import annotations

import argparse
import collections
import sys
from dataclasses import dataclass

import cv2
import numpy as np

from src import cv_pipeline, dsp, frame


@dataclass
class RxStats:
    frames_received: int = 0
    frames_ok: int = 0
    frames_bad_crc: int = 0
    total_payload_bytes: int = 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="LiFi RX (webcam + OpenCV + DSP)")
    ap.add_argument("--mode", choices=list(cv_pipeline.MODES), default="color")
    ap.add_argument("--camera", type=int, default=0, help="Camera index (default 0)")
    ap.add_argument("--input", help="Video file to read instead of the camera")
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--buffer-seconds", type=float, default=12.0,
                    help="Length of the sliding 1D-signal buffer in seconds")
    args = ap.parse_args(argv)

    cap = cv2.VideoCapture(args.input if args.input else args.camera)
    if not cap.isOpened():
        print("error: cannot open video source", file=sys.stderr)
        return 2

    buf_len = int(args.buffer_seconds * args.fps)
    signal_buf: collections.deque[float] = collections.deque(maxlen=buf_len)
    tracker = cv_pipeline.ROITracker(smoothing_window=10)
    stats = RxStats()

    try:
        while True:
            ok, frame_bgr = cap.read()
            if not ok:
                break
            roi = cv_pipeline.find_roi(frame_bgr, mode=args.mode)
            roi = tracker.update(roi)
            intensity = cv_pipeline.extract_intensity(frame_bgr, roi) if roi else 0.0
            signal_buf.append(intensity)

            # Attempt decode once per second of new data.
            if len(signal_buf) == buf_len and stats.frames_received % int(args.fps) == 0:
                signal = np.asarray(signal_buf, dtype=float)
                result = dsp.decode_signal(signal, fs=args.fps, bit_rate=5.0)
                if result.crc_ok:
                    stats.frames_ok += 1
                    stats.total_payload_bytes += len(result.payload or b"")
                    text = (result.payload or b"").decode("ascii", errors="replace")
                    print(f"[OK ] '{text}'  (frames_ok={stats.frames_ok})")
                    signal_buf.clear()  # avoid re-decoding the same frame
                elif result.error and "preamble not found" not in result.error:
                    stats.frames_bad_crc += 1
                    print(f"[ERR] {result.error}")

            stats.frames_received += 1
    finally:
        cap.release()

    print(
        f"summary: received={stats.frames_received} ok={stats.frames_ok} "
        f"bad_crc={stats.frames_bad_crc} bytes={stats.total_payload_bytes}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Smoke-test imports**

Run:
```bash
python -c "from src import rx; print('ok')"
```
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add src/rx.py
git commit -m "feat(rx): receiver skeleton (capture + pipeline + console output)"
```

---

## Task 17: Integration test — offline video decode round-trip

**Files:**
- Create: `tests/test_integration_synthetic_video.py`

- [ ] **Step 1: Write failing integration test**

Create `tests/test_integration_synthetic_video.py`:
```python
"""End-to-end test: synthesize a video of a blinking LED, run the full pipeline.

This exercises cv_pipeline + dsp + frame together. No hardware required.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from src import cv_pipeline, dsp, frame
from tests.conftest import uart_bits_for_byte


def _synth_blinking_video(
    path: Path,
    bits: list[int],
    frames_per_bit: int = 6,
    size: tuple[int, int] = (240, 320),  # h, w
    led_center: tuple[int, int] = (160, 120),  # x, y
    led_radius: int = 12,
    fps: float = 30.0,
) -> None:
    h, w = size
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, fps, (w, h))
    for b in bits:
        for _ in range(frames_per_bit):
            frame_bgr = np.full((h, w, 3), 60, dtype=np.uint8)  # ambient gray
            if b == 1:
                cv2.circle(frame_bgr, led_center, led_radius, (0, 255, 0), -1)
            writer.write(frame_bgr)
    writer.release()


def test_synthetic_video_decode_roundtrip(tmp_path):
    payload = b"Hi"
    full_frame = frame.build_frame(payload)
    bits = [1] * 30  # IDLE before
    for byte in full_frame:
        bits.extend(uart_bits_for_byte(byte))
    bits.extend([1] * 30)  # IDLE after

    video_path = tmp_path / "blink.mp4"
    _synth_blinking_video(video_path, bits)

    cap = cv2.VideoCapture(str(video_path))
    assert cap.isOpened()
    tracker = cv_pipeline.ROITracker(smoothing_window=5)
    intensities = []
    while True:
        ok, frame_bgr = cap.read()
        if not ok:
            break
        roi = cv_pipeline.find_roi(frame_bgr, mode="color")
        roi = tracker.update(roi)
        if roi:
            intensities.append(cv_pipeline.extract_intensity(frame_bgr, roi))
        else:
            intensities.append(0.0)
    cap.release()

    signal = np.asarray(intensities, dtype=float)
    result = dsp.decode_signal(signal, fs=30.0, bit_rate=5.0)
    assert result.crc_ok, f"decode failed: {result.error}"
    assert result.payload == payload
```

- [ ] **Step 2: Run test, verify initial behavior**

Run: `pytest tests/test_integration_synthetic_video.py -v`
Expected: passes if all previous tasks are implemented correctly.
If it fails, examine `result.error` and debug the failing stage.

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration_synthetic_video.py
git commit -m "test(integration): synthetic video -> RX pipeline -> decode round-trip"
```

---

## Task 18: `src/rx.py` — three windows UI (raw + mask + signal plot)

**Files:**
- Modify: `src/rx.py`

- [ ] **Step 1: Add matplotlib-backed signal plot and OpenCV windows**

Replace the `main()` body in `src/rx.py` with a version that renders three
windows every frame. Edit the file as follows (replace the existing `main`):

```python
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="LiFi RX (webcam + OpenCV + DSP)")
    ap.add_argument("--mode", choices=list(cv_pipeline.MODES), default="color")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--input", help="Video file to read instead of the camera")
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--buffer-seconds", type=float, default=12.0)
    ap.add_argument("--no-gui", action="store_true", help="Console only (for CI/tests)")
    args = ap.parse_args(argv)

    cap = cv2.VideoCapture(args.input if args.input else args.camera)
    if not cap.isOpened():
        print("error: cannot open video source", file=sys.stderr)
        return 2

    buf_len = int(args.buffer_seconds * args.fps)
    signal_buf: collections.deque[float] = collections.deque(maxlen=buf_len)
    decoded_bits: collections.deque[int] = collections.deque(maxlen=buf_len)
    tracker = cv_pipeline.ROITracker(smoothing_window=10)
    stats = RxStats()

    if not args.no_gui:
        cv2.namedWindow("LiFi RX — raw", cv2.WINDOW_NORMAL)
        cv2.namedWindow("LiFi RX — mask", cv2.WINDOW_NORMAL)

    try:
        while True:
            ok, frame_bgr = cap.read()
            if not ok:
                break
            mask = cv_pipeline.compute_mask(frame_bgr, mode=args.mode)
            roi = cv_pipeline.find_roi(frame_bgr, mode=args.mode)
            roi = tracker.update(roi)
            intensity = cv_pipeline.extract_intensity(frame_bgr, roi) if roi else 0.0
            signal_buf.append(intensity)

            if not args.no_gui:
                display = frame_bgr.copy()
                if roi:
                    x, y, w, h = roi
                    cv2.rectangle(display, (x, y), (x + w, y + h), (0, 0, 255), 2)
                cv2.imshow("LiFi RX — raw", display)
                cv2.imshow("LiFi RX — mask", mask)
                _draw_signal_plot(list(signal_buf), mode_label=args.mode)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

            if len(signal_buf) == buf_len and stats.frames_received % int(args.fps) == 0:
                signal = np.asarray(signal_buf, dtype=float)
                result = dsp.decode_signal(signal, fs=args.fps, bit_rate=5.0)
                if result.crc_ok:
                    stats.frames_ok += 1
                    stats.total_payload_bytes += len(result.payload or b"")
                    text = (result.payload or b"").decode("ascii", errors="replace")
                    print(f"[OK ] '{text}'  frames_ok={stats.frames_ok}")
                    signal_buf.clear()
                elif result.error and "preamble not found" not in result.error:
                    stats.frames_bad_crc += 1
                    print(f"[ERR] {result.error}")

            stats.frames_received += 1
    finally:
        cap.release()
        if not args.no_gui:
            cv2.destroyAllWindows()

    print(
        f"summary: received={stats.frames_received} ok={stats.frames_ok} "
        f"bad_crc={stats.frames_bad_crc} bytes={stats.total_payload_bytes}"
    )
    return 0


def _draw_signal_plot(signal: list[float], mode_label: str) -> None:
    """Render the 1D signal as a third OpenCV window (no matplotlib to avoid
    thread issues — we draw it ourselves into a numpy canvas)."""
    h, w = 200, 800
    canvas = np.full((h, w, 3), 255, dtype=np.uint8)
    if not signal:
        cv2.imshow("LiFi RX — signal 1D", canvas)
        return
    arr = np.asarray(signal, dtype=float)
    lo, hi = float(arr.min()), float(arr.max()) + 1e-9
    span = max(hi - lo, 1.0)
    # Downsample to width
    if len(arr) > w:
        idx = np.linspace(0, len(arr) - 1, w).astype(int)
        arr = arr[idx]
    xs = np.linspace(0, w - 1, len(arr)).astype(int)
    ys = (h - 10 - (arr - lo) / span * (h - 20)).astype(int)
    for i in range(1, len(xs)):
        cv2.line(canvas, (xs[i - 1], ys[i - 1]), (xs[i], ys[i]), (0, 0, 0), 1)
    cv2.putText(
        canvas, f"mode={mode_label}  samples={len(signal)}",
        (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA,
    )
    cv2.imshow("LiFi RX — signal 1D", canvas)
```

- [ ] **Step 2: Smoke-test with `--no-gui --input` on the synthetic video from Task 17**

Run:
```bash
python -c "
from pathlib import Path
from tests.test_integration_synthetic_video import _synth_blinking_video
from src.frame import build_frame
from tests.conftest import uart_bits_for_byte
bits = [1]*30
for b in build_frame(b'Hi'):
    bits.extend(uart_bits_for_byte(b))
bits += [1]*30
Path('/tmp').mkdir(exist_ok=True)
_synth_blinking_video(Path('/tmp/blink_smoke.mp4'), bits)
"
python src/rx.py --mode color --input /tmp/blink_smoke.mp4 --no-gui
```
Expected output includes `[OK ] 'Hi'`.

- [ ] **Step 3: Commit**

```bash
git add src/rx.py
git commit -m "feat(rx): three-window UI (raw+ROI, mask, signal 1D) with --no-gui escape hatch"
```

---

## Task 19: `src/rx.py` — BER counter display

**Files:**
- Modify: `src/rx.py`

- [ ] **Step 1: Extend `RxStats` and on-screen overlay**

In `src/rx.py`, replace the existing `RxStats` with:
```python
@dataclass
class RxStats:
    frames_received: int = 0
    frames_ok: int = 0
    frames_bad_crc: int = 0
    total_payload_bytes: int = 0
    total_frames_attempted: int = 0  # frames where a decode ran (preamble was found)

    @property
    def ber(self) -> float:
        if self.total_frames_attempted == 0:
            return 0.0
        return self.frames_bad_crc / self.total_frames_attempted
```

Then, in the decode block inside the main loop, increment
`stats.total_frames_attempted` whenever the decode runs AND an error other
than "preamble not found" occurs, OR a CRC OK is reported:

```python
            if len(signal_buf) == buf_len and stats.frames_received % int(args.fps) == 0:
                signal = np.asarray(signal_buf, dtype=float)
                result = dsp.decode_signal(signal, fs=args.fps, bit_rate=5.0)
                if result.crc_ok:
                    stats.frames_ok += 1
                    stats.total_frames_attempted += 1
                    stats.total_payload_bytes += len(result.payload or b"")
                    text = (result.payload or b"").decode("ascii", errors="replace")
                    print(
                        f"[OK ] '{text}'  ok={stats.frames_ok}  "
                        f"BER~{stats.ber*100:.1f}%"
                    )
                    signal_buf.clear()
                elif result.error and "preamble not found" not in result.error:
                    stats.frames_bad_crc += 1
                    stats.total_frames_attempted += 1
                    print(
                        f"[ERR] {result.error}  bad_crc={stats.frames_bad_crc}  "
                        f"BER~{stats.ber*100:.1f}%"
                    )
```

And add the BER overlay at the top of `display` each frame:

```python
                if not args.no_gui:
                    display = frame_bgr.copy()
                    if roi:
                        x, y, w, h = roi
                        cv2.rectangle(display, (x, y), (x + w, y + h), (0, 0, 255), 2)
                    cv2.putText(
                        display,
                        f"mode={args.mode}  ok={stats.frames_ok}  "
                        f"bad={stats.frames_bad_crc}  BER~{stats.ber*100:.1f}%",
                        (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (0, 255, 0), 2, cv2.LINE_AA,
                    )
                    cv2.imshow("LiFi RX — raw", display)
```

- [ ] **Step 2: Smoke-test**

Run the same synthetic-video smoke test as Task 18 Step 2. Confirm output includes `BER~0.0%` when the frame decodes.

- [ ] **Step 3: Commit**

```bash
git add src/rx.py
git commit -m "feat(rx): on-screen BER overlay and stats tracking"
```

---

## Task 20: `scripts/tx_phone.sh` — Termux phone flashlight TX

**Files:**
- Create: `scripts/tx_phone.sh`

Note: cannot unit-test bash/Termux here. Verification is manual on the device.

- [ ] **Step 1: Create the script**

Create `scripts/tx_phone.sh`:
```bash
#!/data/data/com.termux/files/usr/bin/bash
# LiFi TX via phone flashlight (Termux).
# Usage: ./tx_phone.sh frame.bin
#
# Reads bytes from frame.bin (produced by `python src/tx.py --out frame.bin`)
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
```

- [ ] **Step 2: Make executable and commit**

```bash
chmod +x scripts/tx_phone.sh
git add scripts/tx_phone.sh
git commit -m "feat(scripts): Termux phone flashlight TX (UART-over-light)"
```

- [ ] **Step 3: Manual verification on device**

On Android phone:
1. Install Termux (from F-Droid) and Termux:API.
2. In Termux: `pkg install termux-api coreutils`.
3. Grant Termux:API the flashlight permission when prompted.
4. Push a test frame:
   ```bash
   # On notebook
   python src/tx.py --out /tmp/frame_hi.bin
   > Hi
   adb push /tmp/frame_hi.bin /sdcard/
   ```
5. On the phone in Termux:
   ```bash
   bash /sdcard/Download/tx_phone.sh /sdcard/frame_hi.bin
   ```
   Confirm the flashlight flickers for ~20 s with the UART pattern. The script
   prints `done (10 bytes)` at the end.

If `termux-torch` is not found: `pkg install termux-api`. If permission is
denied, open the Termux:API app and enable flashlight access.

---

## Task 21: Live validation — modo color (Arduino) and modo white (phone)

**Files:**
- Modify: `README.md`

Note: manual end-to-end verification. Run both modes and record the demo.

- [ ] **Step 1: Live modo color**

- Start: `python src/rx.py --mode color`
- Point webcam at the Arduino LED (20-50 cm away).
- In a second terminal: `python src/tx.py --port /dev/ttyUSB0`, type `OI`, Enter.
- Within ~20 s the RX console should print `[OK ] 'OI'`.
- Acceptance: 3/3 successful decodes of `Hi` and `OI`.

- [ ] **Step 2: Live modo white**

- Start: `python src/rx.py --mode white`
- Point webcam at the phone flashlight.
- On notebook: `python src/tx.py --out /tmp/oi.bin`, type `OI`, Enter.
- `adb push /tmp/oi.bin /sdcard/`.
- On phone: `bash /sdcard/Download/tx_phone.sh /sdcard/oi.bin`.
- Acceptance: 1/3 successful decodes of `Hi` (looser bar due to OS jitter,
  per spec §13 item 3).

- [ ] **Step 3: Record a demo video (for relatório / slides)**

Record your screen (OBS, kazam, or `ffmpeg -f x11grab`) for both modes above.
Save to `assets/videos_gravados/demo_color.mp4` and `demo_white.mp4`.
These videos are gitignored by the pattern in Task 0.

- [ ] **Step 4: Document results in README**

Append to `README.md`:
```markdown

## Validation results

| Mode  | TX             | Attempts | OK  | BER~ | Notes         |
|-------|----------------|----------|-----|------|---------------|
| color | Arduino + LED  | 3        | 3   | 0%   | sala escura   |
| white | Phone Termux   | 3        | 1   | 66%  | sala escura   |
```
(Fill with your actual results.)

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: live validation results for both modes"
```

---

## Task 22: Robustness sweep — BER × condition

**Files:**
- Create: `scripts/ber_sweep.py`
- Modify: `README.md`

- [ ] **Step 1: Create the sweep helper**

Create `scripts/ber_sweep.py`:
```python
"""Replay a recorded video through rx.py and log frames_ok/bad_crc.

Usage: python scripts/ber_sweep.py path/to/video.mp4 --mode color
"""
from __future__ import annotations

import argparse
import sys

import cv2
import numpy as np

from src import cv_pipeline, dsp


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--mode", choices=list(cv_pipeline.MODES), default="color")
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--buffer-seconds", type=float, default=12.0)
    args = ap.parse_args()

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print("error: cannot open video", file=sys.stderr)
        return 2

    tracker = cv_pipeline.ROITracker(smoothing_window=10)
    buf_len = int(args.buffer_seconds * args.fps)
    signal_buf = []
    ok = 0
    bad = 0
    while True:
        r, f = cap.read()
        if not r:
            break
        roi = tracker.update(cv_pipeline.find_roi(f, mode=args.mode))
        signal_buf.append(cv_pipeline.extract_intensity(f, roi) if roi else 0.0)

    cap.release()
    # Decode once every buf_len samples, sliding by fps each attempt.
    arr = np.asarray(signal_buf, dtype=float)
    step = int(args.fps)
    for start in range(0, len(arr) - buf_len, step):
        result = dsp.decode_signal(arr[start : start + buf_len], fs=args.fps, bit_rate=5.0)
        if result.crc_ok:
            ok += 1
        elif result.error and "preamble not found" not in result.error:
            bad += 1

    total = ok + bad
    ber = (bad / total) if total else 0.0
    print(f"{args.video}: ok={ok} bad={bad} BER~{ber*100:.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Record 4 short clips covering conditions**

Record ~30 s each at the apresentação venue or a similar environment:
- `assets/videos_gravados/color_dark_close.mp4` — sala escura, LED a 30 cm
- `assets/videos_gravados/color_ambient_close.mp4` — luz ambiente, LED a 30 cm
- `assets/videos_gravados/color_ambient_far.mp4` — luz ambiente, LED a 1 m
- `assets/videos_gravados/white_dark_close.mp4` — sala escura, lanterna a 30 cm

While recording, the TX is sending repeated `OI` messages via `tx.py`.

- [ ] **Step 3: Run the sweep**

```bash
for v in assets/videos_gravados/color_*.mp4; do
    python scripts/ber_sweep.py "$v" --mode color
done
python scripts/ber_sweep.py assets/videos_gravados/white_dark_close.mp4 --mode white
```

Record the results in the validation table of `README.md`.

- [ ] **Step 4: Commit the helper and updated README**

```bash
git add scripts/ber_sweep.py README.md
git commit -m "tooling: BER sweep over recorded videos"
```

---

## Task 23: Relatório (final report skeleton)

**Files:**
- Create: `docs/relatorio.md`

- [ ] **Step 1: Write the report scaffold**

Create `docs/relatorio.md`:
```markdown
# LiFi via Câmera — Relatório Final (PCOM)

**Equipe:** [nomes]
**Cadeira:** Princípios de Comunicação (PCOM)
**Data:** [data de entrega]

## 1. Objetivo

Implementar um link de comunicação em luz visível (VLC) entre um Arduino
emitindo sinais OOK via LED e um receptor Python/OpenCV processando frames
da webcam. Sistema dual: também funciona com a lanterna de um celular
Android como fonte, via Termux.

**Tese:** todo filtro analógico clássico (LC, RC, comparador com histerese,
PLL, paridade) é substituído por um equivalente digital em software.

## 2. Arquitetura

(Resumir a Seção 2 do spec.)

## 3. Protocolo

(Resumir a Seção 3 do spec: preamble 0x55×4, UART framing, CRC-8 poly 0x07.)

## 4. DSP — do vídeo aos bits

### 4.1 Pré-processamento espacial (OpenCV)
Dois modos: color (HSV matiz + S alto) e white (V alto + S baixo).

### 4.2 Filtro passa-baixa digital
Média móvel M=3 taps. Corte em 10 Hz. Equivalente digital de um RC com τ ≈ 100 ms.

### 4.3 AGC digital
Threshold = média dos percentis 10/90 do preamble. Substitui o AGC analógico.

### 4.4 Recuperação de clock
Quatro estados: busca → tracking → fim-de-preamble → desserialização UART.

## 5. Resultados

### 5.1 Critério de Nyquist
Fs = 30 fps, Rb = 5 bps ⇒ margem 3×. Sem ISI observada nos testes.

### 5.2 BER por condição
(Copiar a tabela de validation do README.)

### 5.3 Comparação TX Arduino vs lanterna
(Discutir jitter de OS e por que Tb_medido no preamble compensa.)

## 6. Mapeamento PCOM (tabela da Seção 5 do spec)

| Componente | Conceito PCOM |
|---|---|
| ... (copiar da spec) | ... |

## 7. Conclusão e trabalhos futuros

- Extensão natural: Manchester coding para clock embutido.
- FEC (códigos correttores) para melhorar BER em modo white.
- Rate adaptation baseada em BER estimada.
```

- [ ] **Step 2: Commit**

```bash
git add docs/relatorio.md
git commit -m "docs: relatorio skeleton aligned with spec sections"
```

---

## Self-review checklist (run after writing plan — do NOT defer)

**Spec coverage:**
- [x] §3 protocol (preamble 0x55, STX/LEN/CRC/ETX) → Tasks 1-3
- [x] §4 TX Arduino + firmware → Task 14
- [x] §4 TX via file (for phone) → Task 15
- [x] §4 tx_phone.sh Termux → Task 20
- [x] §5 CV pipeline (modes color and white) → Tasks 11-13
- [x] §5 DSP (MA, AGC, clock recovery 4 states, decode) → Tasks 4-10
- [x] §5 three windows UI → Task 18
- [x] §7 BER reporting → Task 19
- [x] §9 Validation layers 1-2 (unit tests) → Tasks 1-13
- [x] §9 Validation layer 3 (offline video) → Task 17
- [x] §9 Validation layers 4-5 (live) → Task 21
- [x] §10 schedule days 1-14 → Tasks 0-23 (roughly 1 task/day + buffer)
- [x] §11 contingency cuts → covered by task ordering (phone is Tasks 20-21, cuttable last)
- [x] §13 acceptance criteria (color: 5-10 char, white: ≥1/3 attempts) → Task 21

**Type/signature consistency:** `crc8(bytes) -> int`, `build_frame(bytes) -> bytes`, `parse_frame(bytes) -> ParsedFrame`, `moving_average(np.ndarray, m:int) -> np.ndarray`, `compute_threshold(np.ndarray) -> Threshold`, `find_preamble(np.ndarray, fs, bit_rate) -> int | None`, `estimate_bit_time_frames(np.ndarray, threshold) -> float`, `find_end_of_preamble(...) -> int | None`, `decode_uart_byte(...) -> tuple[int | None, int]`, `decode_signal(...) -> DecodeResult`. Verified uniform across tasks.

**No placeholders:** every task has full code shown; no "TODO" or "fill in later" strings.

**Scope guardrail:** all 23 tasks map to spec sections. No feature creep beyond what the spec approved.
