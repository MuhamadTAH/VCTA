import pytest
import pytest_asyncio
import aiosqlite
import asyncio
import sys
from pathlib import Path
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, str(Path(__file__).parent.parent))

app_module = __import__("app.main", fromlist=["app"])
app = app_module.app


async def setup_test_db():
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await db.execute("""
        CREATE TABLE stores (
            id INTEGER PRIMARY KEY,
            business_name TEXT,
            context_rules TEXT,
            catalog_json TEXT
        )
    """)
    await db.execute("""
        CREATE TABLE sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_uuid TEXT UNIQUE,
            store_id INTEGER,
            phone_number TEXT,
            created_at TEXT
        )
    """)
    await db.execute("""
        CREATE TABLE push_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_uuid TEXT,
            endpoint TEXT,
            p256dh TEXT,
            auth TEXT,
            created_at TEXT
        )
    """)
    await db.execute("""
        CREATE TABLE video_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT UNIQUE,
            store_id INTEGER,
            status TEXT,
            result TEXT,
            error TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    await db.execute("""
        CREATE TABLE bot_settings (
            store_id INTEGER PRIMARY KEY,
            telegram_bot_token TEXT,
            updated_at TEXT
        )
    """)
    await db.commit()
    return db


@pytest_asyncio.fixture
async def real_db():
    db = await setup_test_db()
    yield db
    await db.close()


@pytest.mark.asyncio
async def test_get_store_rules_auto_creates_store(real_db):
    from app.api.routes import admin as admin_module

    with pytest.MonkeyPatch.context() as mp:
        def patched_get_db():
            class DummyCtx:
                async def __aenter__(self):
                    return real_db
                async def __aexit__(self, *args):
                    pass
            return DummyCtx()

        mp.setattr(admin_module, "get_database", patched_get_db)

        result = await admin_module.get_store_rules(store_id=1)
        assert result.store_id == 1
        assert result.context_rules == {}

        rows = await real_db.execute("SELECT * FROM stores WHERE id = 1")
        row = await rows.fetchone()
        assert row is not None


@pytest.mark.asyncio
async def test_get_store_rules_returns_existing_rules(real_db):
    from app.api.routes import admin as admin_module

    await real_db.execute(
        "INSERT INTO stores (id, business_name, context_rules) VALUES (?, ?, ?)",
        (2, "Test Store", '{"greeting": "مرحبا"}'),
    )
    await real_db.commit()

    with pytest.MonkeyPatch.context() as mp:
        def patched_get_db():
            class DummyCtx:
                async def __aenter__(self):
                    return real_db
                async def __aexit__(self, *args):
                    pass
            return DummyCtx()

        mp.setattr(admin_module, "get_database", patched_get_db)

        result = await admin_module.get_store_rules(store_id=2)
        assert result.store_id == 2
        assert result.context_rules["greeting"] == "مرحبا"


@pytest.mark.asyncio
async def test_update_store_rules_inserts_and_updates(real_db):
    from app.api.routes import admin as admin_module

    await real_db.execute(
        "INSERT INTO stores (id, business_name) VALUES (?, ?)",
        (3, "Store Three"),
    )
    await real_db.commit()

    with pytest.MonkeyPatch.context() as mp:
        def patched_get_db():
            class DummyCtx:
                async def __aenter__(self):
                    return real_db
                async def __aexit__(self, *args):
                    pass
            return DummyCtx()

        mp.setattr(admin_module, "get_database", patched_get_db)

        result = await admin_module.update_store_rules(
            store_id=3,
            payload=admin_module.StoreRulesUpdate(store_id=3, context_rules={"lang": "kurdi"})
        )
        assert result["context_rules"]["lang"] == "kurdi"

        rows = await real_db.execute("SELECT context_rules FROM stores WHERE id = 3")
        row = await rows.fetchone()
        import json
        saved = json.loads(row[0])
        assert saved["lang"] == "kurdi"


@pytest.mark.asyncio
async def test_update_store_rules_with_telegram_token(real_db):
    from app.api.routes import admin as admin_module

    await real_db.execute(
        "INSERT INTO stores (id, business_name) VALUES (?, ?)",
        (4, "Store Four"),
    )
    await real_db.commit()

    with pytest.MonkeyPatch.context() as mp:
        def patched_get_db():
            class DummyCtx:
                async def __aenter__(self):
                    return real_db
                async def __aexit__(self, *args):
                    pass
            return DummyCtx()

        mp.setattr(admin_module, "get_database", patched_get_db)

        result = await admin_module.update_store_rules(
            store_id=4,
            payload=admin_module.StoreRulesUpdate(store_id=4, telegram_bot_token="12345:TOKEN")
        )
        assert result["store_id"] == 4

        rows = await real_db.execute("SELECT telegram_bot_token FROM bot_settings WHERE store_id = 4")
        row = await rows.fetchone()
        assert row["telegram_bot_token"] == "12345:TOKEN"


@pytest.mark.asyncio
async def test_get_catalog_returns_items(real_db):
    from app.api.routes import admin as admin_module

    await real_db.execute(
        "INSERT INTO stores (id, business_name, catalog_json) VALUES (?, ?, ?)",
        (5, "Store Five", '[{"id": "abc", "name": "Pizza", "price": "10"}]'),
    )
    await real_db.commit()

    with pytest.MonkeyPatch.context() as mp:
        def patched_get_db():
            class DummyCtx:
                async def __aenter__(self):
                    return real_db
                async def __aexit__(self, *args):
                    pass
            return DummyCtx()

        mp.setattr(admin_module, "get_database", patched_get_db)

        result = await admin_module.get_catalog(store_id=5)
        assert result.store_id == 5
        assert len(result.catalog) == 1
        assert result.catalog[0].name == "Pizza"


@pytest.mark.asyncio
async def test_add_catalog_item(real_db):
    from app.api.routes import admin as admin_module

    await real_db.execute(
        "INSERT INTO stores (id, business_name, catalog_json) VALUES (?, ?, ?)",
        (6, "Store Six", "[]"),
    )
    await real_db.commit()

    with pytest.MonkeyPatch.context() as mp:
        def patched_get_db():
            class DummyCtx:
                async def __aenter__(self):
                    return real_db
                async def __aexit__(self, *args):
                    pass
            return DummyCtx()

        mp.setattr(admin_module, "get_database", patched_get_db)

        result = await admin_module.add_catalog_item(
            store_id=6,
            item=admin_module.CatalogItem(name="Burger", price="5.99", description="Yummy")
        )
        assert result["item"]["name"] == "Burger"
        assert result["item"]["id"] is not None

        rows = await real_db.execute("SELECT catalog_json FROM stores WHERE id = 6")
        row = await rows.fetchone()
        import json
        saved = json.loads(row[0])
        assert saved[0]["name"] == "Burger"


@pytest.mark.asyncio
async def test_delete_catalog_item(real_db):
    from app.api.routes import admin as admin_module

    await real_db.execute(
        "INSERT INTO stores (id, business_name, catalog_json) VALUES (?, ?, ?)",
        (7, "Store Seven", '[{"id": "to-delete", "name": "Item1"}, {"id": "to-keep", "name": "Item2"}]'),
    )
    await real_db.commit()

    with pytest.MonkeyPatch.context() as mp:
        def patched_get_db():
            class DummyCtx:
                async def __aenter__(self):
                    return real_db
                async def __aexit__(self, *args):
                    pass
            return DummyCtx()

        mp.setattr(admin_module, "get_database", patched_get_db)

        result = await admin_module.delete_catalog_item(store_id=7, item_id="to-delete")
        assert result["deleted"] == "to-delete"

        rows = await real_db.execute("SELECT catalog_json FROM stores WHERE id = 7")
        row = await rows.fetchone()
        import json
        saved = json.loads(row[0])
        assert len(saved) == 1
        assert saved[0]["id"] == "to-keep"


@pytest.mark.asyncio
async def test_delete_catalog_item_404(real_db):
    from app.api.routes import admin as admin_module

    await real_db.execute(
        "INSERT INTO stores (id, business_name, catalog_json) VALUES (?, ?, ?)",
        (8, "Store Eight", '[{"id": "other-item", "name": "Item"}]'),
    )
    await real_db.commit()

    with pytest.MonkeyPatch.context() as mp:
        def patched_get_db():
            class DummyCtx:
                async def __aenter__(self):
                    return real_db
                async def __aexit__(self, *args):
                    pass
            return DummyCtx()

        mp.setattr(admin_module, "get_database", patched_get_db)

        with pytest.raises(Exception) as exc_info:
            await admin_module.delete_catalog_item(store_id=8, item_id="nonexistent")
        assert exc_info.value.status_code == 404