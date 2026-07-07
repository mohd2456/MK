"""MK OS Boot Sequence.

The boot sequence:
1. Kernel loads (handled by systemd)
2. MK service starts, this module runs
3. System probe (hardware, network, storage)
4. Service discovery (what's running, what failed)
5. AI initialization (LLM provider check, memory load)
6. Ready state, accepting input
"""

from __future__ import annotations

import asyncio
import os
import platform
import shlex
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

from mk.config.settings import Settings, load_config

console = Console()


# Boot Phases


class BootPhase:
    """A single phase of the boot sequence."""

    def __init__(self, name: str, description: str) -> None:
        self.name = name
        self.description = description
        self.status: str = "pending"  # pending, running, ok, warn, fail
        self.detail: str = ""
        self.duration_ms: float = 0

    def ok(self, detail: str = "") -> None:
        self.status = "ok"
        self.detail = detail

    def warn(self, detail: str = "") -> None:
        self.status = "warn"
        self.detail = detail

    def fail(self, detail: str = "") -> None:
        self.status = "fail"
        self.detail = detail


# Boot Display


def _status_icon(status: str) -> str:
    """Get the status icon for a boot phase."""
    icons = {
        "ok": "[bold green]✓[/bold green]",
        "warn": "[bold yellow]⚠[/bold yellow]",
        "fail": "[bold red]✗[/bold red]",
        "running": "[bold blue]●[/bold blue]",
        "pending": "[dim]○[/dim]",
    }
    return icons.get(status, "?")


def _print_phase_result(phase: BootPhase) -> None:
    """Print a boot phase result line."""
    icon = _status_icon(phase.status)
    timing = f"[dim]{phase.duration_ms:.0f}ms[/dim]" if phase.duration_ms > 0 else ""
    detail = f" [dim]({phase.detail})[/dim]" if phase.detail else ""
    console.print(f"  {icon} {phase.description}{detail} {timing}")


def print_boot_header() -> None:
    """Print the MK OS boot header — first thing you see."""
    console.print()
    console.print("[bold cyan]  ███╗   ███╗██╗  ██╗[/bold cyan]")
    console.print("[bold cyan]  ████╗ ████║██║ ██╔╝[/bold cyan]")
    console.print("[bold cyan]  ██╔████╔██║█████╔╝ [/bold cyan]")
    console.print("[bold cyan]  ██║╚██╔╝██║██╔═██╗ [/bold cyan]")
    console.print("[bold cyan]  ██║ ╚═╝ ██║██║  ██╗[/bold cyan]")
    console.print("[bold cyan]  ╚═╝     ╚═╝╚═╝  ╚═╝[/bold cyan]")
    console.print()
    console.print("  [bold]MK OS[/bold] [dim]v0.1.0[/dim]")
    console.print("  [dim]Personal AI Operating System[/dim]")
    console.print()
    console.print("  [dim]─────────────────────────────────────────[/dim]")
    console.print()


def print_boot_complete(total_time_ms: float, warnings: int, failures: int) -> None:
    """Print the boot complete summary."""
    console.print()
    console.print("  [dim]─────────────────────────────────────────[/dim]")
    console.print()

    if failures > 0:
        status_line = f"  [bold red]Boot completed with {failures} error(s)[/bold red]"
    elif warnings > 0:
        status_line = f"  [bold yellow]Boot completed with {warnings} warning(s)[/bold yellow]"
    else:
        status_line = "  [bold green]All systems online[/bold green]"

    console.print(status_line)
    console.print(f"  [dim]Boot time: {total_time_ms:.0f}ms | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/dim]")
    console.print()
    console.print("  [bold cyan]MK is ready. Just talk.[/bold cyan]")
    console.print()


# Boot Probes


async def _run_cmd(cmd: str) -> Tuple[int, str]:
    """Quick async command execution for boot probes."""
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        return proc.returncode or 0, stdout.decode().strip()
    except (asyncio.TimeoutError, OSError):
        return 1, ""


async def probe_hardware() -> BootPhase:
    """Probe system hardware — CPU, RAM, architecture."""
    phase = BootPhase("hardware", "Hardware")
    start = time.time()

    cpu_count = os.cpu_count() or 0
    arch = platform.machine()

    # Get RAM
    rc, out = await _run_cmd("free -b | awk '/Mem:/{print $2}'")
    if rc == 0 and out:
        ram_gb = int(out) / (1024**3)
        ram_str = f"{ram_gb:.1f}GB RAM"
    else:
        ram_str = "RAM unknown"

    # Get CPU model (short)
    rc, cpu_model = await _run_cmd(
        "lscpu | grep 'Model name' | cut -d: -f2 | xargs | cut -d' ' -f1-3"
    )
    if not cpu_model:
        cpu_model = arch

    phase.ok(f"{cpu_model}, {cpu_count} cores, {ram_str}")
    phase.duration_ms = (time.time() - start) * 1000
    return phase


async def probe_network() -> BootPhase:
    """Probe network connectivity."""
    phase = BootPhase("network", "Network")
    start = time.time()

    # Check interfaces
    rc, out = await _run_cmd("ip -4 addr show | grep -oP '(?<=inet\\s)\\d+(\\.\\d+){3}/\\d+' | grep -v '127.0.0'")
    ips = [ip.strip() for ip in out.splitlines() if ip.strip()] if rc == 0 else []

    if not ips:
        phase.warn("No network interfaces with IP")
        phase.duration_ms = (time.time() - start) * 1000
        return phase

    # Quick connectivity check
    rc, _ = await _run_cmd("ping -c 1 -W 2 1.1.1.1")
    if rc == 0:
        phase.ok(f"{ips[0]} | internet reachable")
    else:
        phase.warn(f"{ips[0]} | no internet")

    phase.duration_ms = (time.time() - start) * 1000
    return phase


async def probe_storage() -> BootPhase:
    """Probe storage — ZFS pools and disk usage."""
    phase = BootPhase("storage", "Storage")
    start = time.time()

    # Check for ZFS
    rc, out = await _run_cmd("zpool list -H -o name,health 2>/dev/null")
    if rc == 0 and out:
        pools = []
        degraded = False
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                name, health = parts[0], parts[1]
                pools.append(name)
                if health.upper() != "ONLINE":
                    degraded = True

        if degraded:
            phase.warn(f"ZFS: {', '.join(pools)} (DEGRADED)")
        else:
            phase.ok(f"ZFS: {', '.join(pools)} online")
    else:
        # No ZFS — just check disk space
        rc, out = await _run_cmd("df -h / | awk 'NR==2{print $4, $5}'")
        if rc == 0 and out:
            parts = out.split()
            free = parts[0] if parts else "?"
            used_pct = parts[1] if len(parts) > 1 else "?"
            used_num = int(used_pct.rstrip("%")) if used_pct.rstrip("%").isdigit() else 0
            if used_num > 90:
                phase.warn(f"Root: {used_pct} used ({free} free)")
            else:
                phase.ok(f"Root: {used_pct} used ({free} free)")
        else:
            phase.ok("Disk available")

    phase.duration_ms = (time.time() - start) * 1000
    return phase


async def probe_docker() -> BootPhase:
    """Probe Docker container runtime."""
    phase = BootPhase("docker", "Containers")
    start = time.time()

    rc, out = await _run_cmd("docker ps --format '{{.State}}' 2>/dev/null | sort | uniq -c")
    if rc != 0:
        phase.warn("Docker not available")
        phase.duration_ms = (time.time() - start) * 1000
        return phase

    if not out.strip():
        phase.ok("Docker ready, no containers")
    else:
        # Parse container states
        running = 0
        total = 0
        for line in out.splitlines():
            parts = line.strip().split()
            if len(parts) >= 2:
                count = int(parts[0])
                state = parts[1]
                total += count
                if state == "running":
                    running = count

        if running == total:
            phase.ok(f"{running} containers running")
        else:
            phase.warn(f"{running}/{total} containers running")

    phase.duration_ms = (time.time() - start) * 1000
    return phase


async def probe_services() -> BootPhase:
    """Probe systemd services for failures."""
    phase = BootPhase("services", "Services")
    start = time.time()

    rc, out = await _run_cmd(
        "systemctl list-units --state=failed --no-pager --no-legend 2>/dev/null | wc -l"
    )
    if rc != 0:
        phase.ok("systemd available")
        phase.duration_ms = (time.time() - start) * 1000
        return phase

    failed_count = int(out.strip()) if out.strip().isdigit() else 0
    if failed_count > 0:
        # Get which ones failed
        rc, failed_names = await _run_cmd(
            "systemctl list-units --state=failed --no-pager --no-legend 2>/dev/null | "
            "awk '{print $2}' | head -3"
        )
        names = failed_names.replace("\n", ", ") if failed_names else ""
        phase.warn(f"{failed_count} failed: {names}")
    else:
        phase.ok("All services healthy")

    phase.duration_ms = (time.time() - start) * 1000
    return phase


async def probe_config(config_path: Optional[str] = None) -> Tuple[BootPhase, Optional[Settings]]:
    """Load and validate MK configuration."""
    phase = BootPhase("config", "Configuration")
    start = time.time()

    try:
        settings = load_config(config_path)
        providers = len(settings.llm_providers)
        machines = len(settings.machines)

        if providers == 0:
            phase.warn("No LLM providers configured")
        else:
            detail_parts = [f"{providers} LLM provider{'s' if providers > 1 else ''}"]
            if machines > 0:
                detail_parts.append(f"{machines} machine{'s' if machines > 1 else ''}")
            phase.ok(", ".join(detail_parts))

        phase.duration_ms = (time.time() - start) * 1000
        return phase, settings
    except Exception as e:
        phase.fail(f"Config error: {str(e)[:50]}")
        phase.duration_ms = (time.time() - start) * 1000
        return phase, None


async def probe_ai(settings: Optional[Settings]) -> BootPhase:
    """Probe AI/LLM readiness."""
    phase = BootPhase("ai", "AI Engine")
    start = time.time()

    if not settings or not settings.llm_providers:
        phase.warn("No LLM providers — local mode only")
        phase.duration_ms = (time.time() - start) * 1000
        return phase

    # Check if we can reach the primary provider (just DNS, don't call the API)
    primary = settings.active_providers[0] if settings.active_providers else None
    if primary:
        # Just verify the endpoint is resolvable
        from urllib.parse import urlparse
        parsed = urlparse(primary.endpoint)
        host = parsed.hostname or ""
        rc, _ = await _run_cmd(f"getent hosts {shlex.quote(host)} 2>/dev/null")
        if rc == 0:
            phase.ok(f"{primary.name}/{primary.model}")
        else:
            phase.warn(f"{primary.name} (endpoint unreachable)")
    else:
        phase.warn("No active provider")

    phase.duration_ms = (time.time() - start) * 1000
    return phase


async def probe_memory() -> BootPhase:
    """Probe MK's memory system — long-term memory availability."""
    phase = BootPhase("memory", "Memory")
    start = time.time()

    # Check memory path: MK_DATA env → /var/lib/mk/memory → ~/.mk/memory
    mk_data = os.environ.get("MK_DATA")
    if mk_data:
        memory_path = Path(mk_data) / "memory"
    elif Path("/var/lib/mk/memory").exists():
        memory_path = Path("/var/lib/mk/memory")
    else:
        memory_path = Path.home() / ".mk" / "memory"

    if memory_path.exists():
        # Count memory files
        files = list(memory_path.glob("**/*.json"))
        phase.ok(f"{len(files)} memories loaded")
    else:
        phase.ok("Fresh start (no memories)")

    phase.duration_ms = (time.time() - start) * 1000
    return phase


async def probe_gateway() -> BootPhase:
    """Probe the Telegram gateway status."""
    phase = BootPhase("gateway", "Gateway")
    start = time.time()

    # Check if gateway process is running
    rc, out = await _run_cmd("pgrep -f 'mk.*gateway\\|telegram.*bridge' 2>/dev/null")
    if rc == 0 and out:
        phase.ok("Telegram bridge active")
    else:
        # Check if it should be running — check MK_HOME env, then /opt/mk/gateway
        mk_home = os.environ.get("MK_HOME", "/opt/mk")
        gateway_dir = Path(mk_home) / "gateway"
        if not gateway_dir.exists():
            gateway_dir = Path("/opt/mk/gateway")

        if gateway_dir.exists():
            phase.warn("Gateway installed but not running")
        else:
            phase.ok("No gateway configured")

    phase.duration_ms = (time.time() - start) * 1000
    return phase


# Main Boot Sequence


async def boot_sequence(
    config_path: Optional[str] = None,
    quiet: bool = False,
    mode: str = "terminal",
) -> Tuple[Optional[Settings], Dict[str, Any]]:
    """Execute the full MK OS boot sequence.

    This is what runs when MK powers on. It probes all subsystems,
    reports their status, and returns the validated settings.

    Args:
        config_path: Path to config file.
        quiet: If True, suppress output (for daemon mode).
        mode: Boot mode (terminal, daemon).

    Returns:
        Tuple of (Settings or None, boot_info dict with phase results).
    """
    boot_start = time.time()

    if not quiet:
        print_boot_header()

    # Phase 1: System Probe
    if not quiet:
        console.print("  [bold]System Probe[/bold]")

    hw_phase = await probe_hardware()
    net_phase = await probe_network()
    storage_phase = await probe_storage()

    if not quiet:
        _print_phase_result(hw_phase)
        _print_phase_result(net_phase)
        _print_phase_result(storage_phase)
        console.print()

    # Phase 2: Services
    if not quiet:
        console.print("  [bold]Services[/bold]")

    docker_phase = await probe_docker()
    services_phase = await probe_services()
    gateway_phase = await probe_gateway()

    if not quiet:
        _print_phase_result(docker_phase)
        _print_phase_result(services_phase)
        _print_phase_result(gateway_phase)
        console.print()

    # Phase 3: AI Initialization
    if not quiet:
        console.print("  [bold]AI Engine[/bold]")

    config_phase, settings = await probe_config(config_path)
    ai_phase = await probe_ai(settings)
    memory_phase = await probe_memory()

    if not quiet:
        _print_phase_result(config_phase)
        _print_phase_result(ai_phase)
        _print_phase_result(memory_phase)

    # Boot Summary
    all_phases = [
        hw_phase, net_phase, storage_phase,
        docker_phase, services_phase, gateway_phase,
        config_phase, ai_phase, memory_phase,
    ]

    warnings = sum(1 for p in all_phases if p.status == "warn")
    failures = sum(1 for p in all_phases if p.status == "fail")
    total_time_ms = (time.time() - boot_start) * 1000

    if not quiet:
        print_boot_complete(total_time_ms, warnings, failures)

    # Build boot info for the engine
    boot_info = {
        "boot_time_ms": total_time_ms,
        "mode": mode,
        "warnings": warnings,
        "failures": failures,
        "phases": {p.name: {"status": p.status, "detail": p.detail} for p in all_phases},
        "timestamp": datetime.now().isoformat(),
    }

    return settings, boot_info


# Entry Point


def run_boot(config_path: Optional[str] = None, mode: str = "terminal") -> Tuple[Optional[Settings], Dict[str, Any]]:
    """Synchronous wrapper for the boot sequence.

    Args:
        config_path: Config file path.
        mode: Boot mode.

    Returns:
        Tuple of (Settings, boot_info).
    """
    return asyncio.run(boot_sequence(config_path=config_path, mode=mode))
