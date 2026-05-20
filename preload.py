import sys
import wave
import struct
import tempfile
import os
from pathlib import Path


def create_silent_wav(path: str, duration_sec: float = 0.5, sample_rate: int = 16000):
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        num_frames = int(sample_rate * duration_sec)
        wf.writeframes(struct.pack("<h", 0) * num_frames)


def preload_htdemucs():
    try:
        import demucs.separate
    except ImportError:
        print("[preload] demucs not installed. Install with: pip install demucs")
        print("[preload] Skipping model preload.")
        return "[preload] skipped — demucs not installed"

    print("[preload] Triggering htdemucs model download via demucs engine...")

    tmpdir = tempfile.mkdtemp()
    silent_wav = os.path.join(tmpdir, "silent.wav")
    create_silent_wav(silent_wav, duration_sec=0.5)

    args = [
        "--two-stems", "vocals",
        "-n", "htdemucs",
        "--segment", "7",
        "-d", "cpu",
        "-o", tmpdir,
        silent_wav,
    ]

    try:
        demucs.separate.main(args)
        print("[preload] Demucs separation dry-run completed.")
    except SystemExit:
        print("[preload] Demucs exited (models may already be cached).")
    except Exception as e:
        print(f"[preload] Warning: {e}")

    cache_paths = [
        Path.home() / ".cache" / "torch" / "hub" / "checkpoints",
        Path.home() / ".cache" / "torchaudio" / "demucs",
    ]
    model_cached = any(p.exists() and any(p.iterdir()) for p in cache_paths)

    if model_cached:
        print(f"[preload] SUCCESS — htdemucs model weights are cached.")
        print("[preload] Model preload confirmed.")
    else:
        print(f"[preload] WARNING — cache directory not found.")
        print("[preload] Model may still be downloading or cache path differs.")

    try:
        os.remove(silent_wav)
        os.rmdir(tmpdir)
    except OSError:
        pass

    return "[preload] done"


if __name__ == "__main__":
    result = preload_htdemucs()
    print(result)
    sys.exit(0)
