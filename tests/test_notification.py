import pytest
import asyncio
import time
import importlib
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport

app_module = importlib.import_module("app.main")
app = app_module.app

TEST_SESSION_UUID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"


@pytest.mark.asyncio
async def test_rate_limit_allows_within_limit():
    from app.api.routes.chat import check_rate_limit
    for _ in range(5):
        result = check_rate_limit(TEST_SESSION_UUID)
        assert result is True, "Should allow calls within limit"


@pytest.mark.asyncio
async def test_rate_limit_blocks_after_max():
    from app.api.routes.chat import check_rate_limit, _rate_limit_store
    _rate_limit_store.clear()
    for _ in range(10):
        check_rate_limit(TEST_SESSION_UUID, max_calls=10)
    result = check_rate_limit(TEST_SESSION_UUID, max_calls=10)
    assert result is False, "Should block after max calls reached"


@pytest.mark.asyncio
async def test_rate_limit_resets_after_window():
    from app.api.routes.chat import check_rate_limit, _rate_limit_store
    _rate_limit_store.clear()
    assert check_rate_limit(TEST_SESSION_UUID, max_calls=2, window_seconds=0.1) is True
    assert check_rate_limit(TEST_SESSION_UUID, max_calls=2, window_seconds=0.1) is True
    assert check_rate_limit(TEST_SESSION_UUID, max_calls=2, window_seconds=0.1) is False
    await asyncio.sleep(0.2)
    assert check_rate_limit(TEST_SESSION_UUID, max_calls=2, window_seconds=0.1) is True, "Should reset after window expires"


@pytest.mark.asyncio
async def test_phone_e164_validated_before_whatsapp():
    from app.api.routes.chat import send_notification
    with patch("app.api.routes.chat.check_rate_limit", return_value=True):
        with patch("app.api.routes.chat.ws_manager") as mock_ws:
            mock_ws.is_connected.return_value = False
            with patch("app.api.routes.chat.send_fcm_to_subscription", return_value=False) as mock_fcm:
                result = await send_notification(
                    session_id=TEST_SESSION_UUID,
                    title="Test",
                    body="Test body",
                    phone_number="abc123",
                    use_whatsapp_fallback=True
                )
    assert result["error"] == "invalid_phone_format"
    mock_fcm.assert_not_called()


@pytest.mark.asyncio
async def test_whatsapp_not_called_without_fallback_flag():
    from app.api.routes.chat import send_notification
    with patch("app.api.routes.chat.check_rate_limit", return_value=True):
        with patch("app.api.routes.chat.ws_manager") as mock_ws:
            mock_ws.is_connected.return_value = False
            with patch("app.api.routes.chat.send_fcm_to_subscription", return_value=False):
                with patch("app.api.routes.chat.send_whatsapp_message") as mock_whatsapp:
                    result = await send_notification(
                        session_id=TEST_SESSION_UUID,
                        title="Test",
                        body="Test body",
                        phone_number="abc123",
                        use_whatsapp_fallback=False
                    )
    mock_whatsapp.assert_not_called()
    assert result["delivered_via"] == "none"


@pytest.mark.asyncio
async def test_ws_connected_returns_websocket_delivery():
    from app.services.websocket_manager import WebSocketManager
    manager = WebSocketManager()
    assert manager.is_connected("s1") is False
    await manager.connect("s1")
    assert manager.is_connected("s1") is True
    await manager.disconnect("s1")
    assert manager.is_connected("s1") is False


@pytest.mark.asyncio
async def test_ws_fallback_cascade_to_fcm():
    from app.api.routes.chat import send_notification
    with patch("app.api.routes.chat.check_rate_limit", return_value=True):
        with patch("app.api.routes.chat.ws_manager") as mock_ws:
            mock_ws.is_connected.return_value = False
            with patch("app.api.routes.chat.send_fcm_to_subscription", return_value=True) as mock_fcm:
                result = await send_notification(
                    session_id=TEST_SESSION_UUID,
                    title="Test",
                    body="Test body"
                )
    assert result["delivered_via"] == "fcm"
    mock_fcm.assert_called_once()


@pytest.mark.asyncio
async def test_ws_fallback_cascade_to_whatsapp():
    from app.api.routes.chat import send_notification
    with patch("app.api.routes.chat.check_rate_limit", return_value=True):
        with patch("app.api.routes.chat.ws_manager") as mock_ws:
            mock_ws.is_connected.return_value = False
            with patch("app.api.routes.chat.send_fcm_to_subscription", return_value=False) as mock_fcm:
                with patch("app.api.routes.chat.send_whatsapp_message", return_value=True) as mock_whatsapp:
                    result = await send_notification(
                        session_id=TEST_SESSION_UUID,
                        title="Test",
                        body="Test body",
                        phone_number="+9647701234567",
                        use_whatsapp_fallback=True
                    )
    assert result["delivered_via"] == "whatsapp"
    mock_fcm.assert_called_once()
    mock_whatsapp.assert_called_once()


@pytest.mark.asyncio
async def test_rate_limited_returns_error_response():
    from app.api.routes.chat import check_rate_limit, _rate_limit_store
    _rate_limit_store.clear()
    unknown_uuid = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    for _ in range(10):
        check_rate_limit(unknown_uuid, max_calls=10)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/notifications/send",
            params={"session_id": unknown_uuid, "title": "Test", "body": "Test body"}
        )
    assert response.status_code == 200
    data = response.json()
    assert data["error"] == "rate_limited"


@pytest.mark.asyncio
async def test_invalid_phone_returns_error_response():
    from app.api.routes.chat import E164_PATTERN
    assert E164_PATTERN.match("abc123") is None


@pytest.mark.asyncio
async def test_is_connected_false_for_unknown_session():
    from app.services.websocket_manager import ws_manager
    assert ws_manager.is_connected("unknown_session_id") is False