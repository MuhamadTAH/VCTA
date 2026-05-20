import os
from typing import Optional
from app.services.tts.base import BaseTTSProvider


class FishSpeechProvider(BaseTTSProvider):
    async def generate_audio(
        self,
        text: str,
        output_path: str,
        voice_reference: Optional[dict] = None,
    ) -> str:
        from app.services.fish_speech_client import generate_voice_clone

        ref_path = None
        if voice_reference and voice_reference.get("audio_url"):
            ref_path = voice_reference["audio_url"]
            if ref_path.startswith("/"):
                ref_path = "." + ref_path

        if not ref_path:
            raise RuntimeError("FishSpeechProvider requires a voice_reference with audio_url")

        success, result = await generate_voice_clone(
            text=text,
            reference_audio_path=ref_path,
            output_path=output_path,
        )

        if not success:
            raise RuntimeError(f"FishSpeech generation failed: {result}")

        return result if result else output_path