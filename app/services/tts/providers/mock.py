import os
from typing import Optional
from app.services.tts.base import BaseTTSProvider


class MockTTSProvider(BaseTTSProvider):
    async def generate_audio(
        self,
        text: str,
        output_path: str,
        voice_reference: Optional[dict] = None,
    ) -> str:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(b"RIFF" + b"\x00" * 100)
        return output_path