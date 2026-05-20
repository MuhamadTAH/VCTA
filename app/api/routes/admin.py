import json
from typing import Any
from fastapi import APIRouter, HTTPException, Query
from pathlib import Path
from pydantic import BaseModel, ConfigDict
from app.core.database import get_database


router = APIRouter(prefix="/store", tags=["admin"])


class StoreRulesResponse(BaseModel):
    store_id: int
    context_rules: str | dict[str, Any]


class StoreRulesUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    store_id: int | None = None
    context_rules: str | dict[str, Any] = {}
    telegram_bot_token: str | None = None


class CatalogItem(BaseModel):
    id: str | None = None
    name: str
    price: str | None = None
    description: str | None = None


class CatalogResponse(BaseModel):
    store_id: int
    catalog: list[CatalogItem]


@router.get("/rules", response_model=StoreRulesResponse)
async def get_store_rules(store_id: int):
    async with get_database() as db:
        cursor = await db.execute("SELECT id FROM stores WHERE id = ?", (store_id,))
        if not cursor.fetchone():
            await db.execute("INSERT INTO stores (id, business_name) VALUES (?, ?)", (store_id, f"Store {store_id}"))
            await db.commit()
        cursor = await db.execute("SELECT context_rules FROM stores WHERE id = ?", (store_id,))
        row = await cursor.fetchone()
        try:
            rules = json.loads(row[0]) if row[0] else {}
        except (json.JSONDecodeError, TypeError):
            rules = row[0] if row[0] else {}
        return StoreRulesResponse(store_id=store_id, context_rules=rules)


@router.put("/rules")
async def update_store_rules(
    store_id: int | None = Query(None),
    payload: StoreRulesUpdate = None,
):
    if payload is None:
        payload = StoreRulesUpdate()

    resolved_store_id = store_id or payload.store_id or 1

    async with get_database() as db:
        cursor = await db.execute("SELECT id FROM stores WHERE id = ?", (resolved_store_id,))
        if not cursor.fetchone():
            await db.execute("INSERT INTO stores (id, business_name) VALUES (?, ?)", (resolved_store_id, f"Store {resolved_store_id}"))
            await db.commit()
        rules_value = payload.context_rules if isinstance(payload.context_rules, str) else json.dumps(payload.context_rules)
        await db.execute(
            "UPDATE stores SET context_rules = ? WHERE id = ?",
            (rules_value, resolved_store_id),
        )
        await db.commit()

    if payload.telegram_bot_token:
        async with get_database() as db:
            cursor = await db.execute("SELECT id FROM stores WHERE id = ?", (resolved_store_id,))
            if not cursor.fetchone():
                await db.execute("INSERT INTO stores (id, business_name) VALUES (?, ?)", (resolved_store_id, f"Store {resolved_store_id}"))
                await db.commit()
            await db.execute(
                """INSERT INTO bot_settings (store_id, telegram_bot_token) VALUES (?, ?)
                   ON CONFLICT(store_id) DO UPDATE SET telegram_bot_token = excluded.telegram_bot_token, updated_at = CURRENT_TIMESTAMP""",
                (resolved_store_id, payload.telegram_bot_token),
            )
            await db.commit()

    return {"store_id": resolved_store_id, "context_rules": payload.context_rules}


@router.get("/catalog", response_model=CatalogResponse)
async def get_catalog(store_id: int):
    async with get_database() as db:
        cursor = await db.execute(
            "SELECT catalog_json FROM stores WHERE id = ?",
            (store_id,),
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Store not found")
        try:
            catalog = json.loads(row[0]) if row[0] else []
        except (json.JSONDecodeError, TypeError):
            catalog = []
        return CatalogResponse(store_id=store_id, catalog=catalog)


@router.post("/catalog")
async def add_catalog_item(store_id: int, item: CatalogItem):
    async with get_database() as db:
        cursor = await db.execute(
            "SELECT catalog_json FROM stores WHERE id = ?",
            (store_id,),
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Store not found")
        try:
            catalog = json.loads(row[0]) if row[0] else []
        except (json.JSONDecodeError, TypeError):
            catalog = []

        import uuid
        new_item = item.model_dump(exclude_none=True)
        if new_item.get("id") is None:
            new_item["id"] = str(uuid.uuid4())
        catalog.append(new_item)

        await db.execute(
            "UPDATE stores SET catalog_json = ? WHERE id = ?",
            (json.dumps(catalog), store_id),
        )
        await db.commit()
        return {"store_id": store_id, "item": new_item}


@router.delete("/catalog/{item_id}")
async def delete_catalog_item(store_id: int, item_id: str):
    async with get_database() as db:
        cursor = await db.execute(
            "SELECT catalog_json FROM stores WHERE id = ?",
            (store_id,),
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Store not found")
        try:
            catalog = json.loads(row[0]) if row[0] else []
        except (json.JSONDecodeError, TypeError):
            catalog = []

        original_len = len(catalog)
        catalog = [c for c in catalog if c.get("id") != item_id]

        if len(catalog) == original_len:
            raise HTTPException(status_code=404, detail="Catalog item not found")

        await db.execute(
            "UPDATE stores SET catalog_json = ? WHERE id = ?",
            (json.dumps(catalog), store_id),
        )
        await db.commit()
        return {"store_id": store_id, "deleted": item_id}
