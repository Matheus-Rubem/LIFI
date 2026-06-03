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
