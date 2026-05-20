import json
import re
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from app.core.config import get_settings
from app.core.database import get_database
from app.services.chatbot_engine import (
    generate_streaming_response,
    load_session_chat_history,
    get_store_context,
    MAX_HISTORY_MESSAGES,
)


router = APIRouter(prefix="/api/telegram", tags=["telegram"])

START_PATTERN = re.compile(r"^/start store_(\d+)$")


class TelegramUpdate(BaseModel):
    update_id: int
    message: dict | None = None


async def send_telegram_message(chat_id: str, text: str) -> bool:
    settings = get_settings()
    if not settings.TELEGRAM_BOT_TOKEN:
        return False

    import httpx
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=10.0)
            return response.status_code == 200
    except Exception:
        return False


async def get_telegram_session(chat_id: str) -> dict | None:
    async with get_database() as db:
        cursor = await db.execute(
            "SELECT chat_id, store_id, chat_history_json FROM telegram_sessions WHERE chat_id = ?",
            (chat_id,),
        )
        row = await cursor.fetchone()
        if row:
            return {"chat_id": row[0], "store_id": row[1], "chat_history_json": row[2]}
        return None


async def upsert_telegram_session(chat_id: str, store_id: int) -> None:
    async with get_database() as db:
        await db.execute(
            """
            INSERT INTO telegram_sessions (chat_id, store_id) VALUES (?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET store_id = excluded.store_id, updated_at = CURRENT_TIMESTAMP
            """,
            (chat_id, store_id),
        )
        await db.commit()


async def save_telegram_history(chat_id: str, history: list[dict]) -> None:
    truncated = history[-MAX_HISTORY_MESSAGES:]
    async with get_database() as db:
        await db.execute(
            "UPDATE telegram_sessions SET chat_history_json = ?, updated_at = CURRENT_TIMESTAMP WHERE chat_id = ?",
            (json.dumps(truncated), chat_id),
        )
        await db.commit()


async def append_telegram_message(chat_id: str, user_message: str, assistant_message: str) -> None:
    session = await get_telegram_session(chat_id)
    if not session:
        return

    try:
        history = json.loads(session["chat_history_json"]) if session["chat_history_json"] else []
    except (json.JSONDecodeError, TypeError):
        history = []

    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": assistant_message})

    await save_telegram_history(chat_id, history)


@router.post("/webhook")
async def telegram_webhook(update: TelegramUpdate, request: Request):
    if not update.message:
        return {"ok": True}

    chat_id = str(update.message.get("chat", {}).get("id", ""))
    text = update.message.get("text", "").strip()

    if not chat_id or not text:
        return {"ok": True}

    start_match = START_PATTERN.match(text)

    if start_match:
        store_id = int(start_match.group(1))
        await upsert_telegram_session(chat_id, store_id)

        context_rules, catalog_json = await get_store_context(store_id)
        messages = [
            {"role": "user", "content": text},
        ]
        greeting = (
            "👋 مرحباً! أنا المساعد الذكي لهذه المتجر.\n\n"
            "كيف يمكنني مساعدتك اليوم؟"
        )
        async for token in generate_streaming_response(
            messages=messages,
            store_id=store_id,
            context_rules=context_rules,
            catalog_json=catalog_json,
        ):
            greeting += token

        await send_telegram_message(chat_id, greeting.strip())
        return {"ok": True}

    session = await get_telegram_session(chat_id)
    if not session:
        await send_telegram_message(
            chat_id,
            "مرحباً! يرجى بدء محادثة جديدة باستخدام /start store_<id>"
        )
        return {"ok": True}

    store_id = session["store_id"]
    context_rules, catalog_json = await get_store_context(store_id)

    history = []
    if session["chat_history_json"]:
        try:
            history = json.loads(session["chat_history_json"])
        except (json.JSONDecodeError, TypeError):
            history = []

    sliced = history[-MAX_HISTORY_MESSAGES:]
    messages = sliced + [{"role": "user", "content": text}]

    full_response = ""
    async for token in generate_streaming_response(
        messages=messages,
        store_id=store_id,
        context_rules=context_rules,
        catalog_json=catalog_json,
    ):
        full_response += token

    await send_telegram_message(chat_id, full_response)
    await append_telegram_message(chat_id, text, full_response)

    return {"ok": True}