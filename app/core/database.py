import aiosqlite
from contextlib import asynccontextmanager
from pathlib import Path
from app.core.config import get_db_path


async def init_db() -> None:
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path, timeout=30) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA busy_timeout=5000;")
        await db.execute("PRAGMA foreign_keys=ON;")
        existing = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        existing_tables = {row[0] for row in await existing.fetchall()}
        create_stores = "stores" not in existing_tables
        create_sessions = "sessions" not in existing_tables
        create_push_subscriptions = "push_subscriptions" not in existing_tables
        create_video_jobs = "video_jobs" not in existing_tables
        create_telegram_sessions = "telegram_sessions" not in existing_tables
        create_voice_library = "voice_library" not in existing_tables
        create_bot_settings = None

        if create_stores:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS stores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    business_name TEXT NOT NULL,
                    location TEXT,
                    context_rules TEXT DEFAULT '{}',
                    catalog_json TEXT DEFAULT '[]',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        if create_sessions:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    store_id INTEGER NOT NULL,
                    anonymous_user_id TEXT NOT NULL,
                    chat_history_json TEXT DEFAULT '[]',
                    language_pref TEXT DEFAULT 'sorani',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (store_id) REFERENCES stores(id)
                )
            """)
        if create_push_subscriptions:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS push_subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    token TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
            """)
        if create_video_jobs:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS video_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    store_id INTEGER NOT NULL,
                    status TEXT DEFAULT 'pending',
                    input_path TEXT NOT NULL,
                    output_path TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (store_id) REFERENCES stores(id)
                )
            """)
        if create_telegram_sessions:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS telegram_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL UNIQUE,
                    store_id INTEGER NOT NULL,
                    chat_history_json TEXT DEFAULT '[]',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (store_id) REFERENCES stores(id)
                )
            """)
        if create_voice_library:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS voice_library (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    language TEXT NOT NULL,
                    audio_url TEXT NOT NULL
                )
            """)
        if create_bot_settings is None:
            try:
                await db.execute("SELECT id FROM bot_settings LIMIT 1")
                create_bot_settings = False
            except:
                create_bot_settings = True
        if create_bot_settings:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS bot_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    store_id INTEGER NOT NULL UNIQUE,
                    telegram_bot_token TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (store_id) REFERENCES stores(id)
                )
            """)
        await db.commit()


@asynccontextmanager
async def get_database():
    db = await aiosqlite.connect(get_db_path(), timeout=30)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL;")
    await db.execute("PRAGMA busy_timeout=5000;")
    await db.execute("PRAGMA foreign_keys=ON;")
    try:
        yield db
    finally:
        await db.close()