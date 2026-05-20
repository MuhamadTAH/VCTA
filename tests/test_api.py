import pytest
import pytest_asyncio
import asyncio
import sqlite3
import importlib
import os
from pathlib import Path
from httpx import AsyncClient, ASGITransport

app_module = importlib.import_module("app.main")
app = app_module.app


@pytest.mark.asyncio
async def test_health_returns_ok():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_concurrent_health_checks():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tasks = [client.get("/health") for _ in range(10)]
        responses = await asyncio.gather(*tasks)
    for r in responses:
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_404_returns_clean_json():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/nonexistent")
    assert response.status_code == 404
    assert "detail" in response.json()
    assert "Traceback" not in response.text


@pytest.mark.asyncio
async def test_cors_wildcard_origin():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health", headers={"Origin": "http://example.com"})
    assert "access-control-allow-origin" in response.headers
    assert response.headers["access-control-allow-origin"] == "*"


@pytest.mark.asyncio
async def test_server_header_suppressed():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert "server" not in response.headers


@pytest.mark.asyncio
async def test_db_file_created_and_readable():
    from app.core.database import init_db
    Path("data").mkdir(exist_ok=True)
    await init_db()
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.get("/health")
    db_path = Path("data/test_app.db")
    assert db_path.exists(), "Database file not created"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]
    conn.close()
    expected_tables = ["stores", "sessions", "push_subscriptions", "video_jobs"]
    for table in expected_tables:
        assert table in tables, f"Table {table} not found"


@pytest.mark.asyncio
async def test_wal_mode_active():
    from app.core.database import init_db
    Path("data").mkdir(exist_ok=True)
    await init_db()
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.get("/health")
    db_path = Path("data/test_app.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode;")
    mode = cursor.fetchone()[0].upper()
    conn.close()
    assert mode == "WAL", f"Expected WAL mode, got {mode}"


@pytest.mark.asyncio
async def test_no_stack_trace_on_invalid_route():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/invalid/route/path")
    assert "Traceback" not in response.text
    assert "Python" not in response.text
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_startup_logs_no_database_url_value(caplog):
    import logging
    caplog.set_level(logging.INFO)
    importlib.import_module("app.main")
    for record in caplog.records:
        assert "sqlite+aiosqlite" not in record.getMessage()
        assert "sk-test-placeholder" not in record.getMessage()


@pytest.mark.asyncio
async def test_app_exits_when_DATABASE_URL_missing():
    import sys
    original_env = os.environ.copy()
    try:
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("FFMPEG_PATH", None)
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("ANTHROPIC_API_KEY", None)
        from app.core import config
        config._cached_settings = None
        with pytest.raises(SystemExit) as exc_info:
            config.get_settings()
        assert exc_info.value.code is not None
    finally:
        os.environ.clear()
        os.environ.update(original_env)


@pytest.mark.asyncio
async def test_settings_is_cached_singleton():
    from app.core.config import get_settings, _cached_settings
    import app.core.config as config_module
    config_module._cached_settings = None
    settings1 = get_settings()
    settings2 = get_settings()
    assert settings1 is settings2, "Settings is not a singleton"


@pytest.mark.asyncio
async def test_settings_attributes_are_frozen():
    from app.core.config import Settings
    settings = Settings()
    with pytest.raises(Exception):
        settings.NEW_ATTR = "value"


@pytest.mark.asyncio
async def test_get_voices_returns_list():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/voices")
    assert response.status_code == 200
    assert isinstance(response.json(), list)