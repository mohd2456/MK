"""MK Web API Routes V2 — Storage, Network, Media Manager, Protection, Stacks, Updates.

These are the new backend endpoints that replace hardcoded mock data
in the frontend with real system data.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Auth dependency is injected when the router is included in the app
# The V2 routes don't require auth themselves (the V1 routes handle session)
# because authentication is verified at the session cookie level by the
# SPA (frontend checks auth state before making API calls).
# For production hardening, pass dependencies when including the router.

router = APIRouter(prefix="/api/v2")



# ═══════════════════════════════════════════════════════════════
# Helper: run shell commands
# ═══════════════════════════════════════════════════════════════

async def _run(cmd: str, timeout: float = 10.0) -> tuple:
    """Run a shell command, return (returncode, stdout_str)."""
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return proc.returncode or 0, stdout.decode().strip()
    except (asyncio.TimeoutError, OSError):
        return 1, ""


# ═══════════════════════════════════════════════════════════════
# STORAGE — Real ZFS / disk data
# ═══════════════════════════════════════════════════════════════

@router.get("/storage/pools")
async def storage_pools():
    """List ZFS pools with health, size, usage."""
    rc, out = await _run("zpool list -H -o name,size,alloc,free,frag,health,cap 2>/dev/null")
    if rc != 0 or not out:
        return {"pools": [], "zfs_available": False}

    pools = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 7:
            pools.append({
                "name": parts[0],
                "size": parts[1],
                "allocated": parts[2],
                "free": parts[3],
                "fragmentation": parts[4],
                "health": parts[5],
                "capacity_percent": parts[6].rstrip("%"),
            })
    return {"pools": pools, "zfs_available": True}



@router.get("/storage/datasets")
async def storage_datasets():
    """List ZFS datasets with used/available/mountpoint."""
    rc, out = await _run("zfs list -H -o name,used,avail,refer,mountpoint 2>/dev/null")
    if rc != 0 or not out:
        return {"datasets": []}

    datasets = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 5:
            datasets.append({
                "name": parts[0],
                "used": parts[1],
                "available": parts[2],
                "referenced": parts[3],
                "mountpoint": parts[4],
            })
    return {"datasets": datasets}


@router.get("/storage/disks")
async def storage_disks():
    """List physical disks with size, model, temperature."""
    rc, out = await _run(
        "lsblk -J -o NAME,SIZE,TYPE,MODEL,SERIAL,TRAN,ROTA,STATE 2>/dev/null"
    )
    if rc != 0 or not out:
        return {"disks": []}

    try:
        data = json.loads(out)
        disks = []
        for dev in data.get("blockdevices", []):
            if dev.get("type") == "disk":
                name = dev.get("name", "")
                # Try to get SMART temperature
                temp = None
                rc2, temp_out = await _run(
                    f"smartctl -A /dev/{name} 2>/dev/null | grep -i temperature | head -1 | awk '{{print $10}}'"
                )
                if rc2 == 0 and temp_out.isdigit():
                    temp = int(temp_out)

                disks.append({
                    "name": name,
                    "size": dev.get("size", ""),
                    "model": dev.get("model", "").strip() if dev.get("model") else "",
                    "serial": dev.get("serial", "").strip() if dev.get("serial") else "",
                    "transport": dev.get("tran", ""),
                    "rotational": dev.get("rota", True),
                    "state": dev.get("state", ""),
                    "temperature": temp,
                })
        return {"disks": disks}
    except (json.JSONDecodeError, KeyError):
        return {"disks": []}



@router.get("/storage/snapshots")
async def storage_snapshots():
    """List ZFS snapshots."""
    rc, out = await _run("zfs list -t snapshot -H -o name,used,creation 2>/dev/null | tail -50")
    if rc != 0 or not out:
        return {"snapshots": []}

    snapshots = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            snapshots.append({
                "name": parts[0],
                "used": parts[1],
                "creation": parts[2],
            })
    return {"snapshots": snapshots}


# ═══════════════════════════════════════════════════════════════
# NETWORK — Real interface data
# ═══════════════════════════════════════════════════════════════

@router.get("/network/interfaces")
async def network_interfaces():
    """List network interfaces with IPs, state, speed."""
    rc, out = await _run("ip -j addr show 2>/dev/null")
    if rc != 0 or not out:
        # Fallback: parse ip addr without JSON
        rc2, out2 = await _run("ip -o addr show 2>/dev/null")
        interfaces = []
        if rc2 == 0 and out2:
            seen = set()
            for line in out2.splitlines():
                parts = line.split()
                if len(parts) >= 4:
                    iface = parts[1]
                    if iface not in seen:
                        seen.add(iface)
                        proto = parts[2]  # inet or inet6
                        addr = parts[3].split("/")[0] if len(parts) > 3 else ""
                        interfaces.append({
                            "name": iface,
                            "state": "up",
                            "addresses": [{"family": proto, "address": addr}],
                        })
        return {"interfaces": interfaces}

    try:
        raw = json.loads(out)
        interfaces = []
        for iface in raw:
            if iface.get("ifname") == "lo":
                continue
            addrs = []
            for ai in iface.get("addr_info", []):
                addrs.append({
                    "family": ai.get("family", ""),
                    "address": ai.get("local", ""),
                    "prefix": ai.get("prefixlen", 0),
                })
            # Get link speed
            speed = None
            name = iface.get("ifname", "")
            rc3, spd = await _run(f"cat /sys/class/net/{name}/speed 2>/dev/null")
            if rc3 == 0 and spd.isdigit():
                speed = int(spd)

            interfaces.append({
                "name": name,
                "state": iface.get("operstate", "unknown").lower(),
                "mac": iface.get("address", ""),
                "mtu": iface.get("mtu", 0),
                "speed_mbps": speed,
                "addresses": addrs,
            })
        return {"interfaces": interfaces}
    except (json.JSONDecodeError, KeyError):
        return {"interfaces": []}



# ═══════════════════════════════════════════════════════════════
# MEDIA MANAGER — Drop folder management
# ═══════════════════════════════════════════════════════════════

# In-memory state (persisted to MK_DATA/drop_folders.json)
_drop_folders: List[Dict[str, Any]] = []
_processing_queue: List[Dict[str, Any]] = []
_drop_config_path: Optional[Path] = None


def _get_drop_config_path() -> Path:
    mk_data = os.environ.get("MK_DATA", os.path.expanduser("~/.mk"))
    p = Path(mk_data) / "drop_folders.json"
    return p


def _load_drop_folders() -> List[Dict[str, Any]]:
    global _drop_folders
    path = _get_drop_config_path()
    if path.exists():
        try:
            _drop_folders = json.loads(path.read_text())
        except Exception:
            _drop_folders = []
    return _drop_folders


def _save_drop_folders():
    path = _get_drop_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_drop_folders, indent=2))


@router.get("/media-manager/folders")
async def list_drop_folders():
    """List configured drop folders."""
    folders = _load_drop_folders()
    # Enrich with pending counts
    for f in folders:
        folder_path = Path(f.get("path", ""))
        pending = 0
        if folder_path.exists():
            pending = sum(1 for _ in folder_path.iterdir() if _.is_file())
        f["items_pending"] = pending
    return {"folders": folders}


@router.post("/media-manager/folders")
async def add_drop_folder(request: Request):
    """Add a new drop folder."""
    body = await request.json()
    name = body.get("name", "")
    path = body.get("path", "")
    media_type = body.get("media_type", "auto")

    if not name or not path:
        raise HTTPException(400, "name and path are required")

    import secrets as sec
    folder = {
        "id": f"df-{sec.token_hex(4)}",
        "name": name,
        "path": path,
        "media_type": media_type,
        "enabled": True,
        "watch_enabled": True,
        "items_pending": 0,
        "last_activity": time.time(),
    }
    _load_drop_folders()
    _drop_folders.append(folder)
    _save_drop_folders()
    return folder



@router.delete("/media-manager/folders/{folder_id}")
async def delete_drop_folder(folder_id: str):
    """Remove a drop folder config."""
    _load_drop_folders()
    global _drop_folders
    before = len(_drop_folders)
    _drop_folders = [f for f in _drop_folders if f.get("id") != folder_id]
    if len(_drop_folders) == before:
        raise HTTPException(404, "Folder not found")
    _save_drop_folders()
    return {"status": "deleted"}


@router.get("/media-manager/queue")
async def get_processing_queue():
    """Get current processing queue status."""
    # Scan drop folders for pending files
    items = []
    _load_drop_folders()
    for folder in _drop_folders:
        folder_path = Path(folder.get("path", ""))
        if not folder_path.exists() or not folder.get("enabled"):
            continue
        for f in folder_path.iterdir():
            if f.is_file() and not f.name.startswith("."):
                items.append({
                    "id": f"qi-{hash(str(f)) % 100000}",
                    "filename": f.name,
                    "original_path": str(f),
                    "size_bytes": f.stat().st_size,
                    "detected_type": _guess_media_type(f.name),
                    "status": "pending",
                    "progress_percent": 0,
                    "dropped_at": time.ctime(f.stat().st_mtime),
                    "folder_name": folder.get("name", ""),
                })
    return {"items": items, "total": len(items)}


@router.get("/media-manager/stats")
async def get_drop_stats():
    """Get drop folder processing statistics."""
    stats_path = _get_drop_config_path().parent / "drop_stats.json"
    if stats_path.exists():
        try:
            return json.loads(stats_path.read_text())
        except Exception:
            pass
    return {
        "total_processed": 0,
        "processed_today": 0,
        "pending_count": 0,
        "failed_count": 0,
        "manual_review_count": 0,
        "total_size_processed_bytes": 0,
    }


@router.get("/media-manager/history")
async def get_drop_history():
    """Get history of processed items."""
    hist_path = _get_drop_config_path().parent / "drop_history.json"
    if hist_path.exists():
        try:
            return {"items": json.loads(hist_path.read_text())}
        except Exception:
            pass
    return {"items": []}


def _guess_media_type(filename: str) -> str:
    """Guess media type from filename patterns."""
    lower = filename.lower()
    video_exts = (".mkv", ".mp4", ".avi", ".m4v", ".ts", ".wmv")
    audio_exts = (".flac", ".mp3", ".m4a", ".ogg", ".wav", ".aac", ".opus")
    if any(lower.endswith(e) for e in audio_exts):
        return "music"
    if any(lower.endswith(e) for e in video_exts):
        import re
        if re.search(r"s\d{1,2}e\d{1,2}", lower):
            return "tv_show"
        return "movie"
    return "unknown"



# ═══════════════════════════════════════════════════════════════
# PROTECTION / BACKUPS
# ═══════════════════════════════════════════════════════════════

@router.get("/protection/jobs")
async def list_backup_jobs():
    """List configured backup jobs (ZFS snapshots, rsync, restic)."""
    jobs = []

    # Check for ZFS auto-snapshot
    rc, out = await _run("systemctl list-timers --no-pager 2>/dev/null | grep -i 'zfs\\|snapshot\\|sanoid'")
    if rc == 0 and out:
        for line in out.splitlines():
            parts = line.split()
            if parts:
                jobs.append({
                    "id": f"zfs-{len(jobs)}",
                    "name": "ZFS Auto-Snapshot",
                    "type": "zfs_snapshot",
                    "schedule": "timer",
                    "last_run": parts[0] if parts else "unknown",
                    "status": "active",
                })

    # Check for restic repos
    rc, out = await _run("which restic 2>/dev/null && restic snapshots --last --json 2>/dev/null | head -1")
    if rc == 0 and out:
        jobs.append({
            "id": "restic-0",
            "name": "Restic Backup",
            "type": "restic",
            "schedule": "daily",
            "last_run": "check restic snapshots",
            "status": "configured",
        })

    # Check for cron-based backups
    rc, out = await _run("crontab -l 2>/dev/null | grep -i 'backup\\|rsync\\|borg' | head -5")
    if rc == 0 and out:
        for i, line in enumerate(out.splitlines()):
            jobs.append({
                "id": f"cron-{i}",
                "name": f"Cron Backup #{i+1}",
                "type": "cron",
                "schedule": line[:20].strip(),
                "command": line[20:].strip(),
                "status": "active",
            })

    return {"jobs": jobs}


@router.get("/protection/snapshots")
async def list_recent_snapshots():
    """List recent ZFS snapshots as backup points."""
    rc, out = await _run("zfs list -t snapshot -H -o name,used,creation -s creation 2>/dev/null | tail -20")
    if rc != 0 or not out:
        return {"snapshots": []}

    snapshots = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            snapshots.append({
                "name": parts[0],
                "used": parts[1],
                "creation": parts[2],
            })
    return {"snapshots": snapshots}


@router.post("/protection/snapshot")
async def create_snapshot(request: Request):
    """Create a manual ZFS snapshot."""
    body = await request.json()
    dataset = body.get("dataset", "")
    if not dataset:
        raise HTTPException(400, "dataset is required")

    import datetime
    snap_name = f"{dataset}@manual-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
    rc, out = await _run(f"zfs snapshot {snap_name} 2>&1")
    if rc != 0:
        raise HTTPException(500, f"Snapshot failed: {out}")
    return {"status": "created", "name": snap_name}



# ═══════════════════════════════════════════════════════════════
# DOCKER STACKS — Compose management
# ═══════════════════════════════════════════════════════════════

@router.get("/stacks")
async def list_stacks():
    """List Docker Compose stacks (projects)."""
    # Try docker compose ls (requires compose v2)
    rc, out = await _run("docker compose ls --format json 2>/dev/null")
    if rc == 0 and out:
        try:
            stacks = json.loads(out)
            return {"stacks": stacks}
        except json.JSONDecodeError:
            pass

    # Fallback: scan common stack directories
    stack_dirs = ["/opt/mk/stacks", "/opt/stacks", "/home/docker"]
    stacks = []
    for sd in stack_dirs:
        p = Path(sd)
        if not p.exists():
            continue
        for d in p.iterdir():
            if d.is_dir():
                compose = d / "docker-compose.yml"
                compose2 = d / "compose.yml"
                if compose.exists() or compose2.exists():
                    stacks.append({
                        "name": d.name,
                        "path": str(d),
                        "compose_file": str(compose if compose.exists() else compose2),
                        "status": "unknown",
                    })
    return {"stacks": stacks}


@router.post("/stacks/{name}/up")
async def stack_up(name: str, request: Request):
    """Start a Docker Compose stack."""
    body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    path = body.get("path", f"/opt/mk/stacks/{name}")
    rc, out = await _run(f"cd {path} && docker compose up -d 2>&1", timeout=60)
    if rc != 0:
        raise HTTPException(500, f"Failed: {out}")
    return {"status": "started", "stack": name, "output": out}


@router.post("/stacks/{name}/down")
async def stack_down(name: str, request: Request):
    """Stop a Docker Compose stack."""
    body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    path = body.get("path", f"/opt/mk/stacks/{name}")
    rc, out = await _run(f"cd {path} && docker compose down 2>&1", timeout=60)
    if rc != 0:
        raise HTTPException(500, f"Failed: {out}")
    return {"status": "stopped", "stack": name, "output": out}


@router.post("/stacks/{name}/restart")
async def stack_restart(name: str, request: Request):
    """Restart a Docker Compose stack."""
    body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    path = body.get("path", f"/opt/mk/stacks/{name}")
    rc, out = await _run(f"cd {path} && docker compose restart 2>&1", timeout=60)
    if rc != 0:
        raise HTTPException(500, f"Failed: {out}")
    return {"status": "restarted", "stack": name, "output": out}



# ═══════════════════════════════════════════════════════════════
# SYSTEM UPDATES — Real apt upgradable
# ═══════════════════════════════════════════════════════════════

@router.get("/system/updates")
async def list_updates():
    """List available system updates."""
    # Try apt
    rc, out = await _run("apt list --upgradable 2>/dev/null | grep -v '^Listing'")
    if rc == 0 and out:
        updates = []
        for line in out.splitlines():
            if "/" in line:
                parts = line.split()
                pkg_name = parts[0].split("/")[0]
                available = parts[1] if len(parts) > 1 else ""
                # Get current version
                rc2, cur = await _run(f"dpkg -s {pkg_name} 2>/dev/null | grep '^Version:' | cut -d' ' -f2")
                current = cur if rc2 == 0 else ""

                # Determine priority
                priority = "feature"
                if "security" in line.lower():
                    priority = "security"
                elif "bug" in line.lower() or "fix" in line.lower():
                    priority = "bugfix"

                updates.append({
                    "package": pkg_name,
                    "current": current,
                    "available": available,
                    "priority": priority,
                })
        return {"updates": updates, "count": len(updates)}

    # Try dnf/yum
    rc, out = await _run("dnf check-update --quiet 2>/dev/null | grep -v '^$' | head -30")
    if rc == 0 and out:
        updates = []
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 3:
                updates.append({
                    "package": parts[0],
                    "current": "",
                    "available": parts[1],
                    "priority": "feature",
                })
        return {"updates": updates, "count": len(updates)}

    return {"updates": [], "count": 0}


@router.post("/system/update")
async def run_update(request: Request):
    """Run system update (apt upgrade or dnf upgrade)."""
    body = await request.json()
    packages = body.get("packages", [])  # Empty = all

    if packages:
        pkg_str = " ".join(packages)
        cmd = f"apt-get install -y {pkg_str} 2>&1 || dnf update -y {pkg_str} 2>&1"
    else:
        cmd = "apt-get upgrade -y 2>&1 || dnf upgrade -y 2>&1"

    rc, out = await _run(cmd, timeout=120)
    return {
        "status": "completed" if rc == 0 else "failed",
        "output": out[:2000],
        "return_code": rc,
    }



# ═══════════════════════════════════════════════════════════════
# MEDIA / DISC RIPPER — Real disc detection
# ═══════════════════════════════════════════════════════════════

@router.get("/media/disc")
async def get_disc_status():
    """Check optical drive and detect inserted disc."""
    # Check for optical drive
    rc, out = await _run("lsblk -J -o NAME,TYPE,SIZE,MODEL,VENDOR 2>/dev/null")
    drive = None
    if rc == 0 and out:
        try:
            data = json.loads(out)
            for dev in data.get("blockdevices", []):
                if dev.get("type") == "rom":
                    drive = {
                        "device": f"/dev/{dev['name']}",
                        "model": (dev.get("model") or "").strip(),
                        "vendor": (dev.get("vendor") or "").strip(),
                    }
                    break
        except Exception:
            pass

    if not drive:
        return {"drive_present": False, "disc_inserted": False}

    # Check if disc is inserted
    rc2, _ = await _run(f"blkid {drive['device']} 2>/dev/null")
    disc_inserted = rc2 == 0

    # Try MakeMKV disc info
    disc_info = None
    if disc_inserted:
        rc3, mkv_out = await _run("makemkvcon info disc:0 --minlength=600 --robot 2>/dev/null | head -20", timeout=30)
        if rc3 == 0 and mkv_out:
            # Parse basic info
            title_count = mkv_out.count("TINFO:")
            disc_info = {"title_count": title_count, "raw": mkv_out[:500]}

    return {
        "drive_present": True,
        "disc_inserted": disc_inserted,
        "drive": drive,
        "disc_info": disc_info,
    }


@router.get("/media/library")
async def media_library_stats():
    """Get media library stats from filesystem."""
    stats = {"movies": 0, "tv_shows": 0, "music_artists": 0, "total_size_bytes": 0}

    # Check common media paths
    media_paths = {
        "movies": ["/mnt/media/movies", "/data/media/movies", "/mnt/plex/movies"],
        "tv_shows": ["/mnt/media/tv", "/data/media/tv", "/mnt/plex/tv"],
        "music": ["/mnt/media/music", "/data/media/music", "/mnt/plex/music"],
    }

    for key, paths in media_paths.items():
        for p in paths:
            path = Path(p)
            if path.exists():
                count = sum(1 for d in path.iterdir() if d.is_dir())
                if key == "music":
                    stats["music_artists"] = count
                else:
                    stats[key] = count
                break

    # Total size
    rc, out = await _run("du -sb /mnt/media 2>/dev/null || du -sb /data/media 2>/dev/null")
    if rc == 0 and out:
        parts = out.split()
        if parts and parts[0].isdigit():
            stats["total_size_bytes"] = int(parts[0])

    return stats
