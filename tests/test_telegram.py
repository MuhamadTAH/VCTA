import pytest
import json
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

app_module = __import__("app.main", fromlist=["app"])
app = app_module.app


@pytest.mark.asyncio
async def test_telegram_webhook_no_message_returns_ok():
    from app.api.routes.telegram import TelegramUpdate
    update = TelegramUpdate(update_id=123, message=None)
    assert update.message is None


@pytest.mark.asyncio
async def test_telegram_webhook_empty_message_returns_ok():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/telegram/webhook",
            json={"update_id": 123, "message": {"chat": {"id": "12345"}, "text": ""}}
        )
    assert response.status_code == 200
    assert response.json()["ok"] is True


@pytest.mark.asyncio
async def test_telegram_start_command_creates_session():
    from app.api.routes import telegram as tg_module

    async def mock_stream(*args, **kwargs):
        yield "مرحبا!"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch.object(tg_module, "upsert_telegram_session", new_callable=AsyncMock) as mock_upsert:
            with patch.object(tg_module, "get_store_context", new_callable=AsyncMock) as mock_ctx:
                mock_ctx.return_value = ("{}", "[]")
                with patch.object(tg_module, "generate_streaming_response", mock_stream):
                    with patch.object(tg_module, "send_telegram_message", new_callable=AsyncMock) as mock_send:
                        mock_send.return_value = True
                        response = await client.post(
                            "/api/telegram/webhook",
                            json={
                                "update_id": 456,
                                "message": {
                                    "chat": {"id": "987654321"},
                                    "text": "/start store_42"
                                }
                            }
                        )
    assert response.status_code == 200
    assert response.json()["ok"] is True
    mock_upsert.assert_awaited_once_with("987654321", 42)


@pytest.mark.asyncio
async def test_telegram_webhook_rejects_unknown_command():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("app.api.routes.telegram.send_telegram_message", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            with patch("app.api.routes.telegram.get_telegram_session", new_callable=AsyncMock) as mock_session:
                mock_session.return_value = None
                response = await client.post(
                    "/api/telegram/webhook",
                    json={
                        "update_id": 789,
                        "message": {
                            "chat": {"id": "111222333"},
                            "text": "hello"
                        }
                    }
                )
    assert response.status_code == 200
    assert response.json()["ok"] is True


@pytest.mark.asyncio
async def test_telegram_start_pattern_extracts_store_id():
    import re
    from app.api.routes.telegram import START_PATTERN
    match = START_PATTERN.match("/start store_402")
    assert match is not None
    assert match.group(1) == "402"


@pytest.mark.asyncio
async def test_telegram_start_pattern_rejects_invalid():
    from app.api.routes.telegram import START_PATTERN
    assert START_PATTERN.match("/start store_abc") is None
    assert START_PATTERN.match("/start 42") is None
    assert START_PATTERN.match("/help") is None
    assert START_PATTERN.match("/start") is None


@pytest.mark.asyncio
async def test_telegram_model_accepts_valid_update():
    from app.api.routes.telegram import TelegramUpdate
    update = TelegramUpdate(
        update_id=1,
        message={"chat": {"id": "123"}, "text": "/start store_1"}
    )
    assert update.update_id == 1
    assert update.message["text"] == "/start store_1"


@pytest.mark.asyncio
async def test_send_telegram_message_returns_false_without_token():
    from app.api.routes.telegram import send_telegram_message
    with patch("app.api.routes.telegram.get_settings") as mock_settings:
        mock_settings.return_value.TELEGRAM_BOT_TOKEN = None
        result = await send_telegram_message("12345", "hello")
        assert result is False


@pytest.mark.asyncio
async def test_upsert_telegram_session_inserts():
    from app.api.routes.telegram import upsert_telegram_session
    with patch("app.api.routes.telegram.get_database") as mock_get_db:
        mock_db = AsyncMock()
        mock_db.__aenter__.return_value = mock_db
        mock_db.__aexit__.return_value = None
        mock_get_db.return_value = mock_db

        await upsert_telegram_session("chat_999", 5)

        mock_db.execute.assert_awaited()
        mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_append_telegram_message_loads_and_saves_history():
    from app.api.routes.telegram import append_telegram_message

    with patch("app.api.routes.telegram.get_telegram_session", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {
            "chat_id": "chat_123",
            "store_id": 1,
            "chat_history_json": "[]"
        }

        with patch("app.api.routes.telegram.save_telegram_history", new_callable=AsyncMock) as mock_save:
            await append_telegram_message("chat_123", "hi", "hello back")
            mock_save.assert_awaited_once()


@pytest.mark.asyncio
async def test_append_telegram_message_skips_if_no_session():
    from app.api.routes.telegram import append_telegram_message

    with patch("app.api.routes.telegram.get_telegram_session", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None

        with patch("app.api.routes.telegram.save_telegram_history", new_callable=AsyncMock) as mock_save:
            await append_telegram_message("unknown_chat", "hi", "hello")
            mock_save.assert_not_called()


@pytest.mark.asyncio
async def test_webhook_integration_with_mock_ai():
    from app.api.routes import telegram as tg_module

    async def mock_stream_response(*args, **kwargs):
        yield "مرحبا!"
        yield " كيف يمكنني مساعدتك؟"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch.object(tg_module, "send_telegram_message", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            with patch.object(tg_module, "generate_streaming_response", mock_stream_response):
                with patch.object(tg_module, "get_telegram_session", new_callable=AsyncMock) as mock_session:
                    mock_session.return_value = {
                        "chat_id": "555",
                        "store_id": 1,
                        "chat_history_json": "[]"
                    }
                    with patch.object(tg_module, "append_telegram_message", new_callable=AsyncMock):
                        with patch.object(tg_module, "get_store_context", new_callable=AsyncMock) as mock_ctx:
                            mock_ctx.return_value = ("{}", "[]")
                            response = await client.post(
                                "/api/telegram/webhook",
                                json={
                                    "update_id": 999,
                                    "message": {
                                        "chat": {"id": "555"},
                                        "text": "مرحبا"
                                    }
                                }
                            )
    assert response.status_code == 200
    assert response.json()["ok"] is True
    mock_send.assert_awaited()
