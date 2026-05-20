import pytest
import os
import sys
import shutil
import sqlite3
from pathlib import Path
import importlib

@pytest.fixture(scope="session", autouse=True)
def setup_and_cleanup():
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./data/test_app.db"
    os.environ["FFMPEG_PATH"] = "ffmpeg"
    os.environ["OPENAI_API_KEY"] = "sk-test-placeholder"
    Path("data").mkdir(exist_ok=True)
    yield
    for f in ["data/test_app.db", "data/test_app.db-wal", "data/test_app.db-shm"]:
        p = Path(f)
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass