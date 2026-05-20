import os
import asyncio
import shutil
from pathlib import Path
from typing import Optional

from app.core.config import get_settings
from app.services.video import transcriber, translator, synthesizer, muxer


async def _process_video_job_inner(job_id: int, video_path: str, store_id: int) -> dict:
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

        arabic_dir = f"{work_dir}/arabic"
        synthesized_segments = await synthesizer.synthesize_segments(translated_segments, arabic_dir)

        final_output = await muxer.process_segments(
            segments=synthesized_segments,
            video_path=video_path,
            output_dir=work_dir,
            background_stem=no_vocals_path,
        )

        return {"status": "completed", "output_path": final_output, "error": None}

    except Exception as e:
        raise


async def process_video_job(job_id: int, video_path: str, store_id: int) -> dict:
    settings = get_settings()
    timeout = settings.VIDEO_JOB_TIMEOUT_SECONDS

    try:
        result = await asyncio.wait_for(
            _process_video_job_inner(job_id, video_path, store_id),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        result = {"status": "failed", "output_path": None, "error": "Job timed out"}

    await update_job_status(job_id, result["status"], output_path=result.get("output_path"), error_message=result.get("error"))
    return result


async def update_job_status(
    job_id: int,
    status: str,
    output_path: Optional[str] = None,
    error_message: Optional[str] = None
) -> None:
    from app.core.database import get_database

    async with get_database() as db:
        import datetime
        now = datetime.datetime.now().isoformat()

        if output_path:
            await db.execute(
                "UPDATE video_jobs SET status = ?, output_path = ?, updated_at = ? WHERE id = ?",
                (status, output_path, now, job_id)
            )
        elif error_message:
            await db.execute(
                "UPDATE video_jobs SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, job_id)
            )
        else:
            await db.execute(
                "UPDATE video_jobs SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, job_id)
            )
        await db.commit()


async def create_video_job(store_id: int, input_path: str) -> int:
    from app.core.database import get_database

    async with get_database() as db:
        cursor = await db.execute(
            "INSERT INTO video_jobs (store_id, status, input_path) VALUES (?, ?, ?)",
            (store_id, "pending", input_path)
        )
        await db.commit()
        return cursor.lastrowid


async def get_job_status(job_id: int) -> dict:
    from app.core.database import get_database

    async with get_database() as db:
        cursor = await db.execute(
            "SELECT id, store_id, status, input_path, output_path, created_at, updated_at FROM video_jobs WHERE id = ?",
            (job_id,)
        )
        row = await cursor.fetchone()
        if row:
            return {
                "id": row[0],
                "store_id": row[1],
                "status": row[2],
                "input_path": row[3],
                "output_path": row[4],
                "created_at": row[5],
                "updated_at": row[6]
            }
        return None