import pytest
import os
import urllib.parse
import importlib
from pathlib import Path
from httpx import AsyncClient, ASGITransport

app_module = importlib.import_module("app.main")
app = app_module.app


@pytest.mark.asyncio
async def test_android_ua_returns_js_payload():
    from app.core.database import init_db
    Path("data").mkdir(exist_ok=True)
    await init_db()
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/shop/1",
            headers={"user-agent": "Mozilla/5.0 (Linux; Android 14) Chrome/120.0.0.0"}
        )
    assert response.status_code == 200
    html = response.text
    assert "window.location.href" in html
    assert "intent://" in html


@pytest.mark.asyncio
async def test_ios_ua_returns_template():
    from app.core.database import init_db
    Path("data").mkdir(exist_ok=True)
    await init_db()
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/shop/1",
            headers={"user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Safari/605.1.15"}
        )
    assert response.status_code == 200
    html = response.text
    assert "کلیک" in html


@pytest.mark.asyncio
async def test_breakout_param_bypasses_android():
    from app.core.database import init_db
    Path("data").mkdir(exist_ok=True)
    await init_db()
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/shop/1?breakout=true",
            headers={"user-agent": "Mozilla/5.0 (Linux; Android 14) Chrome/120.0.0.0"}
        )
    assert response.status_code == 200
    html = response.text
    assert "کلیک" in html
    assert "intent://" not in html


@pytest.mark.asyncio
async def test_other_ua_returns_template():
    from app.core.database import init_db
    Path("data").mkdir(exist_ok=True)
    await init_db()
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/shop/1",
            headers={"user-agent": "Mozilla/5.0 (Windows NT 10.0) Firefox/120"}
        )
    assert response.status_code == 200
    html = response.text
    assert "کلیک" in html


@pytest.mark.asyncio
async def test_breakout_param_bypasses_android():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/shop/1?breakout=true",
            headers={"user-agent": "Mozilla/5.0 (Linux; Android 14) Chrome/120.0.0.0"}
        )
    assert response.status_code == 200
    html = response.text
    assert "کلیک" in html
    assert "intent://" not in html


@pytest.mark.asyncio
async def test_other_ua_returns_template():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/shop/1",
            headers={"user-agent": "Mozilla/5.0 (Windows NT 10.0) Firefox/120"}
        )
    assert response.status_code == 200
    html = response.text
    assert "کلیک" in html


@pytest.mark.asyncio
async def test_android_payload_contains_fallback_button():
    from app.api.routes.landing import build_android_payload
    html = build_android_payload("https://example.com/store/1", breakout=False)
    assert "Open in Chrome" in html


@pytest.mark.asyncio
async def test_android_payload_no_xss_injection():
    from app.api.routes.landing import build_android_payload
    html = build_android_payload("https://example.com/store/1", breakout=False)
    assert "javascript:" not in html
    assert "intent://" in html
    encoded_url = urllib.parse.quote("https://example.com/store/1", safe="")
    assert encoded_url in html


@pytest.mark.asyncio
async def test_store_url_https_validation():
    from app.api.routes.landing import validate_store_url
    with pytest.raises(ValueError) as exc_info:
        validate_store_url("http://example.com")
    assert "https" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_detect_device_android():
    from app.api.routes.landing import detect_device
    result = detect_device("Mozilla/5.0 (Linux; Android 14)")
    assert result == "android"


@pytest.mark.asyncio
async def test_detect_device_ios():
    from app.api.routes.landing import detect_device
    result = detect_device("Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X)")
    assert result == "ios"


@pytest.mark.asyncio
async def test_detect_device_other():
    from app.api.routes.landing import detect_device
    result = detect_device("Mozilla/5.0 (Windows NT 10.0)")
    assert result == "other"


@pytest.mark.asyncio
async def test_templates_path_is_absolute():
    from app.api.routes.landing import templates
    env = templates.env
    template_path = env.loader.searchpath[0] if env.loader.searchpath else None
    assert template_path is not None, "Template search path should be configured"
    template_path_obj = Path(template_path)
    assert template_path_obj.is_absolute(), f"Template search path should be absolute, got: {template_path}"


@pytest.mark.asyncio
async def test_shop_template_contains_kurdish():
    from app.core.database import init_db
    Path("data").mkdir(exist_ok=True)
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/shop/1",
            headers={"user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"}
        )
    html = response.text
    assert "چالاکردنی پسپۆڕی ڕاگەیاندن" in html or "کلیک" in html