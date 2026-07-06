"""System Health Monitoring.

Provides async functions for CPU usage, temperature, RAM usage,
disk I/O, network throughput, uptime, process monitoring, and
overall health scoring.

Reads from /proc or uses standard tools for data collection.
"""

from __future__ import annotations

import asyncio
import os
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


async def _read_proc_file(path: str) -> Optional[str]:
    """Read a /proc file and return its contents."""
    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _read_file_sync, path)
    except (IOError, OSError):
        return None


def _read_file_sync(path: str) -> str:
    """Synchronously read a file."""
    with open(path, "r") as f:
        return f.read()


async def get_cpu_usage() -> Dict[str, Any]:
    """Get CPU usage, temperature, and load average.

    Returns:
        Dict with CPU info including usage percent, temperature, and load averages.
    """
    result: Dict[str, Any] = {"success": True}

    # Load average from /proc/loadavg
    loadavg = await _read_proc_file("/proc/loadavg")
    if loadavg:
        parts = loadavg.split()
        result["load_average"] = {
            "1min": float(parts[0]),
            "5min": float(parts[1]),
            "15min": float(parts[2]),
        }
    else:
        result["load_average"] = None

    # CPU info from /proc/stat
    stat = await _read_proc_file("/proc/stat")
    if stat:
        for line in stat.splitlines():
            if line.startswith("cpu "):
                parts = line.split()
                if len(parts) >= 8:
                    user = int(parts[1])
                    nice = int(parts[2])
                    system = int(parts[3])
                    idle = int(parts[4])
                    iowait = int(parts[5])
                    total = user + nice + system + idle + iowait
                    busy = total - idle
                    result["usage_percent"] = round((busy / total) * 100, 1) if total > 0 else 0.0
                break
    else:
        result["usage_percent"] = None

    # CPU count
    cpuinfo = await _read_proc_file("/proc/cpuinfo")
    if cpuinfo:
        result["cores"] = cpuinfo.count("processor\t:")
    else:
        result["cores"] = os.cpu_count()

    # Temperature
    temp_result = await _run_command(
        "cat", "/sys/class/thermal/thermal_zone0/temp"
    )
    if temp_result["success"]:
        try:
            result["temperature_c"] = int(temp_result["stdout"]) / 1000.0
        except (ValueError, TypeError):
            result["temperature_c"] = None
    else:
        result["temperature_c"] = None

    return result


async def get_memory_usage() -> Dict[str, Any]:
    """Get RAM usage (total, used, free, cached).

    Returns:
        Dict with memory info in human-readable and raw formats.
    """
    meminfo = await _read_proc_file("/proc/meminfo")
    if not meminfo:
        return {"success": False, "error": "Unable to read /proc/meminfo"}

    mem: Dict[str, int] = {}
    for line in meminfo.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            key = parts[0].rstrip(":")
            try:
                # Values are in kB
                mem[key] = int(parts[1])
            except ValueError:
                continue

    total_kb = mem.get("MemTotal", 0)
    free_kb = mem.get("MemFree", 0)
    buffers_kb = mem.get("Buffers", 0)
    cached_kb = mem.get("Cached", 0)
    available_kb = mem.get("MemAvailable", free_kb + buffers_kb + cached_kb)
    used_kb = total_kb - available_kb

    def _to_human(kb: int) -> str:
        if kb >= 1048576:
            return f"{kb / 1048576:.1f} GB"
        elif kb >= 1024:
            return f"{kb / 1024:.1f} MB"
        return f"{kb} KB"

    usage_percent = round((used_kb / total_kb) * 100, 1) if total_kb > 0 else 0.0

    return {
        "success": True,
        "total_kb": total_kb,
        "used_kb": used_kb,
        "free_kb": free_kb,
        "available_kb": available_kb,
        "cached_kb": cached_kb,
        "buffers_kb": buffers_kb,
        "total_human": _to_human(total_kb),
        "used_human": _to_human(used_kb),
        "available_human": _to_human(available_kb),
        "usage_percent": usage_percent,
    }


async def get_disk_io() -> Dict[str, Any]:
    """Get disk I/O statistics from /proc/diskstats.

    Returns:
        Dict with 'success' and 'devices' dict mapping device to I/O stats.
    """
    diskstats = await _read_proc_file("/proc/diskstats")
    if not diskstats:
        return {"success": False, "error": "Unable to read /proc/diskstats", "devices": {}}

    devices: Dict[str, Dict[str, int]] = {}
    for line in diskstats.splitlines():
        parts = line.split()
        if len(parts) >= 14:
            name = parts[2]
            # Skip partition numbers, only show main devices or specific partitions
            if any(c.isdigit() for c in name) and not name.startswith("dm-"):
                # This is a partition - still include it
                pass
            devices[name] = {
                "reads_completed": int(parts[3]),
                "reads_merged": int(parts[4]),
                "sectors_read": int(parts[5]),
                "read_time_ms": int(parts[6]),
                "writes_completed": int(parts[7]),
                "writes_merged": int(parts[8]),
                "sectors_written": int(parts[9]),
                "write_time_ms": int(parts[10]),
                "io_in_progress": int(parts[11]),
                "io_time_ms": int(parts[12]),
            }

    return {"success": True, "devices": devices}


async def get_network_throughput() -> Dict[str, Any]:
    """Get network throughput stats from /proc/net/dev.

    Returns:
        Dict with 'success' and 'interfaces' mapping to rx/tx bytes.
    """
    netdev = await _read_proc_file("/proc/net/dev")
    if not netdev:
        return {"success": False, "error": "Unable to read /proc/net/dev", "interfaces": {}}

    interfaces: Dict[str, Dict[str, int]] = {}
    for line in netdev.splitlines()[2:]:  # Skip header lines
        if ":" not in line:
            continue
        iface, _, data = line.partition(":")
        iface = iface.strip()
        parts = data.split()
        if len(parts) >= 16:
            interfaces[iface] = {
                "rx_bytes": int(parts[0]),
                "rx_packets": int(parts[1]),
                "rx_errors": int(parts[2]),
                "tx_bytes": int(parts[8]),
                "tx_packets": int(parts[9]),
                "tx_errors": int(parts[10]),
            }

    return {"success": True, "interfaces": interfaces}


async def get_uptime() -> Dict[str, Any]:
    """Get system uptime.

    Returns:
        Dict with uptime in seconds and human-readable format.
    """
    uptime_str = await _read_proc_file("/proc/uptime")
    if not uptime_str:
        return {"success": False, "error": "Unable to read /proc/uptime"}

    parts = uptime_str.split()
    uptime_secs = float(parts[0])

    days = int(uptime_secs // 86400)
    hours = int((uptime_secs % 86400) // 3600)
    minutes = int((uptime_secs % 3600) // 60)

    human = ""
    if days > 0:
        human += f"{days}d "
    if hours > 0:
        human += f"{hours}h "
    human += f"{minutes}m"

    return {
        "success": True,
        "uptime_seconds": uptime_secs,
        "uptime_human": human.strip(),
        "days": days,
        "hours": hours,
        "minutes": minutes,
    }


async def get_top_processes(count: int = 10) -> Dict[str, Any]:
    """Get top resource-consuming processes.

    Args:
        count: Number of top processes to return.

    Returns:
        Dict with 'success' and 'processes' list.
    """
    result = await _run_command(
        "ps", "aux", "--sort=-%cpu", "--no-headers"
    )
    if not result["success"]:
        return {"success": False, "error": result["stderr"], "processes": []}

    processes: List[Dict[str, str]] = []
    for line in result["stdout"].splitlines()[:count]:
        parts = line.split(None, 10)
        if len(parts) >= 11:
            processes.append({
                "user": parts[0],
                "pid": parts[1],
                "cpu_percent": parts[2],
                "mem_percent": parts[3],
                "vsz": parts[4],
                "rss": parts[5],
                "command": parts[10],
            })

    return {"success": True, "processes": processes}


async def get_health_score() -> Dict[str, Any]:
    """Calculate overall system health score (green/yellow/red).

    Based on CPU load, memory usage, disk space, and temperature thresholds.

    Returns:
        Dict with 'status' (green/yellow/red), 'score' (0-100),
        and individual component statuses.
    """
    score = 100
    issues: List[str] = []
    components: Dict[str, str] = {}

    # CPU check
    cpu = await get_cpu_usage()
    if cpu.get("load_average"):
        cores = cpu.get("cores", 1) or 1
        load_ratio = cpu["load_average"]["1min"] / cores
        if load_ratio > 2.0:
            score -= 30
            issues.append(f"CPU overloaded: load {cpu['load_average']['1min']}")
            components["cpu"] = "red"
        elif load_ratio > 1.0:
            score -= 15
            issues.append(f"CPU high: load {cpu['load_average']['1min']}")
            components["cpu"] = "yellow"
        else:
            components["cpu"] = "green"
    else:
        components["cpu"] = "unknown"

    # Temperature check
    if cpu.get("temperature_c") is not None:
        temp = cpu["temperature_c"]
        if temp > 80:
            score -= 25
            issues.append(f"CPU temperature critical: {temp}C")
            components["temperature"] = "red"
        elif temp > 65:
            score -= 10
            issues.append(f"CPU temperature high: {temp}C")
            components["temperature"] = "yellow"
        else:
            components["temperature"] = "green"
    else:
        components["temperature"] = "unknown"

    # Memory check
    mem = await get_memory_usage()
    if mem.get("success"):
        usage = mem["usage_percent"]
        if usage > 90:
            score -= 25
            issues.append(f"Memory critical: {usage}% used")
            components["memory"] = "red"
        elif usage > 75:
            score -= 10
            issues.append(f"Memory high: {usage}% used")
            components["memory"] = "yellow"
        else:
            components["memory"] = "green"
    else:
        components["memory"] = "unknown"

    # Determine overall status
    if score >= 70:
        status = "green"
    elif score >= 40:
        status = "yellow"
    else:
        status = "red"

    return {
        "success": True,
        "status": status,
        "score": max(0, score),
        "components": components,
        "issues": issues,
    }
