from contextlib import asynccontextmanager
import asyncio
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
from app.core.database import init_db, get_database
from app.api.routes.landing import landing_view
from app.api.routes.chat import router as chat_router
from app.api.routes.video import router as video_router
from app.api.routes.telegram import router as telegram_router
from app.api.routes.admin import router as admin_router
from app.api.routes.voices import router as voices_router
from app.utils.cleanup import cleanup_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await init_db()
    except SystemExit as e:
        logging.critical(f"System dependency check failed: {e}")
        raise
    except Exception as e:
        logging.warning(f"Database init warning: {e}")

    cleanup_task = asyncio.create_task(cleanup_loop(interval_seconds=900))
    logging.info("[startup] Cleanup background task launched")

    try:
        yield
    finally:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
        logging.info("[shutdown] Cleanup task stopped")


app = FastAPI(title="Unified Video Translator & Chat Funnel", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_api_route("/shop/{store_id}", landing_view, methods=["GET"], name="landing")
app.include_router(chat_router)
app.include_router(video_router, prefix="/video", tags=["video"])
app.include_router(telegram_router)
app.include_router(admin_router, prefix="/api", tags=["admin"])
app.include_router(voices_router)

static_dir = Path("static/voices")
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static/voices", StaticFiles(directory=str(static_dir)), name="static_voices")

outputs_dir = Path("static/outputs")
outputs_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static/outputs", StaticFiles(directory=str(outputs_dir)), name="static_outputs")


templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


@app.get("/", response_class=HTMLResponse)
async def upload_page(request: Request):
    return templates.TemplateResponse(request, "upload.html", {"request": request})


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/admin/{store_id}", response_class=HTMLResponse)
async def admin_dashboard(request: Request, store_id: int):
    voices = []
    session_uuid = "debug-session-id"

    try:
        async with get_database() as db:
            cursor = await db.execute("SELECT id, name, language, audio_url FROM voice_library LIMIT 10")
            rows = await cursor.fetchall()
            voices = [{"id": r[0], "name": r[1], "language": r[2], "audio_url": r[3]} for r in rows]

            cursor = await db.execute("SELECT id FROM sessions WHERE store_id = ? LIMIT 1", (store_id,))
            row = await cursor.fetchone()
            if row:
                session_uuid = row[0]
            else:
                import uuid
                session_uuid = str(uuid.uuid4())
                await db.execute(
                    "INSERT INTO sessions (id, store_id, anonymous_user_id) VALUES (?, ?, ?)",
                    (session_uuid, store_id, str(uuid.uuid4())),
                )
                await db.commit()
    except Exception as e:
        print(f"DB error in admin dashboard: {e}")

    return templates.TemplateResponse(request, "admin_dashboard.html", {
        "request": request,
        "store_id": store_id,
        "store_name": "کۆگای " + str(store_id),
        "store_rules": "",
        "catalog_items": [],
        "telegram_bot_username": None,
        "voices": voices,
        "session_uuid": session_uuid,
    })