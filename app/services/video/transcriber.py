import asyncio
from pathlib import Path
from typing import List, Tuple
from app.services.video.executor import run_ffmpeg_async


_whisper_cache = None


def get_whisper_pipeline():
    global _whisper_cache
    if _whisper_cache is None:
        from transformers import pipeline
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        _whisper_cache = pipeline(
            "automatic-speech-recognition",
            model="openai/whisper-small",
            device=device,
        )
    return _whisper_cache


async def extract_audio(video_path: str, output_wav: str, sample_rate: int = 16000) -> tuple[bool, str]:
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le",
        "-ar", str(sample_rate), "-ac", "1",
        output_wav
    ]
    returncode, _, stderr = await run_ffmpeg_async(cmd)
    return (returncode == 0, output_wav)


async def demucs_separate(audio_wav: str, output_dir: str) -> tuple[str, str]:
    import demucs.separate
    from pathlib import Path

    demucs_args = [
        "--two-stems", "vocals",
        "-n", "htdemucs",
        "--segment", "7",
        "-d", "cpu",
        "-o", output_dir,
        audio_wav,
    ]

    await asyncio.to_thread(demucs.separate.main, demucs_args)

    stem_dir = Path(output_dir) / "htdemucs"
    track_name = Path(audio_wav).stem

    vocals_path = str(stem_dir / track_name / "vocals.wav")
    no_vocals_path = str(stem_dir / track_name / "no_vocals.wav")

    return vocals_path, no_vocals_path


async def detect_silence(audio_path: str, silence_threshold: int = -40, min_silence_len: int = 500) -> List[Tuple[float, float]]:
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-i", audio_path,
        "-af", f"silencedetect=noise={silence_threshold}dB:d={min_silence_len/1000}",
        "-f", "null", "-",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    stderr_text = stderr.decode()

    silence_ranges = []
    start = None
    for line in stderr_text.split("\n"):
        if "silencedetect" in line:
            if "silence_start" in line:
                parts = line.split("silence_start: ")[1].split(" ")
                start = float(parts[0])
            elif "silence_end" in line and start is not None:
                parts = line.split("silence_end: ")[1].split(" ")
                end = float(parts[0])
                if start > 0:
                    silence_ranges.append((start, end))
    return silence_ranges


async def segment_on_silence(audio_wav: str, silence_ranges: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    all_segments = []
    for i, (sil_start, sil_end) in enumerate(silence_ranges):
        if i == 0 and sil_start > 0:
            all_segments.append((0.0, sil_start))
        if i > 0:
            prev_end = silence_ranges[i-1][1]
            all_segments.append((prev_end, sil_start))
    return all_segments


async def extract_segment(audio_wav: str, start: float, end: float, output_path: str) -> bool:
    duration = end - start
    cmd = [
        "ffmpeg", "-y", "-i", audio_wav,
        "-ss", str(start), "-t", str(duration),
        "-acodec", "pcm_s16le", output_path
    ]
    returncode, _, _ = await run_ffmpeg_async(cmd)
    return returncode == 0


async def transcribe_segment(segment_wav: str) -> str:
    transcriber = get_whisper_pipeline()
    result = transcriber(segment_wav, return_timestamps=False)
    return result["text"].strip()


async def transcribe_full_audio(audio_wav: str, work_dir: str) -> List[dict]:
    silence_ranges = await detect_silence(audio_wav)
    segments = await segment_on_silence(audio_wav, silence_ranges)

    results = []
    for start, end in segments:
        segment_path = f"{work_dir}/segment_{start:.3f}_{end:.3f}.wav"
        success = await extract_segment(audio_wav, start, end, segment_path)
        if not success:
            continue

        text = await transcribe_segment(segment_path)
        if text:
            results.append({"start": start, "end": end, "text": text})

        Path(segment_path).unlink(missing_ok=True)

    return results