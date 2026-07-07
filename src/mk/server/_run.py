"""Shared async command runner for all server managers."""

import asyncio
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


async def run_cmd(
    cmd: str,
    sudo: bool = True,
    timeout: int = 120,
    stdin_data: Optional[str] = None,
) -> Tuple[int, str, str]:
    """Execute a shell command asynchronously.

    Args:
        cmd: Command to execute.
        sudo: Prefix with sudo (unless cmd already starts with sudo).
        timeout: Timeout in seconds.
        stdin_data: Data to pass via stdin pipe.

    Returns:
        Tuple of (return_code, stdout, stderr).
    """
    if sudo and not cmd.startswith("sudo"):
        full_cmd = f"sudo {cmd}"
    else:
        full_cmd = cmd

    logger.debug(f"exec: {full_cmd}")

    proc = await asyncio.create_subprocess_shell(
        full_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.PIPE if stdin_data else None,
    )

    try:
        stdin_bytes = stdin_data.encode() if stdin_data else None
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=stdin_bytes), timeout=timeout
        )
    except asyncio.TimeoutError:
        proc.kill()
        return 1, "", f"Command timed out after {timeout}s"

    rc = proc.returncode or 0
    out = stdout.decode().strip()
    err = stderr.decode().strip()

    if rc != 0:
        logger.debug(f"Command failed ({rc}): {full_cmd}: {err[:200]}")

    return rc, out, err
