import pytest
import json
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

app_module = __import__("app.main", fromlist=["app"])
app = app_module.app


@pytest.fixture
def mock_db():
    mock = AsyncMock()
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=None)
    return mock


@pytest.mark.asyncio
async def test_get_store_rules_returns_rules(mock_db):
    from app.api.routes import admin as admin_module

    with patch.object(admin_module, "get_database", return_value=mock_db):
        mock_db.execute.return_value.fetchone.return_value = (
            json.dumps({"greeting": "مرحبا"}),
        )

        result = await admin_module.get_store_rules(store_id=1)
        assert result.store_id == 1
        assert result.context_rules["greeting"] == "مرحبا"


@pytest.mark.asyncio
async def test_get_store_rules_404_when_missing(mock_db):
    from app.api.routes import admin as admin_module

    with patch.object(admin_module, "get_database", return_value=mock_db):
        mock_db.execute.return_value.fetchone.return_value = None

        try:
            await admin_module.get_store_rules(store_id=999)
            assert False, "Should have raised HTTPException"
        except Exception as e:
            assert e.status_code == 404


@pytest.mark.asyncio
async def test_update_store_rules(mock_db):
    from app.api.routes import admin as admin_module

    with patch.object(admin_module, "get_database", return_value=mock_db):
        mock_db.execute.return_value.fetchone.return_value = (1,)

        result = await admin_module.update_store_rules(
            admin_module.StoreRulesUpdate(store_id=1, context_rules={"lang": "kurdi"})
        )
        assert result["context_rules"]["lang"] == "kurdi"
        mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_get_catalog(mock_db):
    from app.api.routes import admin as admin_module

    with patch.object(admin_module, "get_database", return_value=mock_db):
        mock_db.execute.return_value.fetchone.return_value = (
            json.dumps([{"id": "abc", "name": "Pizza", "price": "10"}]),
        )

        result = await admin_module.get_catalog(store_id=1)
        assert result.store_id == 1
        assert len(result.catalog) == 1
        assert result.catalog[0].name == "Pizza"


@pytest.mark.asyncio
async def test_add_catalog_item(mock_db):
    from app.api.routes import admin as admin_module

    with patch.object(admin_module, "get_database", return_value=mock_db):
        mock_db.execute.return_value.fetchone.return_value = ("[]",)

        result = await admin_module.add_catalog_item(
            store_id=1,
            item=admin_module.CatalogItem(name="Burger", price="5.99", description="Yummy")
        )
        assert result["item"]["name"] == "Burger"
        assert result["item"]["id"] is not None


@pytest.mark.asyncio
async def test_delete_catalog_item(mock_db):
    from app.api.routes import admin as admin_module

    with patch.object(admin_module, "get_database", return_value=mock_db):
        mock_db.execute.return_value.fetchone.return_value = (
            json.dumps([
                {"id": "to-delete", "name": "Item1"},
                {"id": "to-keep", "name": "Item2"},
            ]),
        )

        result = await admin_module.delete_catalog_item(store_id=1, item_id="to-delete")
        assert result["deleted"] == "to-delete"


@pytest.mark.asyncio
async def test_delete_catalog_item_404(mock_db):
    from app.api.routes import admin as admin_module

    with patch.object(admin_module, "get_database", return_value=mock_db):
        mock_db.execute.return_value.fetchone.return_value = (
            json.dumps([{"id": "other-item", "name": "Item"}]),
        )

        try:
            await admin_module.delete_catalog_item(store_id=1, item_id="nonexistent")
            assert False, "Should have raised HTTPException"
        except Exception as e:
            assert e.status_code == 404


@pytest.mark.asyncio
async def test_add_catalog_item_without_price(mock_db):
    from app.api.routes import admin as admin_module

    with patch.object(admin_module, "get_database", return_value=mock_db):
        mock_db.execute.return_value.fetchone.return_value = ("[]",)

        result = await admin_module.add_catalog_item(
            store_id=1,
            item=admin_module.CatalogItem(name="Coffee")
        )
        assert result["item"]["name"] == "Coffee"
