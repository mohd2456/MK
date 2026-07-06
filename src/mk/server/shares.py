"""Network File Sharing (Samba/SMB) Management.

Provides async functions to create/remove SMB shares, list active shares,
manage permissions, and generate Samba configuration sections.

This module handles config generation and service reload, not Samba installation.
"""

from __future__ import annotations

import asyncio
import re
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


def generate_share_config(
    name: str,
    path: str,
    comment: str = "",
    read_only: bool = False,
    guest_ok: bool = False,
    valid_users: Optional[List[str]] = None,
    browseable: bool = True,
) -> str:
    """Generate a Samba share configuration section.

    Args:
        name: Share name.
        path: Filesystem path to share.
        comment: Optional share description.
        read_only: If True, share is read-only.
        guest_ok: If True, allow guest access.
        valid_users: List of allowed usernames. None means all users.
        browseable: If True, share is visible in network browsing.

    Returns:
        Samba config section as a string.
    """
    lines = [f"[{name}]"]
    if comment:
        lines.append(f"   comment = {comment}")
    lines.append(f"   path = {path}")
    lines.append(f"   browseable = {'yes' if browseable else 'no'}")
    lines.append(f"   read only = {'yes' if read_only else 'no'}")
    lines.append(f"   guest ok = {'yes' if guest_ok else 'no'}")
    if valid_users:
        lines.append(f"   valid users = {' '.join(valid_users)}")
    lines.append("")
    return "\n".join(lines)


async def list_shares(config_path: str = "/etc/samba/smb.conf") -> Dict[str, Any]:
    """List active SMB shares from Samba configuration.

    Args:
        config_path: Path to smb.conf file.

    Returns:
        Dict with 'success' and 'shares' list.
    """
    result = await _run_command("cat", config_path)
    if not result["success"]:
        return {"success": False, "error": result["stderr"], "shares": []}

    shares: List[Dict[str, str]] = []
    current_share: Optional[Dict[str, str]] = None

    for line in result["stdout"].splitlines():
        line = line.strip()
        # Match section header like [sharename]
        match = re.match(r"^\[(.+)\]$", line)
        if match:
            if current_share and current_share["name"] not in ("global", "homes", "printers"):
                shares.append(current_share)
            current_share = {"name": match.group(1)}
            continue

        if current_share and "=" in line:
            key, _, value = line.partition("=")
            current_share[key.strip()] = value.strip()

    # Don't forget the last share
    if current_share and current_share["name"] not in ("global", "homes", "printers"):
        shares.append(current_share)

    return {"success": True, "shares": shares}


async def create_share(
    name: str,
    path: str,
    comment: str = "",
    read_only: bool = False,
    guest_ok: bool = False,
    valid_users: Optional[List[str]] = None,
    config_path: str = "/etc/samba/smb.conf",
) -> Dict[str, Any]:
    """Create a new SMB share by appending to Samba config.

    Args:
        name: Share name.
        path: Filesystem path to share.
        comment: Optional description.
        read_only: If True, share is read-only.
        guest_ok: If True, allow guest access.
        valid_users: List of allowed usernames.
        config_path: Path to smb.conf.

    Returns:
        Dict with 'success' and share details.
    """
    # Generate the config section
    config_section = generate_share_config(
        name=name,
        path=path,
        comment=comment,
        read_only=read_only,
        guest_ok=guest_ok,
        valid_users=valid_users,
    )

    # Append to config file
    try:
        proc = await asyncio.create_subprocess_exec(
            "tee", "-a", config_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=f"\n{config_section}".encode()), timeout=10.0
        )
        if proc.returncode != 0:
            return {
                "success": False,
                "error": stderr.decode("utf-8", errors="replace").strip(),
            }
    except (asyncio.TimeoutError, FileNotFoundError, OSError) as e:
        return {"success": False, "error": str(e)}

    # Reload Samba service
    reload_result = await reload_samba()

    return {
        "success": True,
        "share": {
            "name": name,
            "path": path,
            "read_only": read_only,
            "guest_ok": guest_ok,
        },
        "service_reloaded": reload_result["success"],
    }


async def remove_share(
    name: str,
    config_path: str = "/etc/samba/smb.conf",
) -> Dict[str, Any]:
    """Remove an SMB share from Samba configuration.

    Args:
        name: Share name to remove.
        config_path: Path to smb.conf.

    Returns:
        Dict with 'success' indicating if share was removed.
    """
    result = await _run_command("cat", config_path)
    if not result["success"]:
        return {"success": False, "error": result["stderr"]}

    lines = result["stdout"].splitlines()
    new_lines: List[str] = []
    in_target_section = False
    found = False

    for line in lines:
        match = re.match(r"^\[(.+)\]$", line.strip())
        if match:
            if match.group(1) == name:
                in_target_section = True
                found = True
                continue
            else:
                in_target_section = False

        if not in_target_section:
            new_lines.append(line)

    if not found:
        return {"success": False, "error": f"Share '{name}' not found"}

    # Write the new config
    new_content = "\n".join(new_lines)
    try:
        proc = await asyncio.create_subprocess_exec(
            "tee", config_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=new_content.encode()), timeout=10.0
        )
        if proc.returncode != 0:
            return {
                "success": False,
                "error": stderr.decode("utf-8", errors="replace").strip(),
            }
    except (asyncio.TimeoutError, FileNotFoundError, OSError) as e:
        return {"success": False, "error": str(e)}

    reload_result = await reload_samba()
    return {"success": True, "removed": name, "service_reloaded": reload_result["success"]}


async def reload_samba() -> Dict[str, Any]:
    """Reload the Samba service to apply config changes.

    Returns:
        Dict with 'success' indicating if reload succeeded.
    """
    result = await _run_command("systemctl", "reload", "smbd")
    return {
        "success": result["success"],
        "error": result["stderr"] if not result["success"] else None,
    }


async def set_share_permissions(
    name: str,
    read_only: bool = False,
    valid_users: Optional[List[str]] = None,
    config_path: str = "/etc/samba/smb.conf",
) -> Dict[str, Any]:
    """Update permissions for an existing share.

    Args:
        name: Share name.
        read_only: If True, make read-only.
        valid_users: List of allowed users. None means keep current.
        config_path: Path to smb.conf.

    Returns:
        Dict with 'success' and updated permission info.
    """
    result = await _run_command("cat", config_path)
    if not result["success"]:
        return {"success": False, "error": result["stderr"]}

    lines = result["stdout"].splitlines()
    new_lines: List[str] = []
    in_target_section = False
    found = False
    read_only_set = False
    users_set = False

    for line in lines:
        match = re.match(r"^\[(.+)\]$", line.strip())
        if match:
            if in_target_section:
                # Before leaving section, add missing directives
                if not read_only_set:
                    new_lines.append(f"   read only = {'yes' if read_only else 'no'}")
                if not users_set and valid_users is not None:
                    new_lines.append(f"   valid users = {' '.join(valid_users)}")
            in_target_section = match.group(1) == name
            if in_target_section:
                found = True
                read_only_set = False
                users_set = False
            new_lines.append(line)
            continue

        if in_target_section:
            stripped = line.strip()
            if stripped.startswith("read only"):
                new_lines.append(f"   read only = {'yes' if read_only else 'no'}")
                read_only_set = True
            elif stripped.startswith("valid users") and valid_users is not None:
                new_lines.append(f"   valid users = {' '.join(valid_users)}")
                users_set = True
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    # Handle case where section is the last one
    if in_target_section:
        if not read_only_set:
            new_lines.append(f"   read only = {'yes' if read_only else 'no'}")
        if not users_set and valid_users is not None:
            new_lines.append(f"   valid users = {' '.join(valid_users)}")

    if not found:
        return {"success": False, "error": f"Share '{name}' not found"}

    # Write back
    new_content = "\n".join(new_lines)
    try:
        proc = await asyncio.create_subprocess_exec(
            "tee", config_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=new_content.encode()), timeout=10.0
        )
        if proc.returncode != 0:
            return {"success": False, "error": stderr.decode("utf-8", errors="replace").strip()}
    except (asyncio.TimeoutError, FileNotFoundError, OSError) as e:
        return {"success": False, "error": str(e)}

    reload_result = await reload_samba()
    return {
        "success": True,
        "share": name,
        "read_only": read_only,
        "valid_users": valid_users,
        "service_reloaded": reload_result["success"],
    }
