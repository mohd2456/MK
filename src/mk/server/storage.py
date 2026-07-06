"""Storage and Drive Management.

Provides async functions to list drives/partitions, check SMART health,
show disk usage, monitor temperatures, and alert on failing drives or
low disk space.

All data is returned as structured Python dicts/lists.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional


async def _run_command(
    *args: str, timeout: float = 30.0
) -> Dict[str, Any]:
    """Run a subprocess command and return structured result.

    Args:
        *args: Command and arguments.
        timeout: Maximum seconds to wait.

    Returns:
        Dict with 'success', 'stdout', 'stderr', and 'returncode'.
    """
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
        return {
            "success": False,
            "stdout": "",
            "stderr": "Command timed out",
            "returncode": -1,
        }
    except FileNotFoundError:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Command not found: {args[0]}",
            "returncode": -1,
        }
    except OSError as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(e),
            "returncode": -1,
        }


async def list_drives() -> Dict[str, Any]:
    """List all drives and partitions using lsblk.

    Returns:
        Dict with 'success' bool and 'drives' list containing drive info
        (name, size, type, mountpoint, fstype, model).
    """
    result = await _run_command(
        "lsblk", "-J", "-o", "NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE,MODEL"
    )
    if not result["success"]:
        return {"success": False, "error": result["stderr"], "drives": []}

    try:
        data = json.loads(result["stdout"])
        drives = []
        for device in data.get("blockdevices", []):
            drive_info: Dict[str, Any] = {
                "name": device.get("name", ""),
                "size": device.get("size", ""),
                "type": device.get("type", ""),
                "mountpoint": device.get("mountpoint"),
                "fstype": device.get("fstype"),
                "model": device.get("model"),
                "children": [],
            }
            for child in device.get("children", []):
                drive_info["children"].append({
                    "name": child.get("name", ""),
                    "size": child.get("size", ""),
                    "type": child.get("type", ""),
                    "mountpoint": child.get("mountpoint"),
                    "fstype": child.get("fstype"),
                })
            drives.append(drive_info)
        return {"success": True, "drives": drives}
    except (json.JSONDecodeError, KeyError) as e:
        return {"success": False, "error": f"Failed to parse lsblk output: {e}", "drives": []}


async def check_smart_health(device: str) -> Dict[str, Any]:
    """Check drive health via SMART using smartctl.

    Args:
        device: Device path (e.g., '/dev/sda').

    Returns:
        Dict with health status, temperature, and attributes.
    """
    result = await _run_command("smartctl", "-j", "-a", device)
    if not result["success"] and not result["stdout"]:
        return {"success": False, "error": result["stderr"], "device": device}

    try:
        data = json.loads(result["stdout"])
        health_status = data.get("smart_status", {}).get("passed", None)
        temperature = data.get("temperature", {}).get("current")
        power_on_hours = None
        reallocated_sectors = None

        for attr in data.get("ata_smart_attributes", {}).get("table", []):
            if attr.get("name") == "Power_On_Hours":
                power_on_hours = attr.get("raw", {}).get("value")
            elif attr.get("name") == "Reallocated_Sector_Ct":
                reallocated_sectors = attr.get("raw", {}).get("value")

        return {
            "success": True,
            "device": device,
            "healthy": health_status,
            "temperature_c": temperature,
            "power_on_hours": power_on_hours,
            "reallocated_sectors": reallocated_sectors,
            "model": data.get("model_name"),
            "serial": data.get("serial_number"),
        }
    except (json.JSONDecodeError, KeyError) as e:
        return {"success": False, "error": f"Failed to parse smartctl output: {e}", "device": device}


async def get_disk_usage() -> Dict[str, Any]:
    """Show disk usage per mount point using df.

    Returns:
        Dict with 'success' and 'filesystems' list containing usage info.
    """
    result = await _run_command("df", "-h", "--output=source,size,used,avail,pcent,target")
    if not result["success"]:
        return {"success": False, "error": result["stderr"], "filesystems": []}

    filesystems: List[Dict[str, str]] = []
    lines = result["stdout"].splitlines()
    for line in lines[1:]:  # Skip header
        parts = line.split()
        if len(parts) >= 6:
            filesystems.append({
                "device": parts[0],
                "size": parts[1],
                "used": parts[2],
                "available": parts[3],
                "use_percent": parts[4],
                "mountpoint": parts[5],
            })

    return {"success": True, "filesystems": filesystems}


async def get_drive_temperatures() -> Dict[str, Any]:
    """Monitor drive temperatures using smartctl or hddtemp.

    Returns:
        Dict with 'success' and 'temperatures' dict mapping device to temp.
    """
    # First get list of block devices
    result = await _run_command("lsblk", "-d", "-n", "-o", "NAME,TYPE")
    if not result["success"]:
        return {"success": False, "error": result["stderr"], "temperatures": {}}

    temperatures: Dict[str, Optional[int]] = {}
    for line in result["stdout"].splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "disk":
            device = f"/dev/{parts[0]}"
            smart = await check_smart_health(device)
            if smart.get("success"):
                temperatures[device] = smart.get("temperature_c")
            else:
                temperatures[device] = None

    return {"success": True, "temperatures": temperatures}


async def check_drive_alerts(
    space_threshold: int = 90,
    temp_threshold: int = 55,
) -> Dict[str, Any]:
    """Check for drive alerts (failing drives, low space, high temperature).

    Args:
        space_threshold: Percent usage to trigger low space alert.
        temp_threshold: Temperature in Celsius to trigger alert.

    Returns:
        Dict with 'alerts' list of warning messages and 'status' (ok/warning/critical).
    """
    alerts: List[Dict[str, str]] = []
    status = "ok"

    # Check disk space
    usage = await get_disk_usage()
    if usage["success"]:
        for fs in usage["filesystems"]:
            try:
                pct = int(fs["use_percent"].rstrip("%"))
                if pct >= space_threshold:
                    alerts.append({
                        "type": "low_space",
                        "severity": "critical" if pct >= 95 else "warning",
                        "message": (
                            f"Low disk space on {fs['mountpoint']}: "
                            f"{fs['use_percent']} used ({fs['available']} free)"
                        ),
                        "device": fs["device"],
                    })
                    status = "critical" if pct >= 95 else "warning"
            except (ValueError, KeyError):
                continue

    # Check temperatures
    temps = await get_drive_temperatures()
    if temps["success"]:
        for device, temp in temps["temperatures"].items():
            if temp is not None and temp >= temp_threshold:
                alerts.append({
                    "type": "high_temperature",
                    "severity": "critical" if temp >= 65 else "warning",
                    "message": f"High temperature on {device}: {temp}C",
                    "device": device,
                })
                if temp >= 65:
                    status = "critical"
                elif status != "critical":
                    status = "warning"

    return {"success": True, "status": status, "alerts": alerts}
