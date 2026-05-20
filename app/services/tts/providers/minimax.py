import os
import httpx
from typing import Optional
from app.services.tts.base import BaseTTSProvider


MINIMAX_TTS_URL = "https://api.minimax.io/v1/t2a_v2"
MODEL = "speech-2.8-hd"


class MiniMaxProvider(BaseTTSProvider):
    async def generate_audio(
        self,
        text: str,
        output_path: str,
        voice_reference: Optional[dict] = None,
    ) -> str:
        from app.core.config import get_settings
        settings = get_settings()

        if not settings.MINIMAX_API_KEY:
            raise RuntimeError("MINIMAX_API_KEY not configured")

        headers = {
            "Authorization": f"Bearer {settings.MINIMAX_API_KEY}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": MODEL,
            "text": text,
            "stream": False,
            "voice_setting": {
                "voice_id": "male-qn-qingse",
            },
            "audio_setting": {
                "format": "mp3",
                "sample_rate": 32000,
                "bitrate": 128000,
                "channel": 1,
            },
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                MINIMAX_TTS_URL,
                headers=headers,
                json=payload,
            )

            if response.status_code != 200:
                raise RuntimeError(f"MiniMax API error: {response.status_code} {response.text}")

            data = response.json()
            audio_hex = data.get("data", {}).get("audio")
            if not audio_hex:
                raise RuntimeError("No audio data in MiniMax response")

            audio_bytes = bytes.fromhex(audio_hex)

            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(audio_bytes)

            return output_path