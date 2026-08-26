"""
Shared Asynchronous Utilities.
Provides centralized Windows Proactor event loop configuration and safe subprocess execution.
"""

import asyncio
import sys
from typing import Tuple, Optional


def configure_asyncio_policy() -> None:
    """
    Call this before asyncio.run() in CLI entry points only.
    Do NOT call on module import — it interferes with tests and embedding.
    """
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


async def run_subprocess_async(
    *args: str,
    stdin_data: Optional[bytes] = None,
    timeout: float = 4.0
) -> Tuple[int, bytes, bytes]:
    """
    Runs a subprocess asynchronously. Kills and reaps the child on timeout or error.
    Returns (returncode, stdout_bytes, stderr_bytes).
    Raises asyncio.TimeoutError only after the child process is guaranteed dead.
    """
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.PIPE if stdin_data is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=stdin_data), timeout=timeout
        )
        return proc.returncode if proc.returncode is not None else 0, stdout, stderr
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        await proc.wait()  # Reap process to prevent zombie/resource leak
        raise
    except Exception:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        await proc.wait()
        raise
