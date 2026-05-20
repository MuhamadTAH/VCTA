from fastapi import APIRouter
from app.core.database import get_database


router = APIRouter(prefix="/api", tags=["voices"])


@router.get("/voices")
async def get_voices():
    async with get_database() as db:
        cursor = await db.execute("SELECT id, name, language, audio_url FROM voice_library")
        rows = await cursor.fetchall()
        return [
            {"id": row[0], "name": row[1], "language": row[2], "audio_url": row[3]}
            for row in rows
        ]