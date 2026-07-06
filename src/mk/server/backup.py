"""Backup Management.

Provides async functions for creating compressed backups, listing existing
backups, restoring from backup, scheduled backup support (cron), and
backup rotation (keep last N).
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Dict, List, Optional


async def _run_command(
    *args: str, timeout: float = 600.0
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


async def create_backup(
    source_dirs: List[str],
    backup_dir: str,
    name: Optional[str] = None,
    compression: str = "gz",
) -> Dict[str, Any]:
    """Create a compressed backup of specified directories.

    Args:
        source_dirs: List of directories to back up.
        backup_dir: Directory to store the backup file.
        name: Optional backup name prefix. Defaults to 'backup'.
        compression: Compression type ('gz', 'bz2', 'xz').

    Returns:
        Dict with 'success', backup 'path', and 'size'.
    """
    if not source_dirs:
        return {"success": False, "error": "No source directories specified"}

    prefix = name or "backup"
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    ext_map = {"gz": "tar.gz", "bz2": "tar.bz2", "xz": "tar.xz"}
    extension = ext_map.get(compression, "tar.gz")
    filename = f"{prefix}_{timestamp}.{extension}"
    backup_path = os.path.join(backup_dir, filename)

    # Ensure backup directory exists
    result = await _run_command("mkdir", "-p", backup_dir)
    if not result["success"]:
        return {"success": False, "error": f"Cannot create backup dir: {result['stderr']}"}

    # Build tar command
    comp_flag = {"gz": "-z", "bz2": "-j", "xz": "-J"}.get(compression, "-z")
    args = ["tar", comp_flag, "-cf", backup_path] + source_dirs

    result = await _run_command(*args)
    if not result["success"]:
        return {
            "success": False,
            "error": f"Backup creation failed: {result['stderr']}",
            "path": backup_path,
        }

    # Get file size
    size_result = await _run_command("stat", "--printf=%s", backup_path)
    size = None
    if size_result["success"] and size_result["stdout"]:
        try:
            size = int(size_result["stdout"])
        except ValueError:
            size = None

    return {
        "success": True,
        "path": backup_path,
        "filename": filename,
        "size_bytes": size,
        "source_dirs": source_dirs,
        "compression": compression,
        "timestamp": timestamp,
    }


async def list_backups(
    backup_dir: str, pattern: str = "*.tar.*"
) -> Dict[str, Any]:
    """List existing backups in a directory.

    Args:
        backup_dir: Directory containing backups.
        pattern: Glob pattern to match backup files.

    Returns:
        Dict with 'success' and 'backups' list (sorted newest first).
    """
    result = await _run_command(
        "find", backup_dir, "-maxdepth", "1", "-name", pattern, "-type", "f"
    )
    if not result["success"]:
        return {"success": False, "error": result["stderr"], "backups": []}

    backups: List[Dict[str, Any]] = []
    for filepath in result["stdout"].splitlines():
        if not filepath.strip():
            continue
        # Get file info
        stat_result = await _run_command(
            "stat", "--printf=%s\n%Y", filepath
        )
        size = None
        modified = None
        if stat_result["success"]:
            parts = stat_result["stdout"].split("\n")
            if len(parts) >= 2:
                try:
                    size = int(parts[0])
                    modified = int(parts[1])
                except ValueError:
                    pass

        backups.append({
            "path": filepath,
            "filename": os.path.basename(filepath),
            "size_bytes": size,
            "modified_timestamp": modified,
        })

    # Sort by modification time, newest first
    backups.sort(key=lambda b: b.get("modified_timestamp") or 0, reverse=True)

    return {"success": True, "backups": backups, "count": len(backups)}


async def restore_backup(
    backup_path: str,
    restore_dir: str,
    strip_components: int = 0,
) -> Dict[str, Any]:
    """Restore from a backup archive.

    Args:
        backup_path: Path to the backup archive.
        restore_dir: Directory to restore files into.
        strip_components: Number of leading path components to strip.

    Returns:
        Dict with 'success' and restore details.
    """
    # Ensure restore directory exists
    result = await _run_command("mkdir", "-p", restore_dir)
    if not result["success"]:
        return {"success": False, "error": f"Cannot create restore dir: {result['stderr']}"}

    # Determine compression from extension
    args = ["tar", "-xf", backup_path, "-C", restore_dir]
    if strip_components > 0:
        args.extend([f"--strip-components={strip_components}"])

    result = await _run_command(*args)
    if not result["success"]:
        return {
            "success": False,
            "error": f"Restore failed: {result['stderr']}",
            "backup": backup_path,
        }

    return {
        "success": True,
        "backup": backup_path,
        "restore_dir": restore_dir,
        "strip_components": strip_components,
    }


async def schedule_backup(
    source_dirs: List[str],
    backup_dir: str,
    schedule: str = "0 2 * * *",
    name: Optional[str] = None,
    compression: str = "gz",
    keep_last: int = 7,
) -> Dict[str, Any]:
    """Schedule a recurring backup via cron.

    Args:
        source_dirs: Directories to back up.
        backup_dir: Where to store backups.
        schedule: Cron schedule expression (default: 2am daily).
        name: Backup name prefix.
        compression: Compression type.
        keep_last: Number of backups to retain.

    Returns:
        Dict with 'success' and cron entry details.
    """
    prefix = name or "backup"
    sources = " ".join(source_dirs)
    comp_flag = {"gz": "-z", "bz2": "-j", "xz": "-J"}.get(compression, "-z")
    ext = {"gz": "tar.gz", "bz2": "tar.bz2", "xz": "tar.xz"}.get(compression, "tar.gz")

    # Build the cron command
    cron_command = (
        f"tar {comp_flag} -cf {backup_dir}/{prefix}_$(date +\\%Y\\%m\\%d_\\%H\\%M\\%S).{ext} "
        f"{sources} && "
        f"cd {backup_dir} && ls -t {prefix}_*.{ext} | tail -n +{keep_last + 1} | xargs -r rm --"
    )

    cron_entry = f"{schedule} {cron_command}"

    # Add to crontab
    # Get existing crontab
    existing = await _run_command("crontab", "-l")
    current_crontab = existing["stdout"] if existing["success"] else ""

    # Remove any existing entry for this backup
    lines = [
        line for line in current_crontab.splitlines()
        if f"{backup_dir}/{prefix}_" not in line
    ]
    lines.append(cron_entry)

    new_crontab = "\n".join(lines) + "\n"

    # Write new crontab
    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            "crontab", "-",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=new_crontab.encode()), timeout=10.0
        )
        if proc.returncode != 0:
            return {
                "success": False,
                "error": f"Failed to set crontab: {stderr.decode()}",
            }
    except (asyncio.TimeoutError, FileNotFoundError, OSError) as e:
        return {"success": False, "error": str(e)}

    return {
        "success": True,
        "cron_entry": cron_entry,
        "schedule": schedule,
        "source_dirs": source_dirs,
        "backup_dir": backup_dir,
        "keep_last": keep_last,
    }


async def rotate_backups(
    backup_dir: str,
    keep_last: int = 7,
    pattern: str = "*.tar.*",
) -> Dict[str, Any]:
    """Rotate backups, keeping only the last N and deleting older ones.

    Args:
        backup_dir: Directory containing backups.
        keep_last: Number of most recent backups to keep.
        pattern: Glob pattern to match backup files.

    Returns:
        Dict with 'success', 'kept' count, and 'deleted' list.
    """
    listing = await list_backups(backup_dir, pattern)
    if not listing["success"]:
        return {"success": False, "error": listing.get("error", "Failed to list backups")}

    backups = listing["backups"]
    to_delete = backups[keep_last:]  # Already sorted newest first
    deleted: List[str] = []

    for backup in to_delete:
        result = await _run_command("rm", "-f", backup["path"])
        if result["success"]:
            deleted.append(backup["filename"])

    return {
        "success": True,
        "total_found": len(backups),
        "kept": min(keep_last, len(backups)),
        "deleted": deleted,
        "deleted_count": len(deleted),
    }
