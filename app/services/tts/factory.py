import os
from typing import Optional
from app.services.tts.base import BaseTTSProvider
from app.services.tts.providers.minimax import MiniMaxProvider
from app.services.tts.providers.fish_speech import FishSpeechProvider
from app.services.tts.providers.mock import MockTTSProvider


def get_tts_provider() -> BaseTTSProvider:
    engine = os.environ.get("ACTIVE_TTS_ENGINE", "minimax").lower()
    if engine == "fish":
        return FishSpeechProvider()
    elif engine == "mock":
        return MockTTSProvider()
    return MiniMaxProvider()


async def generate_audio(
    text: str,
    output_path: str,
    voice_reference: Optional[dict] = None,
) -> str:
    provider = get_tts_provider()
    return await provider.generate_audio(text, output_path, voice_reference)