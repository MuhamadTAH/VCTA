import os
import asyncio
import uuid
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from typing import List, Optional

from app.schemas.video import VideoJobCreate, VideoJobResponse, VideoJobStatus
from app.services.video.pipeline import create_video_job, get_job_status, update_job_status
from app.services.video_worker import process_video_job as worker_process_video_job


router = APIRouter()


@router.post("/jobs", response_model=VideoJobResponse)
async def create_job(
    store_id: int = Form(...),
    file: UploadFile = File(...),
    voice_id: Optional[int] = Form(None),
    background_tasks: BackgroundTasks = None,
) -> VideoJobResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    upload_dir = Path("data/uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(file.filename).suffix or ".mp4"
    safe_filename = f"{uuid.uuid4().hex}{ext}"
    input_path = upload_dir / safe_filename

    with open(input_path, "wb") as f:
        content = await file.read()
        f.write(content)

    job_id = await create_video_job(store_id, str(input_path))

    background_tasks.add_task(
        worker_process_video_job, job_id, str(input_path), store_id, voice_id
    )

    job = await get_job_status(job_id)
    return VideoJobResponse(
        id=job["id"],
        store_id=job["store_id"],
        status=job["status"],
        input_path=job["input_path"],
        output_path=job.get("output_path"),
        created_at=job.get("created_at"),
        updated_at=job.get("updated_at"),
    )


@router.get("/jobs/{job_id}", response_model=VideoJobStatus)
async def get_status(job_id: int) -> VideoJobStatus:
    job = await get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return VideoJobStatus(
        status=job["status"],
        output_path=job.get("output_path"),
    )


@router.get("/jobs/{job_id}/download")
async def download_video(job_id: int) -> FileResponse:
    job = await get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Job not completed")
    
    output_path = job.get("output_path")
    if not output_path or not Path(output_path).exists():
        raise HTTPException(status_code=404, detail="Output file not found")
    
    return FileResponse(
        path=output_path,
        filename=Path(output_path).name,
        media_type="video/mp4"
    )


@router.get("/jobs", response_model=List[VideoJobResponse])
async def list_jobs(store_id: int | None = None) -> List[VideoJobResponse]:
    from app.core.database import get_database
    
    async with get_database() as db:
        if store_id:
            cursor = await db.execute(
                "SELECT id, store_id, status, input_path, output_path, created_at, updated_at FROM video_jobs WHERE store_id = ? ORDER BY created_at DESC",
                (store_id,)
            )
        else:
            cursor = await db.execute(
                "SELECT id, store_id, status, input_path, output_path, created_at, updated_at FROM video_jobs ORDER BY created_at DESC LIMIT 50"
            )
        rows = await cursor.fetchall()
        return [
            VideoJobResponse(
                id=row[0],
                store_id=row[1],
                status=row[2],
                input_path=row[3],
                output_path=row[4],
                created_at=row[5],
                updated_at=row[6],
            )
            for row in rows
        ]