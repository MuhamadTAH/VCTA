import asyncio
import math
from typing import List
from app.services.video.executor import run_ffmpeg_async


ATEMPO_MIN = 0.5
ATEMPO_MAX = 2.0


def build_atempo_chain(ratio: float) -> str:
    """
    Build an FFmpeg atempo filter chain that respects the 0.5 floor limit.
    If ratio < 0.5, chains multiple atempo filters to achieve the target rate.

    Examples:
        ratio=1.0  -> "atempo=1.0"
        ratio=0.25 -> "atempo=0.5,atempo=0.5"
        ratio=0.37 -> "atempo=0.5,atempo=0.74"
    """
    if ratio < ATEMPO_MIN:
        chain = []
        remaining = ratio
        while remaining < ATEMPO_MIN:
            factor = ATEMPO_MIN
            chain.append(f"atempo={factor}")
            remaining /= factor
        if remaining > 0.5:
            chain.append(f"atempo={remaining:.2f}")
        return ",".join(chain)
    elif ratio > ATEMPO_MAX:
        chain = []
        remaining = ratio
        while remaining > ATEMPO_MAX:
            factor = ATEMPO_MAX
            chain.append(f"atempo={factor}")
            remaining /= factor
        if remaining > 0.5:
            chain.append(f"atempo={remaining:.2f}")
        return ",".join(chain)
    else:
        return f"atempo={ratio:.2f}"


def calculate_atempo_ratio(original_duration: float, new_duration: float) -> float:
    """
    Calculate the atempo ratio needed to stretch/shrink audio.
    ratio > 1 = speed up (shrink duration)
    ratio < 1 = slow down (stretch duration)
    """
    if new_duration <= 0:
        return 1.0
    return original_duration / new_duration


async def scale_audio_tempo(audio_path: str, target_duration: float, output_path: str) -> bool:
    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "csv=p=0", audio_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    try:
        actual_duration = float(stdout.decode().strip())
    except ValueError:
        actual_duration = 1.0

    ratio = calculate_atempo_ratio(actual_duration, target_duration)
    atempo_chain = build_atempo_chain(ratio)

    cmd = [
        "ffmpeg", "-y", "-i", audio_path,
        "-filter:a", atempo_chain,
        "-acodec", "pcm_s16le",
        output_path
    ]
    returncode, _, _ = await run_ffmpeg_async(cmd)
    return returncode == 0


async def merge_audio_video(video_path: str, audio_path: str, output_path: str) -> bool:
    """
    Merge scaled Arabic audio with original video using FFmpeg.
    Replaces original audio track with the translated one.

    Args:
        video_path: Original video file
        audio_path: Scaled Arabic audio
        output_path: Final merged output

    Returns:
        True if successful, False otherwise
    """
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path, "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        output_path
    ]
    returncode, _, stderr = await run_ffmpeg_async(cmd)
    return returncode == 0


async def process_segments(segments: List[dict], video_path: str, output_dir: str, background_stem: str | None = None) -> str:
    """
    Process all segments: scale each Arabic audio to match original timing, then mux with video.

    Args:
        segments: [{"start": float, "end": float, "audio_path": str}, ...]
        video_path: Original video
        output_dir: Directory for intermediate and final output files
        background_stem: Path to no_vocals.wav from Demucs to preserve as background mix

    Returns:
        Path to the final merged video
    """
    from pathlib import Path
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    segment_files = []
    for seg in segments:
        if not seg.get("audio_path"):
            continue

        original_duration = seg["end"] - seg["start"]
        scaled_path = seg["audio_path"].replace(".wav", "_scaled.wav")

        success = await scale_audio_tempo(seg["audio_path"], original_duration, scaled_path)
        if success:
            segment_files.append(scaled_path)
            seg["scaled_path"] = scaled_path

    if not segment_files:
        raise RuntimeError("No segments were successfully scaled")

    temp_concat = f"{output_dir}/concat_list.txt"
    try:
        with open(temp_concat, "w") as f:
            for sf in segment_files:
                f.write(f"file '{sf}'\n")

        concat_audio = f"{output_dir}/arabic_concat.wav"
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", temp_concat,
            "-c:a", "pcm_s16le",
            concat_audio
        ]
        returncode, _, _ = await run_ffmpeg_async(cmd)
        if returncode != 0:
            raise RuntimeError("Failed to concatenate audio segments")
    finally:
        Path(temp_concat).unlink(missing_ok=True)

    if background_stem and Path(background_stem).exists():
        mixed_audio = f"{output_dir}/mixed_arabic_bg.wav"
        cmd = [
            "ffmpeg", "-y",
            "-i", concat_audio,
            "-i", background_stem,
            "-filter_complex", "[0:a]volume=1.3[v];[1:a]volume=0.35[bg];[v][bg]amix=inputs=2:duration=longest:normalize=0",
            "-acodec", "pcm_s16le",
            mixed_audio
        ]
        returncode, _, _ = await run_ffmpeg_async(cmd)
        if returncode != 0:
            raise RuntimeError("Failed to mix Arabic audio with background stem")
        concat_audio = mixed_audio

    final_output = f"{output_dir}/final_output.mp4"
    success = await merge_audio_video(video_path, concat_audio, final_output)
    if not success:
        raise RuntimeError("Failed to merge audio with video")

    return final_output