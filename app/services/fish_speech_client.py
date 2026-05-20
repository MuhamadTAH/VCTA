import httpx
import asyncio
import io
from pathlib import Path


FISH_API_URL = "http://127.0.0.1:8080/v2/tts/voice-clone"


async def generate_voice_clone(
    text: str,
    reference_audio_path: str,
    output_path: str,
) -> tuple[bool, str | None]:
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            with open(reference_audio_path, "rb") as f:
                reference_bytes = f.read()

            files = {
                "reference_audio": (Path(reference_audio_path).name, io.BytesIO(reference_bytes), "audio/wav"),
            }
            data = {"text": text}

            response = await client.post(FISH_API_URL, files=files, data=data)

            if response.status_code != 200:
                return False, None

            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(response.content)

            return True, output_path

    except Exception:
        return False, None