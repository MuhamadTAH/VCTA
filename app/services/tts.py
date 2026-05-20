import io
import json
import httpx
import asyncio
import base64
from app.core.config import get_settings


MINIMAX_TTS_URL = "https://api.minimax.io/v1/t2a_v2"
MODEL = "speech-2.8-hd"


async def synthesize_speech(text: str, output_path: str | None = None) -> tuple[bool, str | None]:
    settings = get_settings()
    if not settings.MINIMAX_API_KEY:
        return False, None

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

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                MINIMAX_TTS_URL,
                headers=headers,
                json=payload,
            )

            if response.status_code != 200:
                return False, None

            data = response.json()

            audio_hex = data.get("data", {}).get("audio")
            if not audio_hex:
                return False, None

            audio_bytes = bytes.fromhex(audio_hex)

            if output_path:
                with open(output_path, "wb") as f:
                    f.write(audio_bytes)
                return True, output_path

            return True, None

    except Exception:
        return False, None


async def synthesize_to_wav(text: str, output_wav: str) -> bool:
    import tempfile
    import subprocess
    import asyncio

    success, mp3_path = await synthesize_speech(text)
    if not success or not mp3_path:
        return False

    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-i", mp3_path,
        "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        output_wav,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()
    return proc.returncode == 0