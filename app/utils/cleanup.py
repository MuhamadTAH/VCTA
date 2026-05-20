import asyncio
import logging
import time
from datetime import datetime, timezone
from pathlib import Path


logger = logging.getLogger(__name__)

MAX_AGE_SECONDS = 2 * 60 * 60


def get_cleanup_targets() -> list[Path]:
    base = Path("data")
    targets = []
    for sub in ("jobs", "uploads", "temp"):
        p = base / sub
        if p.exists():
            targets.append(p)
    return targets


async def unlink_old_files(max_age_seconds: int = MAX_AGE_SECONDS) -> dict[str, int]:
    now = time.time()
    deleted = 0
    errors = 0

    for target_dir in get_cleanup_targets():
        try:
            for path in target_dir.rglob("*"):
                if not path.is_file():
                    continue
                try:
                    mtime = path.stat().st_mtime
                    if now - mtime > max_age_seconds:
                        path.unlink(missing_ok=True)
                        deleted += 1
                        logger.info(f"[cleanup] Removed: {path}")
                except OSError as e:
                    logger.warning(f"[cleanup] Could not remove {path}: {e}")
                    errors += 1
        except Exception as e:
            logger.error(f"[cleanup] Scan failed for {target_dir}: {e}")
            errors += 1

    return {"deleted": deleted, "errors": errors}


async def cleanup_loop(interval_seconds: int = 900) -> None:
    while True:
        try:
            result = await unlink_old_files()
            logger.info(f"[cleanup] Run complete: {result}")
        except Exception as e:
            logger.error(f"[cleanup] Loop error: {e}")
        await asyncio.sleep(interval_seconds)


async def run_cleanup_once() -> dict[str, int]:
    return await unlink_old_files()