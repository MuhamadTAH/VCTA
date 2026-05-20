import pytest
import asyncio
import importlib
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport

app_module = importlib.import_module("app.main")
app = app_module.app

TEST_SESSION_UUID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
TEST_STORE_ID = 1


@pytest.mark.asyncio
async def test_ws_manager_connect_creates_queue():
    from app.services.websocket_manager import WebSocketManager
    manager = WebSocketManager()
    queue = await manager.connect("s1")
    assert "s1" in manager.active_connections
    assert manager.active_connections["s1"] is queue


@pytest.mark.asyncio
async def test_ws_manager_disconnect_removes_queue():
    from app.services.websocket_manager import WebSocketManager
    manager = WebSocketManager()
    await manager.connect("s1")
    await manager.disconnect("s1")
    assert "s1" not in manager.active_connections


@pytest.mark.asyncio
async def test_ws_manager_queue_has_maxsize():
    from app.services.websocket_manager import WebSocketManager
    manager = WebSocketManager(max_queue_size=100)
    assert manager.max_queue_size == 100
    queue = await manager.connect("s1")
    assert queue.maxsize == 100


@pytest.mark.asyncio
async def test_ws_manager_send_returns_true_when_connected():
    from app.services.websocket_manager import WebSocketManager
    manager = WebSocketManager()
    await manager.connect("s1")
    result = await manager.send("s1", "test message")
    assert result is True
    msg = await manager.active_connections["s1"].get()
    assert msg == "test message"


@pytest.mark.asyncio
async def test_ws_manager_send_returns_false_when_disconnected():
    from app.services.websocket_manager import WebSocketManager
    manager = WebSocketManager()
    result = await manager.send("unknown", "test message")
    assert result is False


@pytest.mark.asyncio
async def test_heartbeat_sends_empty_ping():
    from app.services.websocket_manager import WebSocketManager
    manager = WebSocketManager()
    mock_ws = AsyncMock()
    await manager.connect("s1")
    task = asyncio.create_task(manager.heartbeat("s1", mock_ws, interval=0.1))
    await asyncio.sleep(0.3)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    mock_ws.send_text.assert_awaited()


@pytest.mark.asyncio
async def test_validate_store_url_rejects_http():
    from app.api.routes.landing import validate_store_url
    with pytest.raises(ValueError) as exc_info:
        validate_store_url("http://x.com")
    assert "https" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_whatsapp_e164_validation_accepts_valid():
    from app.services.whatsapp_gateway import E164_PATTERN
    assert E164_PATTERN.match("+9647701234567") is not None
    assert E164_PATTERN.match("+12025551234") is not None


@pytest.mark.asyncio
async def test_whatsapp_e164_validation_rejects_invalid():
    from app.services.whatsapp_gateway import E164_PATTERN
    assert E164_PATTERN.match("abc123") is None
    assert E164_PATTERN.match("+00") is None
    assert E164_PATTERN.match("1234567890") is None


@pytest.mark.asyncio
async def test_get_message_timeout_is_5_seconds():
    from app.services.websocket_manager import WebSocketManager
    manager = WebSocketManager()
    import inspect
    sig = inspect.signature(manager.get_message)
    timeout_default = sig.parameters["timeout"].default
    assert timeout_default == 5.0, f"Expected timeout=5.0, got {timeout_default}"


@pytest.mark.asyncio
async def test_chat_interstitial_template_has_vapid_placeholder():
    template_content = Path("app/templates/chat_interstitial.html").read_text()
    assert "{{ vapid_key }}" in template_content or "applicationServerKey" in template_content


@pytest.mark.asyncio
async def test_push_subscription_stored_in_db():
    from app.services.push_service import register_push_subscription, get_push_subscription
    from app.core.database import get_database

    with patch("app.core.database.get_database") as mock_get_db:
        mock_db = AsyncMock()
        mock_db.__aenter__.return_value = mock_db
        mock_db.__aexit__.return_value = None
        mock_get_db.return_value = mock_db

        await register_push_subscription(
            session_id=TEST_SESSION_UUID,
            endpoint="https://push.example.com/sub",
            token="test_token_abc123"
        )

        mock_db.execute.assert_awaited()
        mock_db.commit.assert_awaited()

        mock_db.execute.return_value = AsyncMock()
        mock_db.execute.return_value.fetchone.return_value = ("https://push.example.com/sub", "test_token_abc123")

        subscription = await get_push_subscription(TEST_SESSION_UUID)
        assert subscription is not None
        assert subscription["endpoint"] == "https://push.example.com/sub"
        assert subscription["token"] == "test_token_abc123"


@pytest.mark.asyncio
async def test_validate_uuid_accepts_valid_uuid():
    from app.api.routes.chat import validate_uuid
    assert validate_uuid("a1b2c3d4-e5f6-7890-abcd-ef1234567890") is True
    assert validate_uuid("A1B2C3D4-E5F6-7890-ABCD-EF1234567890") is True
    assert validate_uuid("550e8400-e29b-41d4-a716-446655440000") is True


@pytest.mark.asyncio
async def test_validate_uuid_rejects_invalid():
    from app.api.routes.chat import validate_uuid
    assert validate_uuid("not-a-uuid") is False
    assert validate_uuid("12345") is False
    assert validate_uuid("") is False
    assert validate_uuid("a1b2c3d4-e5f6-7890-abcd") is False
    assert validate_uuid("a1b2c3d4e5f67890abcd ef1234567890") is False