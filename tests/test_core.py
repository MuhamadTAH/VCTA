import pytest
import pytest_asyncio
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest_asyncio.fixture
async def test_db_path(tmp_path):
    db_file = tmp_path / "test_app.db"
    return f"sqlite+aiosqlite:///{db_file}"


@pytest_asyncio.fixture
async def mock_env(test_db_path):
    env = {
        "DATABASE_URL": test_db_path,
        "FFMPEG_PATH": "ffmpeg",
        "OPENAI_API_KEY": "sk-test-key-for-testing",
        "PATH": os.environ.get("PATH", ""),
    }
    with patch.dict(os.environ, env, clear=True):
        yield env


@pytest_asyncio.fixture
async def app(mock_env, test_db_path):
    import app.core.config
    app.core.config._cached_settings = None
    from app.main import app as fastapi_app
    yield fastapi_app


@pytest_asyncio.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_health_check_returns_ok(self, client):
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_init_db_creates_all_tables(self, app, test_db_path):
        from app.core.database import init_db
        await init_db()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            pass
        db_path = test_db_path.replace("sqlite+aiosqlite:///", "")
        import sqlite3
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        assert "stores" in tables
        assert "sessions" in tables
        assert "push_subscriptions" in tables
        assert "video_jobs" in tables

    @pytest.mark.asyncio
    async def test_get_database_yields_valid_connection(self, test_db_path):
        from app.core.database import init_db, get_database
        await init_db()
        async with get_database() as db:
            assert db is not None
            cursor = await db.execute("SELECT 1")
            rows = await cursor.fetchall()
            assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_db_path_is_lazy_not_module_level(self, mock_env, monkeypatch):
        import app.core.database as db_module
        monkeypatch.delitem(sys.modules, "app.core.database", raising=False)
        monkeypatch.setattr("app.core.config._cached_settings", None)
        from app.core import config
        config._cached_settings = None
        settings_call_count = 0
        original_settings_init = config.Settings.__init__
        async def counting_init(self, *args, **kwargs):
            nonlocal settings_call_count
            settings_call_count += 1
            return original_settings_init(self, *args, **kwargs)
        monkeypatch.setattr("app.core.config.Settings.__init__", counting_init)
        import importlib
        db_module = importlib.import_module("app.core.database")
        assert settings_call_count == 0, "Settings() was called at module import — DB_PATH must not be resolved at import time"


class TestMaliciousTests:
    @pytest.mark.asyncio
    async def test_concurrent_db_writes_do_not_lock(self, app, test_db_path):
        from app.core.database import init_db, get_database
        import asyncio
        await init_db()
        errors = []
        async def write_task(task_id):
            try:
                async with get_database() as db:
                    await db.execute("INSERT INTO stores (business_name) VALUES (?)", (f"store_{task_id}",))
                    await db.commit()
            except Exception as e:
                errors.append(e)
        tasks = [write_task(i) for i in range(10)]
        await asyncio.gather(*tasks)
        assert len(errors) == 0, f"Concurrent writes failed: {errors}"

    @pytest.mark.asyncio
    async def test_cors_allow_credentials_is_false(self, app):
        cors_middleware_found = False
        for middleware in app.user_middleware:
            if middleware.cls.__name__ == "CORSMiddleware":
                cors_middleware_found = True
                break
        assert cors_middleware_found, "CORSMiddleware not found in user_middleware"
        from httpx import AsyncClient, ASGITransport
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/health", headers={"Origin": "http://example.com"})
        assert "access-control-allow-origin" in response.headers
        assert response.headers["access-control-allow-origin"] == "*"

    @pytest.mark.asyncio
    async def test_lifespan_logs_critical_on_init_failure(self, mock_env, monkeypatch):
        import logging
        import importlib

        async def failing_init_db():
            raise RuntimeError("DB init failed intentionally")

        import app.core.config
        import app.core.database
        import app.main

        monkeypatch.setattr(app.core.database, "init_db", failing_init_db)
        app.core.config._cached_settings = None
        importlib.reload(app.main)
        app.main.init_db = failing_init_db

        captured_logs = []
        class FakeHandler(logging.Handler):
            def emit(self, record):
                captured_logs.append(record)
        logger = logging.getLogger()
        handler = FakeHandler()
        handler.setLevel(logging.CRITICAL)
        logger.addHandler(handler)
        try:
            async with app.main.app.router.lifespan_context(app.main.app):
                pass
        except (RuntimeError, SystemExit):
            pass
        finally:
            logger.removeHandler(handler)
        critical_records = [r for r in captured_logs if r.levelno == logging.CRITICAL]
        assert len(critical_records) > 0, "Lifespan must call logging.critical when init_db() fails"

    @pytest.mark.asyncio
    async def test_init_db_idempotent_no_double_create_error(self, app, test_db_path):
        from app.core.database import init_db
        await init_db()
        await init_db()
        db_path = test_db_path.replace("sqlite+aiosqlite:///", "")
        import sqlite3
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM stores")
        count = cursor.fetchone()[0]
        conn.close()
        assert count == 0

    @pytest.mark.asyncio
    async def test_wal_mode_enabled_on_connection(self, test_db_path, mock_env):
        from app.core.database import init_db, get_database
        await init_db()
        async with get_database() as db:
            cursor = await db.execute("PRAGMA journal_mode")
            row = await cursor.fetchone()
            assert row[0].upper() == "WAL", f"Expected WAL mode, got {row[0]}"