import pytest
import asyncio
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.mark.asyncio
async def test_cleanup_unlinks_old_files(tmp_path):
    from app.utils.cleanup import unlink_old_files

    old_file = tmp_path / "old.wav"
    old_file.write_bytes(b"\x00" * 100)

    import time, os
    old_stat = old_file.stat()
    old_mtime = old_stat.st_mtime - 7201
    os.utime(old_file, (old_stat.st_atime, old_mtime))

    with patch("app.utils.cleanup.get_cleanup_targets", return_value=[tmp_path]):
        result = await unlink_old_files(max_age_seconds=7200)
    assert result["deleted"] >= 1


@pytest.mark.asyncio
async def test_cleanup_skips_new_files(tmp_path):
    from app.utils.cleanup import unlink_old_files

    new_file = tmp_path / "new.wav"
    new_file.write_bytes(b"\x00" * 100)

    with patch("app.utils.cleanup.get_cleanup_targets", return_value=[tmp_path]):
        result = await unlink_old_files(max_age_seconds=3600)
    assert result["deleted"] == 0


@pytest.mark.asyncio
async def test_cleanup_returns_deleted_and_errors():
    from app.utils.cleanup import unlink_old_files
    with patch("app.utils.cleanup.get_cleanup_targets", return_value=[]):
        result = await unlink_old_files()
    assert "deleted" in result
    assert "errors" in result


@pytest.mark.asyncio
async def test_cleanup_loop_runs():
    from app.utils.cleanup import cleanup_loop

    call_count = 0
    async def mock_cleanup(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            raise KeyboardInterrupt

    with patch("app.utils.cleanup.unlink_old_files", mock_cleanup):
        try:
            await cleanup_loop(interval_seconds=0.01)
        except KeyboardInterrupt:
            pass
    assert call_count >= 2


@pytest.mark.asyncio
async def test_run_cleanup_once():
    from app.utils.cleanup import run_cleanup_once
    with patch("app.utils.cleanup.unlink_old_files", return_value={"deleted": 5, "errors": 0}):
        result = await run_cleanup_once()
    assert result["deleted"] == 5