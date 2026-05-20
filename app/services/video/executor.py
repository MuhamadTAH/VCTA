import asyncio
import shlex
from typing import List


async def run_ffmpeg_cmd(cmd: str, timeout: int = 3600) -> tuple[int, str, str]:
    """
    Execute an FFmpeg command asynchronously using asyncio.create_subprocess_exec.
    Non-blocking — protects the FastAPI event loop from CPU-bound FFmpeg operations.

    Args:
        cmd: Full FFmpeg command string (will be shell-split)
        timeout: Max seconds before process is killed

    Returns:
        (returncode, stdout, stderr)
    """
    args = shlex.split(cmd)
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return proc.returncode, stdout.decode(), stderr.decode()
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return -1, "", "Process timed out"


async def run_ffmpeg_async(args: List[str], timeout: int = 3600) -> tuple[int, str, str]:
    """
    Execute FFmpeg with a list of arguments (cleaner than shell-split).
    Non-blocking via asyncio.create_subprocess_exec.

    Args:
        args: List of FFmpeg arguments, e.g. ["ffmpeg", "-i", "input.wav", "output.mp3"]
        timeout: Max seconds before process is killed

    Returns:
        (returncode, stdout, stderr)
    """
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return proc.returncode, stdout.decode(), stderr.decode()
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return -1, "", "Process timed out"