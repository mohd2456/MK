"""Network Management.

Provides async functions to show network interfaces, check connectivity,
display active connections, DNS configuration, and firewall rules.
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


async def get_interfaces() -> Dict[str, Any]:
    """Show all network interfaces and their IP addresses.

    Returns:
        Dict with 'success' and 'interfaces' list.
    """
    result = await _run_command("ip", "-j", "addr", "show")
    if not result["success"]:
        return {"success": False, "error": result["stderr"], "interfaces": []}

    import json
    try:
        data = json.loads(result["stdout"])
        interfaces: List[Dict[str, Any]] = []
        for iface in data:
            addresses: List[Dict[str, str]] = []
            for addr_info in iface.get("addr_info", []):
                addresses.append({
                    "address": addr_info.get("local", ""),
                    "prefix_len": addr_info.get("prefixlen", ""),
                    "family": addr_info.get("family", ""),
                })
            interfaces.append({
                "name": iface.get("ifname", ""),
                "state": iface.get("operstate", "UNKNOWN"),
                "mac": iface.get("address", ""),
                "mtu": iface.get("mtu", 0),
                "addresses": addresses,
            })
        return {"success": True, "interfaces": interfaces}
    except (json.JSONDecodeError, KeyError) as e:
        return {"success": False, "error": f"Failed to parse ip output: {e}", "interfaces": []}


async def check_connectivity(
    host: str = "8.8.8.8", count: int = 3, timeout_secs: int = 5
) -> Dict[str, Any]:
    """Check internet connectivity via ping.

    Args:
        host: Host to ping.
        count: Number of ping packets.
        timeout_secs: Timeout per packet in seconds.

    Returns:
        Dict with 'success', 'reachable', and latency info.
    """
    result = await _run_command(
        "ping", "-c", str(count), "-W", str(timeout_secs), host,
        timeout=float(count * timeout_secs + 5),
    )

    latency: Optional[str] = None
    packet_loss: Optional[str] = None

    if result["stdout"]:
        for line in result["stdout"].splitlines():
            if "avg" in line and "/" in line:
                # rtt min/avg/max/mdev = 1.234/5.678/9.012/1.234 ms
                parts = line.split("=")
                if len(parts) >= 2:
                    values = parts[1].strip().split("/")
                    if len(values) >= 2:
                        latency = f"{values[1]}ms"
            if "packet loss" in line:
                for part in line.split(","):
                    if "packet loss" in part:
                        packet_loss = part.strip()

    return {
        "success": True,
        "reachable": result["success"],
        "host": host,
        "latency_avg": latency,
        "packet_loss": packet_loss,
    }


async def get_active_connections() -> Dict[str, Any]:
    """Show active network connections using ss.

    Returns:
        Dict with 'success' and 'connections' list.
    """
    result = await _run_command("ss", "-tuln")
    if not result["success"]:
        return {"success": False, "error": result["stderr"], "connections": []}

    connections: List[Dict[str, str]] = []
    lines = result["stdout"].splitlines()
    for line in lines[1:]:  # Skip header
        parts = line.split()
        if len(parts) >= 5:
            connections.append({
                "protocol": parts[0],
                "state": parts[1],
                "recv_q": parts[2],
                "send_q": parts[3],
                "local_address": parts[4],
                "peer_address": parts[5] if len(parts) > 5 else "",
            })

    return {"success": True, "connections": connections}


async def get_dns_config() -> Dict[str, Any]:
    """Get DNS configuration info.

    Returns:
        Dict with 'success' and DNS server list.
    """
    # Try systemd-resolve first
    result = await _run_command("resolvectl", "status")
    if result["success"]:
        dns_servers: List[str] = []
        for line in result["stdout"].splitlines():
            if "DNS Servers" in line or "DNS Server" in line:
                _, _, value = line.partition(":")
                server = value.strip()
                if server:
                    dns_servers.append(server)
        return {"success": True, "dns_servers": dns_servers, "source": "systemd-resolved"}

    # Fallback to /etc/resolv.conf
    result = await _run_command("cat", "/etc/resolv.conf")
    if result["success"]:
        dns_servers = []
        for line in result["stdout"].splitlines():
            line = line.strip()
            if line.startswith("nameserver"):
                parts = line.split()
                if len(parts) >= 2:
                    dns_servers.append(parts[1])
        return {"success": True, "dns_servers": dns_servers, "source": "resolv.conf"}

    return {"success": False, "error": "Unable to read DNS configuration", "dns_servers": []}


async def get_firewall_rules() -> Dict[str, Any]:
    """List firewall rules (ufw or iptables).

    Returns:
        Dict with 'success', 'backend' (ufw/iptables), and 'rules' list.
    """
    # Try ufw first
    result = await _run_command("ufw", "status", "numbered")
    if result["success"]:
        rules: List[Dict[str, str]] = []
        for line in result["stdout"].splitlines():
            line = line.strip()
            if line and line[0] == "[":
                # Parse numbered rule like: [ 1] 22/tcp ALLOW IN Anywhere
                parts = line.split("]", 1)
                if len(parts) == 2:
                    rules.append({
                        "number": parts[0].strip("[ "),
                        "rule": parts[1].strip(),
                    })
        status_line = result["stdout"].splitlines()[0] if result["stdout"] else ""
        return {
            "success": True,
            "backend": "ufw",
            "status": status_line,
            "rules": rules,
        }

    # Fallback to iptables
    result = await _run_command("iptables", "-L", "-n", "--line-numbers")
    if result["success"]:
        rules = []
        current_chain = ""
        for line in result["stdout"].splitlines():
            if line.startswith("Chain"):
                current_chain = line.split()[1] if len(line.split()) > 1 else ""
            elif line and line[0].isdigit():
                rules.append({
                    "chain": current_chain,
                    "rule": line,
                })
        return {"success": True, "backend": "iptables", "rules": rules}

    return {
        "success": False,
        "error": "Neither ufw nor iptables available",
        "backend": None,
        "rules": [],
    }
