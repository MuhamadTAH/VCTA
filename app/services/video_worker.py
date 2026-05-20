import asyncio
import logging
import shutil
from pathlib import Path

from app.core.config import get_settings
from app.services.video import transcriber, translator, synthesizer, muxer


logger = logging.getLogger(__name__)


async def get_voice_reference(voice_id: int) -> dict | None:
    from app.core.database import get_database
    async with get_database() as db:
        cursor = await db.execute(
            "SELECT id, name, language, audio_url FROM voice_library WHERE id = ?",
            (voice_id,)
        )
        row = await cursor.fetchone()
        if row:
            return {"id": row[0], "name": row[1], "language": row[2], "audio_url": row[3]}
        return None


async def _process_video_job_inner(job_id: int, video_path: str, store_id: int, voice_id: int | None) -> dict:
    work_dir = f"data/jobs/{job_id}"
    Path(work_dir).mkdir(parents=True, exist_ok=True)

    try:
        audio_wav = f"{work_dir}/audio.wav"
        extract_success, _ = await transcriber.extract_audio(video_path, audio_wav)
        if not extract_success:
            raise RuntimeError("Failed to extract audio from video")

        vocals_path, no_vocals_path = await transcriber.demucs_separate(audio_wav, work_dir)

        segments = await transcriber.transcribe_full_audio(vocals_path, work_dir)
        if not segments:
            raise RuntimeError("No speech segments detected in audio")

        translated_segments = await translator.translate_segments(segments)

        voice_ref = None
        if voice_id:
            voice_ref = await get_voice_reference(voice_id)

        arabic_dir = f"{work_dir}/arabic"
        synthesized_segments = await synthesizer.synthesize_segments(
            translated_segments, arabic_dir, voice_reference=voice_ref
        )

        final_output = await muxer.process_segments(
            segments=synthesized_segments,
            video_path=video_path,
            output_dir=work_dir,
            background_stem=no_vocals_path,
        )

        output_dir = Path("static/outputs")
        output_dir.mkdir(parents=True, exist_ok=True)
        final_name = f"job_{job_id}_output.mp4"
        result_path = str(output_dir / final_name)
        shutil.copy(final_output, result_path)

        return {"status": "completed", "output_path": result_path, "error": None}

    except Exception as e:
        logger.exception(f"Video job {job_id} failed: {e}")
        raise


async def process_video_job(job_id: int, video_path: str, store_id: int, voice_id: int | None = None) -> dict:
    from app.services.video.pipeline import update_job_status

    settings = get_settings()
    timeout = settings.VIDEO_JOB_TIMEOUT_SECONDS

    try:
        await update_job_status(job_id, "processing")

        result = await asyncio.wait_for(
            _process_video_job_inner(job_id, video_path, store_id, voice_id),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        result = {"status": "failed", "output_path": None, "error": "Job timed out"}
    except Exception:
        result = {"status": "failed", "output_path": None, "error": "Processing error"}

    await update_job_status(job_id, result["status"], output_path=result.get("output_path"), error_message=result.get("error"))
    return result