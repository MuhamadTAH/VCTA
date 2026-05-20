import re
import urllib.parse
from pathlib import Path
from typing import Literal
from fastapi import Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.core.config import get_settings


templates = Jinja2Templates(directory=Path(__file__).parent.parent.parent / "templates")

ANDROID_PATTERN = re.compile(r"Android", re.IGNORECASE)
IOS_PATTERN = re.compile(r"iPhone|iPad|iPod", re.IGNORECASE)


def detect_device(user_agent: str) -> Literal["android", "ios", "other"]:
    if ANDROID_PATTERN.search(user_agent):
        return "android"
    if IOS_PATTERN.search(user_agent):
        return "ios"
    return "other"


async def get_store_url(store_id: int) -> str:
    settings = get_settings()
    base = settings.STORE_URL_BASE.rstrip("/")
    return f"{base}/store/{store_id}"


def validate_store_url(store_url: str) -> None:
    if not store_url.startswith("https://"):
        raise ValueError("store_url must use https scheme")


async def ensure_store_exists(store_id: int) -> None:
    from app.core.database import get_database
    async with get_database() as db:
        cursor = await db.execute("SELECT id FROM stores WHERE id = ?", (store_id,))
        row = await cursor.fetchone()
        if not row:
            await db.execute(
                "INSERT OR IGNORE INTO stores (id, business_name) VALUES (?, ?)",
                (store_id, f"Store {store_id}"),
            )
            await db.commit()


def build_android_payload(store_url: str, breakout: bool) -> str:
    validate_store_url(store_url)
    safe_store_url = urllib.parse.quote(store_url, safe="")
    intent_url = f"intent://{safe_store_url}?breakout={str(breakout).lower()}#Intent;scheme=https;package=com.android.chrome;end"
    fallback_url = f"{store_url}?breakout={str(breakout).lower()}"
    escaped_fallback = fallback_url.replace('"', "&quot;")
    escaped_intent = intent_url.replace('"', "&quot;")
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;margin:0;padding:40px 20px;background:#f5f5f5;display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;text-align:center}}
a{{display:inline-block;margin-top:24px;padding:14px 28px;background:#1976d2;color:#fff;text-decoration:none;border-radius:8px;font-size:16px;font-weight:600}}
a:hover{{background:#1565c0}}
</style>
</head>
<body>
<script>
window.location.href = "{escaped_intent}";
</script>
<p>جاري فتح المتجر...</p>
<a href="{escaped_fallback}">Open in Chrome</a>
</body>
</html>"""


async def landing_view(request: Request, store_id: int) -> Response:
    breakout = request.query_params.get("breakout", "").lower() == "true"
    user_agent = request.headers.get("user-agent", "")
    device = detect_device(user_agent) if not breakout else "other"

    store_url = await get_store_url(store_id)

    from app.core.database import get_database
    import uuid
    await ensure_store_exists(store_id)
    session_id = None
    async with get_database() as db:
        cursor = await db.execute(
            "SELECT id FROM sessions WHERE store_id = ? LIMIT 1",
            (store_id,),
        )
        row = await cursor.fetchone()
        if row:
            session_id = row[0]
        else:
            session_uuid = str(uuid.uuid4())
            anon = str(uuid.uuid4())
            await db.execute(
                "INSERT INTO sessions (id, store_id, anonymous_user_id) VALUES (?, ?, ?)",
                (session_uuid, store_id, anon),
            )
            await db.commit()
            session_id = session_uuid

    if breakout or device != "android":
        settings = get_settings()
        return templates.TemplateResponse(
            "shop.html",
            {
                "request": request,
                "store_id": store_id,
                "store_url": store_url,
                "session_id": session_id,
                "telegram_bot_username": settings.TELEGRAM_BOT_USERNAME or "",
            }
        )

    return HTMLResponse(content=build_android_payload(store_url, breakout))