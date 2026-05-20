import asyncio
import time
import re
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
from app.services.websocket_manager import ws_manager
from app.services.push_service import register_push_subscription, delete_push_subscription, get_push_subscription
from app.services.fcm_gateway import send_fcm_to_subscription
from app.services.whatsapp_gateway import send_whatsapp_message, format_arabic_message
from app.core.database import get_database
from app.services.chatbot_engine import (
    generate_streaming_response,
    load_session_chat_history,
    get_store_context,
    resilient_save_history,
)


router = APIRouter()

E164_PATTERN = re.compile(r"^\+[1-9]\d{1,14}$")
UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

_rate_limit_store: dict[str, tuple[int, float]] = {}

MAX_HISTORY_MESSAGES = 15


def check_rate_limit(session_id: str, max_calls: int = 10, window_seconds: float = 60.0) -> bool:
    now = time.time()
    key = session_id
    if key not in _rate_limit_store or now - _rate_limit_store[key][1] > window_seconds:
        _rate_limit_store[key] = (1, now)
        return True
    count, start = _rate_limit_store[key]
    if count >= max_calls:
        return False
    _rate_limit_store[key] = (count + 1, start)
    return True


def validate_uuid(session_id: str) -> bool:
    return bool(UUID_PATTERN.match(session_id))


@router.websocket("/ws/chat/{store_id}/{session_uuid}")
async def websocket_chat(websocket: WebSocket, store_id: int, session_uuid: str):
    if not validate_uuid(session_uuid):
        await websocket.send_text(json.dumps({"type": "error", "content": "Invalid session ID"}))
        await websocket.close(code=4001)
        return

    await websocket.accept()
    await ws_manager.connect(session_uuid)
    heartbeat_task = None

    try:
        heartbeat_task = asyncio.create_task(
            ws_manager.heartbeat(session_uuid, websocket)
        )

        async with get_database() as db:
            cursor = await db.execute(
                "SELECT id, store_id, chat_history_json FROM sessions WHERE id = ? AND store_id = ?",
                (session_uuid, store_id),
            )
            session_row = await cursor.fetchone()

        if not session_row:
            await websocket.send_text(json.dumps({"type": "error", "content": "Session not found"}))
            await websocket.close(code=4004)
            return

        context_rules, catalog_json = await get_store_context(store_id)

        while True:
            data = await websocket.receive_text()

            try:
                payload = json.loads(data)
                user_message = payload.get("content", "") if isinstance(payload, dict) else data
            except json.JSONDecodeError:
                user_message = data

            if not user_message or not user_message.strip():
                continue

            history = await load_session_chat_history(session_uuid)

            sliced_history = history[-MAX_HISTORY_MESSAGES:]
            messages = sliced_history + [{"role": "user", "content": user_message}]

            await websocket.send_text(json.dumps({"type": "start", "content": ""}))

            full_response = ""
            async for token in generate_streaming_response(
                messages=messages,
                store_id=store_id,
                context_rules=context_rules,
                catalog_json=catalog_json,
            ):
                await websocket.send_text(json.dumps({"type": "token", "content": token}))
                full_response += token

            await websocket.send_text(json.dumps({"type": "end", "content": full_response}))

            try:
                asyncio.create_task(
                    resilient_save_history(session_uuid, user_message, full_response)
                )
            except Exception:
                pass

    except WebSocketDisconnect:
        pass
    finally:
        if heartbeat_task:
            heartbeat_task.cancel()
        await ws_manager.disconnect(session_uuid)


@router.get("/chat/interstitial/{session_uuid}", response_class=HTMLResponse)
async def chat_interstitial(request: Request, session_uuid: str):
    from fastapi.templating import Jinja2Templates
    from pathlib import Path
    from app.core.config import get_settings

    if not validate_uuid(session_uuid):
        return HTMLResponse("Invalid session", status_code=400)

    settings = get_settings()
    templates = Jinja2Templates(directory=Path(__file__).parent.parent.parent.parent / "templates")

    return templates.TemplateResponse(
        "chat_interstitial.html",
        {"request": request, "session_id": session_uuid, "vapid_key": settings.VAPID_PUBLIC_KEY}
    )


@router.post("/push/subscribe")
async def subscribe_push(session_id: str, endpoint: str, token: str):
    if not validate_uuid(session_id):
        return {"success": False, "error": "Invalid session ID"}
    success = await register_push_subscription(session_id, endpoint, token)
    return {"success": success}


@router.post("/push/unsubscribe")
async def unsubscribe_push(session_id: str):
    if not validate_uuid(session_id):
        return {"success": False, "error": "Invalid session ID"}
    success = await delete_push_subscription(session_id)
    return {"success": success}


@router.get("/push/status/{session_id}")
async def push_status(session_id: str):
    if not validate_uuid(session_id):
        return {"subscribed": False, "subscription": None}
    subscription = await get_push_subscription(session_id)
    return {"subscribed": subscription is not None, "subscription": subscription}


@router.post("/notifications/send")
async def send_notification(
    session_id: str,
    title: str,
    body: str,
    phone_number: str = None,
    use_whatsapp_fallback: bool = False
):
    if not validate_uuid(session_id):
        return {"delivered_via": "none", "success": False, "error": "invalid_session_id"}

    if not check_rate_limit(session_id):
        return {"delivered_via": "none", "success": False, "error": "rate_limited"}

    if use_whatsapp_fallback and phone_number:
        if not E164_PATTERN.match(phone_number):
            return {"delivered_via": "none", "success": False, "error": "invalid_phone_format"}

    if ws_manager.is_connected(session_id):
        await ws_manager.send(session_id, body)
        return {"delivered_via": "websocket", "success": True}

    fcm_sent = await send_fcm_to_subscription(session_id, title, body)
    if fcm_sent:
        return {"delivered_via": "fcm", "success": True}

    if use_whatsapp_fallback and phone_number:
        formatted = await format_arabic_message(body)
        whatsapp_sent = await send_whatsapp_message(phone_number, formatted)
        if whatsapp_sent:
            return {"delivered_via": "whatsapp", "success": True}

    return {"delivered_via": "none", "success": False}


@router.get("/ws/status/{session_id}")
async def ws_status(session_id: str):
    if not validate_uuid(session_id):
        return {"session_id": session_id, "connected": False}
    connected = ws_manager.is_connected(session_id)
    return {"session_id": session_id, "connected": connected}