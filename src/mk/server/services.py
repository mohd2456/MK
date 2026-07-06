"""System Services Management.

Provides async functions to manage systemd services including listing,
starting, stopping, restarting, enabling, disabling services, and
checking their status and logs.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional


async def _run_command(
    *args: str, timeout: float = 30.0
) -> Dict[str, Any]:
    """Run a subprocess command and return structured result."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
        return {
            "success": proc.returncode == 0,
            "stdout": stdout.decode("utf-8", errors="replace").strip(),
            "stderr": stderr.decode("utf-8", errors="replace").strip(),
            "returncode": proc.returncode,
        }
    except asyncio.TimeoutError:
        return {"success": False, "stdout": "", "stderr": "Command timed out", "returncode": -1}
    except FileNotFoundError:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Command not found: {args[0]}",
            "returncode": -1,
        }
    except OSError as e:
        return {"success": False, "stdout": "", "stderr": str(e), "returncode": -1}


async def list_services(
    state: Optional[str] = None,
) -> Dict[str, Any]:
    """List systemd services.

    Args:
        state: Filter by state ('running', 'dead', 'failed', or None for all).

    Returns:
        Dict with 'success' and 'services' list.
    """
    args = ["systemctl", "list-units", "--type=service", "--no-pager", "--plain"]
    if state:
        args.extend([f"--state={state}"])

    result = await _run_command(*args)
    if not result["success"] and not result["stdout"]:
        return {"success": False, "error": result["stderr"], "services": []}

    services: List[Dict[str, str]] = []
    for line in result["stdout"].splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[0].endswith(".service"):
            services.append({
                "name": parts[0],
                "load": parts[1],
                "active": parts[2],
                "sub": parts[3],
                "description": " ".join(parts[4:]) if len(parts) > 4 else "",
            })

    return {"success": True, "services": services}


async def get_service_status(name: str) -> Dict[str, Any]:
    """Get detailed status of a specific service.

    Args:
        name: Service name (with or without .service suffix).

    Returns:
        Dict with 'success' and service status details.
    """
    if not name.endswith(".service"):
        name = f"{name}.service"

    result = await _run_command("systemctl", "show", name, "--no-pager")
    if not result["success"] and not result["stdout"]:
        return {"success": False, "error": result["stderr"], "service": name}

    status: Dict[str, str] = {}
    for line in result["stdout"].splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            status[key.strip()] = value.strip()

    return {
        "success": True,
        "service": name,
        "active_state": status.get("ActiveState", "unknown"),
        "sub_state": status.get("SubState", "unknown"),
        "load_state": status.get("LoadState", "unknown"),
        "description": status.get("Description", ""),
        "main_pid": status.get("MainPID", "0"),
        "memory": status.get("MemoryCurrent", ""),
        "started_at": status.get("ActiveEnterTimestamp", ""),
        "enabled": status.get("UnitFileState", "unknown"),
    }


async def start_service(name: str) -> Dict[str, Any]:
    """Start a systemd service.

    Args:
        name: Service name.

    Returns:
        Dict with 'success' and action info.
    """
    if not name.endswith(".service"):
        name = f"{name}.service"

    result = await _run_command("systemctl", "start", name)
    return {
        "success": result["success"],
        "service": name,
        "action": "start",
        "error": result["stderr"] if not result["success"] else None,
    }


async def stop_service(name: str) -> Dict[str, Any]:
    """Stop a systemd service.

    Args:
        name: Service name.

    Returns:
        Dict with 'success' and action info.
    """
    if not name.endswith(".service"):
        name = f"{name}.service"

    result = await _run_command("systemctl", "stop", name)
    return {
        "success": result["success"],
        "service": name,
        "action": "stop",
        "error": result["stderr"] if not result["success"] else None,
    }


async def restart_service(name: str) -> Dict[str, Any]:
    """Restart a systemd service.

    Args:
        name: Service name.

    Returns:
        Dict with 'success' and action info.
    """
    if not name.endswith(".service"):
        name = f"{name}.service"

    result = await _run_command("systemctl", "restart", name)
    return {
        "success": result["success"],
        "service": name,
        "action": "restart",
        "error": result["stderr"] if not result["success"] else None,
    }


async def enable_service(name: str) -> Dict[str, Any]:
    """Enable a systemd service to start on boot.

    Args:
        name: Service name.

    Returns:
        Dict with 'success' and action info.
    """
    if not name.endswith(".service"):
        name = f"{name}.service"

    result = await _run_command("systemctl", "enable", name)
    return {
        "success": result["success"],
        "service": name,
        "action": "enable",
        "error": result["stderr"] if not result["success"] else None,
    }


async def disable_service(name: str) -> Dict[str, Any]:
    """Disable a systemd service from starting on boot.

    Args:
        name: Service name.

    Returns:
        Dict with 'success' and action info.
    """
    if not name.endswith(".service"):
        name = f"{name}.service"

    result = await _run_command("systemctl", "disable", name)
    return {
        "success": result["success"],
        "service": name,
        "action": "disable",
        "error": result["stderr"] if not result["success"] else None,
    }


async def get_service_logs(
    name: str, lines: int = 50, since: Optional[str] = None
) -> Dict[str, Any]:
    """Get logs for a systemd service via journalctl.

    Args:
        name: Service name.
        lines: Number of recent log lines.
        since: Optional time filter (e.g., '1h ago', 'today').

    Returns:
        Dict with 'success' and 'logs' string.
    """
    if not name.endswith(".service"):
        name = f"{name}.service"

    args = ["journalctl", "-u", name, "--no-pager", "-n", str(lines)]
    if since:
        args.extend(["--since", since])

    result = await _run_command(*args)
    return {
        "success": result["success"] or bool(result["stdout"]),
        "service": name,
        "logs": result["stdout"],
        "error": result["stderr"] if not result["success"] and not result["stdout"] else None,
    }
