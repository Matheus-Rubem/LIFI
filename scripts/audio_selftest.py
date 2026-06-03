"""Audio-only self-test (no light): mic -> notes -> speaker.

Records a few seconds from the microphone, detects the melody with the
Goertzel bank, prints the detected notes, and plays them back. Use this to
validate mic + pitch detection + synthesis before the full light pipeline.

Run:  python scripts/audio_selftest.py [seconds]
"""
import os
import sys
import time

# Make the project root importable when run as `python scripts/audio_selftest.py`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sounddevice as sd

from src.audio_synth import synthesize
from src.note_codec import midi_to_freq
from src.pitch_detect import SAMPLE_RATE, audio_to_notes


def _describe(notes) -> str:
    parts = []
    for n in notes:
        name = "pausa" if n.pitch == 0 else f"MIDI{n.pitch}~{midi_to_freq(n.pitch):.0f}Hz"
        parts.append(f"{name} {n.steps * 0.05:.2f}s")
    return " | ".join(parts) if parts else "(nenhuma nota)"


def main() -> int:
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 4.0

    print("Prepare-se para cantar/assoviar 2-3 notas distintas e sustentadas.")
    for c in (3, 2, 1):
        print(f"  {c}...")
        time.sleep(1)
    print(f"GRAVANDO {seconds:.0f}s — cante AGORA!")

    audio = sd.rec(int(seconds * SAMPLE_RATE), samplerate=SAMPLE_RATE,
                   channels=1, dtype="float32")
    sd.wait()

    notes = audio_to_notes(audio.flatten(), SAMPLE_RATE)
    print(f"\nDetectado: {_describe(notes)}")

    if not notes:
        print("Nenhuma nota detectada (silencio ou muito baixo). Tente falar mais alto / mais perto do mic.")
        return 1

    print("Tocando de volta...")
    sd.play(synthesize(notes), 44100)
    sd.wait()
    print("Pronto.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
