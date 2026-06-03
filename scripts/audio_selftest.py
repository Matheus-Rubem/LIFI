"""Audio-only self-test (no light): mic/WAV -> notes -> speaker.

Detects a melody with the Goertzel bank, prints the detected notes, and (for
mic mode) plays them back. Use it to validate pitch detection + synthesis
before the full light pipeline.

Run:
  python scripts/audio_selftest.py [seconds]      # record from the microphone
  python scripts/audio_selftest.py --file x.wav   # decode a WAV offline (no mic)
"""
import argparse
import os
import sys
import time

# Make the project root importable when run as `python scripts/audio_selftest.py`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.audio_io import read_wav  # noqa: E402
from src.audio_synth import synthesize  # noqa: E402
from src.note_codec import midi_to_freq  # noqa: E402
from src.pitch_detect import SAMPLE_RATE, audio_to_notes  # noqa: E402


def _describe(notes) -> str:
    parts = []
    for n in notes:
        name = "pausa" if n.pitch == 0 else f"MIDI{n.pitch}~{midi_to_freq(n.pitch):.0f}Hz"
        parts.append(f"{name} {n.steps * 0.05:.2f}s")
    return " | ".join(parts) if parts else "(nenhuma nota)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("seconds", nargs="?", type=float, default=4.0,
                    help="Mic recording length (ignored with --file).")
    ap.add_argument("--file", help="Decode this WAV offline instead of recording.")
    args = ap.parse_args()

    if args.file:
        audio = read_wav(args.file, SAMPLE_RATE)
        notes = audio_to_notes(audio, SAMPLE_RATE)
        print(f"Detectado (de {args.file}): {_describe(notes)}")
        return 0 if notes else 1

    import sounddevice as sd
    print("Prepare-se para cantar/assoviar 2-3 notas distintas e sustentadas.")
    for c in (3, 2, 1):
        print(f"  {c}...")
        time.sleep(1)
    print(f"GRAVANDO {args.seconds:.0f}s — toque/cante AGORA!")
    audio = sd.rec(int(args.seconds * SAMPLE_RATE), samplerate=SAMPLE_RATE,
                   channels=1, dtype="float32")
    sd.wait()

    notes = audio_to_notes(audio.flatten(), SAMPLE_RATE)
    print(f"\nDetectado: {_describe(notes)}")
    if not notes:
        print("Nenhuma nota detectada. Toque/cante mais alto e mais perto do mic.")
        return 1
    print("Tocando de volta...")
    sd.play(synthesize(notes), 44100)
    sd.wait()
    print("Pronto.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
