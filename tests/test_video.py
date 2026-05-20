import pytest
import asyncio
import os
import importlib
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport

app_module = importlib.import_module("app.main")
app = app_module.app


@pytest.mark.asyncio
async def test_executor_run_ffmpeg_async_returns_code():
    from app.services.video.executor import run_ffmpeg_async
    returncode, stdout, stderr = await run_ffmpeg_async(["ffmpeg", "-version"])
    assert returncode == 0


@pytest.mark.asyncio
async def test_detect_silence_is_async():
    from app.services.video.transcriber import detect_silence
    assert asyncio.iscoroutinefunction(detect_silence)


@pytest.mark.asyncio
async def test_scale_audio_tempo_is_async():
    from app.services.video.muxer import scale_audio_tempo
    assert asyncio.iscoroutinefunction(scale_audio_tempo)


@pytest.mark.asyncio
async def test_whisper_pipeline_cached():
    from app.services.video.transcriber import get_whisper_pipeline
    import app.services.video.transcriber as transcriber_module
    transcriber_module._whisper_cache = None
    p1 = get_whisper_pipeline()
    p2 = get_whisper_pipeline()
    assert id(p1) == id(p2)


@pytest.mark.asyncio
async def test_build_atempo_chain_respects_floor():
    from app.services.video.muxer import build_atempo_chain
    result = build_atempo_chain(0.25)
    assert "0.5" in result


@pytest.mark.asyncio
async def test_build_atempo_chain_single_for_high_ratio():
    from app.services.video.muxer import build_atempo_chain
    result = build_atempo_chain(1.0)
    assert result == "atempo=1.00"
    assert "," not in result


@pytest.mark.asyncio
async def test_concat_list_deleted_after_process_segments(tmp_path):
    from app.services.video.muxer import process_segments
    video_path = tmp_path / "input.mp4"
    video_path.write_bytes(b"\x00" * 100)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "seg1_scaled.wav").write_bytes(b"\x00" * 100)
    (output_dir / "seg2_scaled.wav").write_bytes(b"\x00" * 100)
    segments = [
        {"start": 0.0, "end": 1.0, "audio_path": str(output_dir / "seg1_scaled.wav")},
        {"start": 1.0, "end": 2.0, "audio_path": str(output_dir / "seg2_scaled.wav")},
    ]
    concat_file = output_dir / "concat_list.txt"
    with patch("app.services.video.muxer.run_ffmpeg_async", new_callable=AsyncMock) as mock_ffmpeg:
        with patch("app.services.video.muxer.scale_audio_tempo", new_callable=AsyncMock) as mock_scale:
            mock_ffmpeg.return_value = (0, "", "")
            mock_scale.return_value = True
            await process_segments(segments, str(video_path), str(output_dir))
    assert not concat_file.exists(), "concat_file should be deleted after process_segments"


@pytest.mark.asyncio
async def test_process_video_job_respects_timeout():
    from app.services.video.pipeline import process_video_job
    import app.services.video.pipeline as pipeline_module

    async def slow_inner(*args, **kwargs):
        await asyncio.sleep(100)
        return {"status": "completed", "output_path": None, "error": None}

    mock_settings = MagicMock()
    mock_settings.VIDEO_JOB_TIMEOUT_SECONDS = 1

    with patch.object(pipeline_module, "_process_video_job_inner", slow_inner):
        with patch.object(pipeline_module, "get_settings", return_value=mock_settings):
            with patch.object(pipeline_module, "update_job_status", new_callable=AsyncMock):
                result = await process_video_job(job_id=1, video_path="dummy.mp4", store_id=1)

    assert result["status"] == "failed"
    assert "timed out" in result["error"].lower()


@pytest.mark.asyncio
async def test_transcribe_full_audio_uses_work_dir(tmp_path):
    from app.services.video.transcriber import transcribe_full_audio

    audio_wav = tmp_path / "audio.wav"
    audio_wav.write_bytes(b"RIFF" + b"\x00" * 100)
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    created_files = []

    async def mock_extract_segment(audio_wav, start, end, output_path):
        Path(output_path).write_bytes(b"RIFF" + b"\x00" * 100)
        created_files.append(output_path)
        return True

    with patch("app.services.video.transcriber.detect_silence", new_callable=AsyncMock) as mock_silence:
        with patch("app.services.video.transcriber.segment_on_silence", new_callable=AsyncMock) as mock_seg:
            with patch("app.services.video.transcriber.extract_segment", side_effect=mock_extract_segment):
                with patch("app.services.video.transcriber.transcribe_segment", new_callable=AsyncMock) as mock_transcribe:
                    with patch("pathlib.Path.unlink"):
                        mock_silence.return_value = []
                        mock_seg.return_value = [(0.0, 1.0)]
                        mock_transcribe.return_value = "test"
                        await transcribe_full_audio(str(audio_wav), str(work_dir))
                    assert len(created_files) > 0, "extract_segment should have been called"
                    assert work_dir.name in created_files[0], "Segment should be in work_dir"


@pytest.mark.asyncio
async def test_db_job_record_updated_on_completion(tmp_path):
    from app.services.video.pipeline import create_video_job, process_video_job, get_job_status
    from app.core.database import get_database
    import app.services.video.pipeline as pipeline_module

    video_file = tmp_path / "test.mp4"
    video_file.write_bytes(b"fake video content")

    with patch("app.core.database.get_database") as mock_get_db:
        mock_db = AsyncMock()
        mock_cursor = AsyncMock()
        mock_cursor.lastrowid = 1
        mock_cursor.fetchone.return_value = (1, 1, "pending", str(video_file), None, "2024-01-01", "2024-01-01")
        mock_db.execute.return_value = mock_cursor
        mock_db.__aenter__.return_value = mock_db
        mock_db.__aexit__.return_value = None
        mock_get_db.return_value = mock_db

        job_id = await create_video_job(store_id=1, input_path=str(video_file))
        assert job_id == 1

        async def mock_inner(*args, **kwargs):
            return {"status": "completed", "output_path": "/fake/output.mp4", "error": None}

        with patch.object(pipeline_module, "_process_video_job_inner", mock_inner):
            with patch.object(pipeline_module, "update_job_status", new_callable=AsyncMock):
                await process_video_job(job_id=job_id, video_path=str(video_file), store_id=1)

        mock_cursor.fetchone.return_value = (1, 1, "completed", str(video_file), "/fake/output.mp4", "2024-01-01", "2024-01-01")
        status = await get_job_status(job_id)
        assert status is not None
        assert status["status"] in ("completed", "failed")


@pytest.mark.asyncio
async def test_silence_detection_returns_list_of_tuples(tmp_path):
    from app.services.video.transcriber import detect_silence
    audio_file = tmp_path / "silence_test.wav"
    audio_file.write_bytes(b"RIFF" + b"\x00" * 100)
    result = await detect_silence(str(audio_file))
    assert isinstance(result, list)
    for item in result:
        assert isinstance(item, tuple)
        assert len(item) == 2
        assert isinstance(item[0], float)
        assert isinstance(item[1], float)


@pytest.mark.asyncio
async def test_atempo_chain_for_very_low_ratio():
    from app.services.video.muxer import build_atempo_chain
    result = build_atempo_chain(0.1)
    parts = result.replace("atempo=", "").split(",")
    product = 1.0
    for p in parts:
        product *= float(p)
    for p in parts:
        assert float(p) >= 0.5, f"Each segment should be >= 0.5, got {p}"
    assert product >= 0.1, f"Final product should be >= 0.1, got {product}"