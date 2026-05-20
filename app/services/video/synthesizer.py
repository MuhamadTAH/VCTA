import os
from typing import List, Optional
from app.services.tts import generate_audio


async def synthesize_arabic_speech(
    text: str,
    output_path: str,
    voice: str = "alloy",
    voice_reference: Optional[dict] = None,
) -> bool:
    try:
        await generate_audio(text, output_path, voice_reference)
        return True
    except Exception:
        return False


async def synthesize_segments(
    segments: List[dict],
    output_dir: str,
    voice_reference: Optional[dict] = None,
) -> List[dict]:
    from pathlib import Path
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    for seg in segments:
        audio_path = os.path.join(output_dir, f"arabic_{seg['start']:.3f}_{seg['end']:.3f}.wav")
        success = await synthesize_arabic_speech(seg["arabic"], audio_path, voice_reference=voice_reference)
        seg["audio_path"] = audio_path if success else None

    return segments