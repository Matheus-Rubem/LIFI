"""DSP stage for the receiver: moving average, AGC, clock recovery."""
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


def find_preamble(
    signal: np.ndarray,
    fs: float = FS_DEFAULT,
    bit_rate: float = RB_DEFAULT,
    correlation_threshold: float = 0.85,
) -> int | None:
    """Locate the start of the preamble via correlation with a 2.5 Hz square wave.

    Real-time behavior: return the FIRST (earliest) sample index whose correlation
    with the reference exceeds the threshold. A valid preamble is always before
    any data, so the first strong match is the preamble; looking for the global
    max can be fooled by bit sequences in the payload that happen to alternate.

    Two candidate polarities are tried (the phase of the alternating pattern can
    start with 0 or with 1, because the preamble stream begins with a start bit).
    The first start index at which either polarity meets the threshold wins; we
    then refine to the local peak within the first bit-time to get a crisper lock.
    """
    samples_per_bit = fs / bit_rate
    window_frames = int(round(samples_per_bit * 8))
    if len(signal) < window_frames * 2:
        return None

    def _build_ref(invert: bool) -> np.ndarray:
        # Build the reference at sample resolution so its length is exactly
        # window_frames, even when samples_per_bit is non-integer (e.g. a
        # webcam at 17 fps -> 3.4 samples/bit). The old bit-repeat approach
        # could yield a shorter array and break np.dot against the window.
        bit_idx = (np.arange(window_frames) / samples_per_bit).astype(int)
        ref = np.where(bit_idx % 2 == 0, 1.0, -1.0)
        if invert:
            ref = -ref
        ref -= ref.mean()
        ref /= np.linalg.norm(ref) + 1e-12
        return ref

    refs = [_build_ref(False), _build_ref(True)]

    first_idx = None
    first_corr = -1.0
    for start in range(0, len(signal) - window_frames):
        window = signal[start : start + window_frames].astype(float)
        window = window - window.mean()
        norm = np.linalg.norm(window) + 1e-12
        corr = max(float(np.dot(window, r) / norm) for r in refs)
        if corr >= correlation_threshold:
            first_idx = start
            first_corr = corr
            break

    if first_idx is None:
        return None

    # Refine: search within the next ~1 bit-time for a local peak (crisper start).
    search_end = min(first_idx + int(round(samples_per_bit)), len(signal) - window_frames)
    best_idx = first_idx
    best_corr = first_corr
    for start in range(first_idx, search_end):
        window = signal[start : start + window_frames].astype(float)
        window = window - window.mean()
        norm = np.linalg.norm(window) + 1e-12
        corr = max(float(np.dot(window, r) / norm) for r in refs)
        if corr > best_corr:
            best_corr = corr
            best_idx = start
    return best_idx


def estimate_bit_time_frames(
    preamble_signal: np.ndarray,
    threshold: float,
) -> float:
    """Estimate bit-time (in frames) from threshold crossings in the preamble.

    0x55 with UART framing produces an alternating 0,1,0,1,... pattern at Rb bps.
    Adjacent zero-crossings of the signal occur exactly one bit-time apart
    (the square wave has period 2*Tb but two transitions per period, spaced Tb).
    """
    above = preamble_signal > threshold
    crossings = np.where(np.diff(above.astype(int)) != 0)[0]
    if len(crossings) < 3:
        raise ValueError("not enough crossings to estimate Tb")
    deltas = np.diff(crossings)
    return float(np.median(deltas))


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


from src import frame as _frame  # noqa: E402 — late import avoids circularity concerns


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
