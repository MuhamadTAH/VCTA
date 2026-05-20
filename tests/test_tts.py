import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.mark.asyncio
async def test_synthesize_speech_returns_false_without_key():
    from app.services import tts
    with patch("app.services.tts.get_settings") as mock_settings:
        mock_settings.return_value.MINIMAX_API_KEY = None
        success, path = await tts.synthesize_speech("مرحبا", None)
    assert success is False
    assert path is None


@pytest.mark.asyncio
async def test_synthesize_speech_with_mock_response(tmp_path):
    from app.services import tts
    out_file = tmp_path / "output.mp3"

    with patch("app.services.tts.get_settings") as mock_settings:
        mock_settings.return_value.MINIMAX_API_KEY = "fake-key"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "audio/mpeg"}
        mock_response.content = b"\x00\x01\x02\x03"

        with patch("app.services.tts.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value = mock_client

            success, path = await tts.synthesize_speech("مرحبا", str(out_file))

    assert success is True
    assert path == str(out_file)
    assert out_file.read_bytes() == b"\x00\x01\x02\x03"


@pytest.mark.asyncio
async def test_synthesize_to_wav_falls_back_to_ffmpeg(tmp_path):
    from app.services import tts
    mp3_out = tmp_path / "test.mp3"
    wav_out = tmp_path / "test.wav"
    mp3_out.write_bytes(b"\x00\x01\x02")

    with patch("app.services.tts.synthesize_speech", new_callable=AsyncMock) as mock_synth:
        mock_synth.return_value = (True, str(mp3_out))

        with patch("app.services.tts.asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_proc:
            mock_proc.return_value.wait = AsyncMock(return_value=0)
            mock_proc.return_value.communicate = AsyncMock(return_value=(b"", b""))
            mock_proc.return_value.returncode = 0

            result = await tts.synthesize_to_wav("text", str(wav_out))
    assert result is True


@pytest.mark.asyncio
async def test_synthesize_speech_none_output_returns_bytes():
    from app.services import tts
    with patch("app.services.tts.get_settings") as mock_settings:
        mock_settings.return_value.MINIMAX_API_KEY = "fake-key"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "audio/mpeg"}
        mock_response.content = b"\x00\x01\x02"

        with patch("app.services.tts.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value = mock_client

            success, path = await tts.synthesize_speech("مرحبا", None)

    assert success is True
    assert path is None


@pytest.mark.asyncio
async def test_synthesize_speech_handles_http_error():
    from app.services import tts
    with patch("app.services.tts.get_settings") as mock_settings:
        mock_settings.return_value.MINIMAX_API_KEY = "fake-key"

        with patch("app.services.tts.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.side_effect = Exception("Network error")
            mock_client_cls.return_value = mock_client

            success, path = await tts.synthesize_speech("text", None)

    assert success is False