"""Docker Container Management (Enhanced).

Provides async functions to manage Docker containers via the docker CLI.
Supports listing containers, start/stop/restart, image management,
log viewing, compose deployment, and container stats.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional


async def _run_command(
    *args: str, timeout: float = 60.0
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


async def list_containers(all_containers: bool = True) -> Dict[str, Any]:
    """List all Docker containers with status and resource info.

    Args:
        all_containers: If True, include stopped containers.

    Returns:
        Dict with 'success' and 'containers' list.
    """
    args = [
        "docker", "ps", "--format", "{{json .}}",
    ]
    if all_containers:
        args.insert(2, "-a")

    result = await _run_command(*args)
    if not result["success"]:
        return {"success": False, "error": result["stderr"], "containers": []}

    containers: List[Dict[str, str]] = []
    for line in result["stdout"].splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            containers.append({
                "id": data.get("ID", ""),
                "name": data.get("Names", ""),
                "image": data.get("Image", ""),
                "status": data.get("Status", ""),
                "state": data.get("State", ""),
                "ports": data.get("Ports", ""),
                "created": data.get("CreatedAt", ""),
            })
        except json.JSONDecodeError:
            continue

    return {"success": True, "containers": containers}


async def start_container(name: str) -> Dict[str, Any]:
    """Start a Docker container.

    Args:
        name: Container name or ID.

    Returns:
        Dict with 'success' and status info.
    """
    result = await _run_command("docker", "start", name)
    return {
        "success": result["success"],
        "container": name,
        "action": "start",
        "error": result["stderr"] if not result["success"] else None,
    }


async def stop_container(name: str, timeout: int = 10) -> Dict[str, Any]:
    """Stop a Docker container.

    Args:
        name: Container name or ID.
        timeout: Seconds to wait before force killing.

    Returns:
        Dict with 'success' and status info.
    """
    result = await _run_command("docker", "stop", "-t", str(timeout), name)
    return {
        "success": result["success"],
        "container": name,
        "action": "stop",
        "error": result["stderr"] if not result["success"] else None,
    }


async def restart_container(name: str, timeout: int = 10) -> Dict[str, Any]:
    """Restart a Docker container.

    Args:
        name: Container name or ID.
        timeout: Seconds to wait before force killing.

    Returns:
        Dict with 'success' and status info.
    """
    result = await _run_command("docker", "restart", "-t", str(timeout), name)
    return {
        "success": result["success"],
        "container": name,
        "action": "restart",
        "error": result["stderr"] if not result["success"] else None,
    }


async def pull_image(image: str) -> Dict[str, Any]:
    """Pull a Docker image.

    Args:
        image: Image name with optional tag (e.g., 'nginx:latest').

    Returns:
        Dict with 'success' and pull details.
    """
    result = await _run_command("docker", "pull", image, timeout=300.0)
    return {
        "success": result["success"],
        "image": image,
        "output": result["stdout"] if result["success"] else None,
        "error": result["stderr"] if not result["success"] else None,
    }


async def get_container_logs(
    name: str, lines: int = 100, since: Optional[str] = None
) -> Dict[str, Any]:
    """View container logs (tail).

    Args:
        name: Container name or ID.
        lines: Number of recent lines to retrieve.
        since: Optional time filter (e.g., '1h', '2023-01-01').

    Returns:
        Dict with 'success' and 'logs' string.
    """
    args = ["docker", "logs", "--tail", str(lines)]
    if since:
        args.extend(["--since", since])
    args.append(name)

    result = await _run_command(*args)
    # Docker logs can write to stderr for some containers
    logs = result["stdout"] or result["stderr"]
    return {
        "success": result["success"] or bool(logs),
        "container": name,
        "logs": logs,
        "error": result["stderr"] if not result["success"] and not logs else None,
    }


async def deploy_compose(
    compose_path: str, project_name: Optional[str] = None
) -> Dict[str, Any]:
    """Deploy containers from a Docker Compose file.

    Args:
        compose_path: Path to docker-compose.yml file.
        project_name: Optional project name for compose.

    Returns:
        Dict with 'success' and deployment details.
    """
    args = ["docker", "compose", "-f", compose_path]
    if project_name:
        args.extend(["-p", project_name])
    args.extend(["up", "-d"])

    result = await _run_command(*args, timeout=300.0)
    return {
        "success": result["success"],
        "compose_file": compose_path,
        "output": result["stdout"] if result["success"] else None,
        "error": result["stderr"] if not result["success"] else None,
    }


async def get_container_stats(name: Optional[str] = None) -> Dict[str, Any]:
    """Get container resource stats (CPU, RAM, network).

    Args:
        name: Container name or ID. If None, get all container stats.

    Returns:
        Dict with 'success' and 'stats' list.
    """
    args = ["docker", "stats", "--no-stream", "--format", "{{json .}}"]
    if name:
        args.append(name)

    result = await _run_command(*args)
    if not result["success"]:
        return {"success": False, "error": result["stderr"], "stats": []}

    stats: List[Dict[str, str]] = []
    for line in result["stdout"].splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            stats.append({
                "container": data.get("Name", ""),
                "cpu_percent": data.get("CPUPerc", ""),
                "memory_usage": data.get("MemUsage", ""),
                "memory_percent": data.get("MemPerc", ""),
                "net_io": data.get("NetIO", ""),
                "block_io": data.get("BlockIO", ""),
                "pids": data.get("PIDs", ""),
            })
        except json.JSONDecodeError:
            continue

    return {"success": True, "stats": stats}


async def update_container(name: str) -> Dict[str, Any]:
    """Update a container by pulling latest image and recreating.

    Args:
        name: Container name.

    Returns:
        Dict with 'success' and update details.
    """
    # Get current container's image
    result = await _run_command(
        "docker", "inspect", "--format", "{{.Config.Image}}", name
    )
    if not result["success"]:
        return {"success": False, "error": f"Container not found: {result['stderr']}"}

    image = result["stdout"].strip()

    # Pull latest
    pull_result = await pull_image(image)
    if not pull_result["success"]:
        return {"success": False, "error": f"Failed to pull image: {pull_result['error']}"}

    # Restart container
    restart_result = await restart_container(name)
    return {
        "success": restart_result["success"],
        "container": name,
        "image": image,
        "action": "update",
        "error": restart_result.get("error"),
    }
