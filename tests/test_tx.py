"""Test tx.py file mode (file-mode is scriptable without hardware)."""
from __future__ import annotations

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
