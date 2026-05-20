import os
from typing import List, Optional
from app.core.config import get_settings


async def synthesize_arabic_speech(
    text: str,
    output_path: str,
    voice: str = "alloy",
    voice_reference: Optional[dict] = None,
) -> bool:
    settings = get_settings()

    if voice_reference and voice_reference.get("audio_url"):
        try:
            from app.services.fish_speech_client import generate_voice_clone
            import tempfile
            ref_path = voice_reference["audio_url"]
            if ref_path.startswith("/"):
                ref_path = "." + ref_path
            temp_ref = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            temp_ref.close()
            import shutil
            shutil.copy(ref_path, temp_ref.name)
            success, _ = await generate_voice_clone(
                text=text,
                reference_audio_path=temp_ref.name,
                output_path=output_path,
            )
            os.unlink(temp_ref.name, ignore_errors=True)
            if success:
                return True
        except Exception:
            pass

    if settings.MINIMAX_API_KEY:
        from app.services import tts
        mp3_path = output_path.replace(".wav", ".mp3")
        success, _ = await tts.synthesize_speech(text, mp3_path)
        if not success:
            return False
        from app.services.video.executor import run_ffmpeg_async
        cmd = [
            "ffmpeg", "-y", "-i", mp3_path,
            "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            output_path
        ]
        returncode, _, _ = await run_ffmpeg_async(cmd)
        return returncode == 0

    if not settings.OPENAI_API_KEY:
        raise RuntimeError("No TTS API key configured (MINIMAX_API_KEY or OPENAI_API_KEY)")

    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    mp3_path = output_path.replace(".wav", ".mp3")

    response = await client.audio.speech.create(
        model="gpt-4o-mini",
        input=text,
        voice=voice,
        response_format="mp3"
    )

    with open(mp3_path, "wb") as f:
        f.write(response.read())

    from app.services.video.executor import run_ffmpeg_async
    cmd = [
        "ffmpeg", "-y", "-i", mp3_path,
        "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        output_path
    ]
    returncode, _, _ = await run_ffmpeg_async(cmd)
    return returncode == 0


async def synthesize_segments(
    segments: List[dict],
    output_dir: str,
    voice_reference: Optional[dict] = None,
) -> List[dict]:
    """
    Synthesize Arabic TTS for each translated segment.
    Each segment gets its own audio file named by start/end timestamp.

    Args:
        segments: [{"start": float, "end": float, "text": str, "arabic": str}, ...]
        output_dir: Directory to store generated audio files
        voice_reference: Optional dict with voice metadata for zero-shot cloning

    Returns:
        Same segments dict with added "audio_path" field per segment
    """
    from pathlib import Path
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    for seg in segments:
        audio_path = os.path.join(output_dir, f"arabic_{seg['start']:.3f}_{seg['end']:.3f}.wav")
        success = await synthesize_arabic_speech(seg["arabic"], audio_path, voice_reference=voice_reference)
        seg["audio_path"] = audio_path if success else None

    return segments