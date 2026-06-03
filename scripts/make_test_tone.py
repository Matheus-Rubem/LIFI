"""Generate a clean test melody as a WAV of pure tones at exact note pitches.

Play `test_tone.wav` from your phone (or the PC) into the microphone, then run
`audio_selftest.py` and compare the detected notes to the expected ones below.
Pure sines = no harmonics, exact pitches, loud — the ideal test signal.

Run:  python scripts/make_test_tone.py
"""
import os
import sys
import wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.note_codec import midi_to_freq  # noqa: E402

RATE = 44100
NOTES = [60, 64, 67, 72]          # C4, E4, G4, C5 — distinct, in the Dó3–Dó5 range
NAMES = {60: "C4", 64: "E4", 67: "G4", 72: "C5"}
TONE_S = 0.9                      # each note held ~0.9 s
GAP_S = 0.4                       # silence between notes so they segment cleanly
AMP = 0.7                         # loud and clear


def main() -> int:
    env = int(RATE * 0.01)
    segs = []
    for m in NOTES:
        n = int(RATE * TONE_S)
        t = np.arange(n) / RATE
        seg = AMP * np.sin(2 * np.pi * midi_to_freq(m) * t)
        ramp = np.linspace(0.0, 1.0, env)     # fade in/out to avoid clicks
        seg[:env] *= ramp
        seg[-env:] *= ramp[::-1]
        segs.append(seg)
        segs.append(np.zeros(int(RATE * GAP_S)))
    pcm = (np.concatenate(segs) * 32767).astype("<i2")

    out = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "test_tone.wav"
    )
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())

    print(f"Gerado: {out}")
    print("Esperado (nesta ordem): "
          + ", ".join(f"{NAMES[m]} (MIDI{m}~{midi_to_freq(m):.0f}Hz)" for m in NOTES))
    print("\nProximos passos:")
    print("  1) Sanity offline (sem mic): python scripts/audio_selftest.py --file test_tone.wav")
    print("  2) Toque test_tone.wav do celular perto do mic e rode: python scripts/audio_selftest.py 8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
