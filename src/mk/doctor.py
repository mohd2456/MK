"""MK Doctor — pre-flight system readiness check.

Runs a comprehensive battery of checks across every MK subsystem and produces
a clear green/red readout with actionable fix suggestions. Unlike the boot
sequence (which is fast and optimistic), the doctor is *thorough* — it verifies
connectivity, permissions, tool availability, model serving, and configuration
completeness so you know exactly what's ready and what isn't before relying on
MK for real operations.

Usage:
    mk-doctor              # full check, human-readable
    mk-doctor --json       # machine-readable output (for CI / scripting)
    mk-doctor --fix        # attempt to fix what it can (mkdir, chmod, etc.)
"""

from __future__ import annotations

import asyncio
import json as json_module
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rich.console import Console

console = Console()


# ─── Data Model ───────────────────────────────────────────────────────────────


@dataclass
class Check:
    """Result of a single doctor check."""

    name: str
    category: str  # system, storage, containers, network, ai, security
    status: str = "skip"  # pass, warn, fail, skip
    detail: str = ""
    fix: str = ""  # actionable fix suggestion (empty if passing)

    @property
    def passed(self) -> bool:
        return self.status == "pass"


@dataclass
class DoctorReport:
    """Complete doctor report."""

    checks: List[Check] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.status == "pass")

    @property
    def warnings(self) -> int:
        return sum(1 for c in self.checks if c.status == "warn")

    @property
    def failures(self) -> int:
        return sum(1 for c in self.checks if c.status == "fail")

    @property
    def healthy(self) -> bool:
        return self.failures == 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "healthy": self.healthy,
            "passed": self.passed,
            "warnings": self.warnings,
            "failures": self.failures,
            "checks": [
                {
                    "name": c.name,
                    "category": c.category,
                    "status": c.status,
                    "detail": c.detail,
                    "fix": c.fix,
                }
                for c in self.checks
            ],
        }


# ─── Helpers ──────────────────────────────────────────────────────────────────


async def _run(cmd: str, timeout: float = 10.0) -> Tuple[int, str]:
    """Run a command, returning (returncode, stdout)."""
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


def _which(name: str) -> Optional[str]:
    """Check if a binary is on PATH."""
    return shutil.which(name)


# ─── Checks ───────────────────────────────────────────────────────────────────


async def check_python_version() -> Check:
    c = Check("Python version", "system")
    v = sys.version_info
    if v >= (3, 10):
        c.status = "pass"
        c.detail = f"{v.major}.{v.minor}.{v.micro}"
    else:
        c.status = "fail"
        c.detail = f"{v.major}.{v.minor} (need >=3.10)"
        c.fix = "Install Python 3.10+ (pyenv install 3.12)"
    return c


async def check_disk_space() -> Check:
    c = Check("Disk space (root)", "system")
    try:
        st = os.statvfs("/")
        free_gb = (st.f_frsize * st.f_bavail) / (1024**3)
        total_gb = (st.f_frsize * st.f_blocks) / (1024**3)
        pct = ((total_gb - free_gb) / total_gb) * 100 if total_gb > 0 else 0
        c.detail = f"{free_gb:.1f}GB free ({pct:.0f}% used)"
        if pct > 95:
            c.status = "fail"
            c.fix = "Free disk space (< 5% remaining)"
        elif pct > 85:
            c.status = "warn"
            c.fix = "Consider freeing space (> 85% used)"
        else:
            c.status = "pass"
    except OSError:
        c.status = "warn"
        c.detail = "Could not check disk"
    return c


async def check_ram() -> Check:
    c = Check("RAM available", "system")
    try:
        meminfo = Path("/proc/meminfo").read_text()
        total_kb = 0
        avail_kb = 0
        for line in meminfo.splitlines():
            if line.startswith("MemTotal:"):
                total_kb = int(line.split()[1])
            elif line.startswith("MemAvailable:"):
                avail_kb = int(line.split()[1])
        total_gb = total_kb / (1024 * 1024)
        avail_gb = avail_kb / (1024 * 1024)
        c.detail = f"{avail_gb:.1f}GB available / {total_gb:.1f}GB total"
        if total_gb < 4:
            c.status = "warn"
            c.fix = "MK + local brain needs ~4GB minimum; consider more RAM"
        else:
            c.status = "pass"
    except (OSError, ValueError):
        c.status = "skip"
        c.detail = "Cannot read /proc/meminfo"
    return c


async def check_docker() -> Check:
    c = Check("Docker", "containers")
    if not _which("docker"):
        c.status = "fail"
        c.detail = "docker not found"
        c.fix = (
            "Install Docker: sudo apt install docker.io (Debian) or sudo dnf install docker (RHEL)"
        )
        return c
    rc, out = await _run("docker info --format '{{.ServerVersion}}' 2>/dev/null")
    if rc != 0:
        c.status = "fail"
        c.detail = "Docker installed but daemon not reachable"
        c.fix = "Start Docker: sudo systemctl start docker"
        return c
    c.status = "pass"
    c.detail = f"v{out}"
    return c


async def check_zfs() -> Check:
    c = Check("ZFS tools", "storage")
    if not _which("zpool"):
        c.status = "warn"
        c.detail = "zpool not found (ZFS features disabled)"
        c.fix = "Install ZFS: sudo apt install zfsutils-linux (Debian)"
        return c
    rc, out = await _run("zpool list -H -o name 2>/dev/null")
    if rc != 0:
        c.status = "warn"
        c.detail = "ZFS tools installed but no pools imported"
        c.fix = "Import pools: sudo zpool import -a"
    else:
        pools = [p for p in out.splitlines() if p.strip()]
        c.status = "pass"
        c.detail = f"{len(pools)} pool(s): {', '.join(pools)}" if pools else "No pools"
    return c


async def check_network_connectivity() -> Check:
    c = Check("Internet connectivity", "network")
    rc, _ = await _run("ping -c 1 -W 3 1.1.1.1 2>/dev/null")
    if rc == 0:
        c.status = "pass"
        c.detail = "Reachable (1.1.1.1)"
    else:
        rc2, _ = await _run("ping -c 1 -W 3 8.8.8.8 2>/dev/null")
        if rc2 == 0:
            c.status = "pass"
            c.detail = "Reachable (8.8.8.8)"
        else:
            c.status = "warn"
            c.detail = "No internet (cloud LLM providers won't work)"
            c.fix = "Check network config; local-brain-only mode still works"
    return c


async def check_local_brain() -> Check:
    c = Check("Local brain (LLM server)", "ai")
    url = os.environ.get("MK_LOCAL_BRAIN_URL")
    if not url:
        c.status = "skip"
        c.detail = "MK_LOCAL_BRAIN_URL not set (optional)"
        c.fix = "Set MK_LOCAL_BRAIN_URL=http://localhost:8080/v1 to enable local inference"
        return c
    # Try to reach the server
    import urllib.parse

    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 8080
    rc, out = await _run(
        f"curl -s -m 5 -o /dev/null -w '%{{http_code}}' http://{host}:{port}/v1/models 2>/dev/null"
    )
    if rc == 0 and out.strip("'") in ("200", "404"):
        c.status = "pass"
        c.detail = f"Responding at {url}"
    else:
        c.status = "fail"
        c.detail = f"Not reachable at {url}"
        c.fix = (
            f"Start your local model server: llama-server -m model.gguf --host {host} --port {port}"
        )
    return c


async def check_ollama() -> Check:
    c = Check("Ollama", "ai")
    if not _which("ollama"):
        c.status = "skip"
        c.detail = "Not installed (optional)"
        return c
    rc, out = await _run("curl -s -m 5 http://localhost:11434/api/tags 2>/dev/null")
    if rc == 0 and out:
        try:
            data = json_module.loads(out)
            models = [m.get("name", "") for m in data.get("models", [])]
            c.status = "pass"
            c.detail = (
                f"{len(models)} model(s): {', '.join(models[:3])}"
                if models
                else "Running, no models pulled"
            )
        except (json_module.JSONDecodeError, TypeError):
            c.status = "pass"
            c.detail = "Responding"
    else:
        c.status = "warn"
        c.detail = "Installed but not responding"
        c.fix = "Start Ollama: ollama serve"
    return c


async def check_llm_keys() -> Check:
    c = Check("LLM API keys", "ai")
    from mk.llm.keys import KeyManager

    km = KeyManager()
    total = km.total_keys()
    active = km.get_active_providers()
    has_local = bool(os.environ.get("MK_LOCAL_BRAIN_URL"))
    if total > 0:
        c.status = "pass"
        c.detail = f"{total} key(s) for {', '.join(active)}"
    elif has_local:
        c.status = "pass"
        c.detail = "No cloud keys (local brain configured)"
    else:
        c.status = "warn"
        c.detail = "No API keys and no local brain"
        c.fix = "Add a key: /setkey your-api-key (from Telegram) or edit /etc/mk/config.yaml"
    return c


async def check_config() -> Check:
    c = Check("MK configuration", "system")
    paths_to_check = [
        Path("/etc/mk/config.yaml"),
        Path.home() / ".mk" / "config.yaml",
        Path("config.yaml"),
    ]
    found = None
    for p in paths_to_check:
        if p.exists():
            found = p
            break
    if found:
        c.status = "pass"
        c.detail = str(found)
    else:
        c.status = "warn"
        c.detail = "No config file found (using defaults)"
        c.fix = "Copy config.example.yaml to /etc/mk/config.yaml and customize"
    return c


async def check_permissions() -> Check:
    c = Check("MK data directories", "security")
    dirs = [
        Path(os.environ.get("MK_DATA", "/var/lib/mk")),
        Path(os.environ.get("MK_LOG", "/var/log/mk")),
        Path.home() / ".mk",
    ]
    issues: List[str] = []
    for d in dirs:
        if d.exists() and not os.access(d, os.W_OK):
            issues.append(f"{d} not writable")
    if issues:
        c.status = "fail"
        c.detail = "; ".join(issues)
        c.fix = f"Fix permissions: sudo chown -R $(whoami) {' '.join(str(d) for d in dirs)}"
    else:
        c.status = "pass"
        c.detail = "All data dirs accessible"
    return c


async def check_systemd_services() -> Check:
    c = Check("MK systemd services", "system")
    rc, _ = await _run("systemctl is-active mk.service 2>/dev/null")
    mk_active = rc == 0
    rc2, _ = await _run("systemctl is-active mk-web.service 2>/dev/null")
    web_active = rc2 == 0
    # Check if units are even installed
    rc3, _ = await _run("systemctl cat mk.service 2>/dev/null")
    mk_installed = rc3 == 0

    if not mk_installed:
        c.status = "skip"
        c.detail = "MK services not installed (running manually)"
        return c
    parts = []
    if mk_active:
        parts.append("mk: active")
    else:
        parts.append("mk: inactive")
    if web_active:
        parts.append("mk-web: active")
    else:
        parts.append("mk-web: inactive")
    c.status = "pass" if mk_active else "warn"
    c.detail = ", ".join(parts)
    if not mk_active:
        c.fix = "Start MK: sudo systemctl start mk"
    return c


async def check_makemkv() -> Check:
    c = Check("MakeMKV (disc ripper)", "system")
    if _which("makemkvcon"):
        c.status = "pass"
        c.detail = "Installed"
    else:
        c.status = "skip"
        c.detail = "Not installed (optional, for disc ripping)"
    return c


async def check_tailscale() -> Check:
    c = Check("Tailscale VPN", "network")
    if not _which("tailscale"):
        c.status = "skip"
        c.detail = "Not installed (optional)"
        return c
    rc, out = await _run("tailscale status --json 2>/dev/null | head -c 200")
    if rc == 0 and out:
        try:
            json_module.loads(out + "}")  # partial JSON — just confirms it's responding
        except Exception:
            pass
        c.status = "pass"
        c.detail = "Connected"
    else:
        c.status = "warn"
        c.detail = "Installed but not connected"
        c.fix = "Connect: sudo tailscale up"
    return c


async def check_rsync() -> Check:
    c = Check("rsync", "storage")
    if _which("rsync"):
        c.status = "pass"
        c.detail = "Available"
    else:
        c.status = "warn"
        c.detail = "Not installed (rsync backups won't work)"
        c.fix = "Install: sudo apt install rsync"
    return c


async def check_web_ui_build() -> Check:
    c = Check("Web UI build", "system")
    # Check common locations for the built webui
    candidates = [
        Path("/opt/mk/webui/dist/index.html"),
        Path.cwd() / "webui" / "dist" / "index.html",
        Path(__file__).parent.parent.parent / "webui" / "dist" / "index.html",
    ]
    for p in candidates:
        if p.exists():
            c.status = "pass"
            c.detail = str(p.parent)
            return c
    c.status = "warn"
    c.detail = "No built webui found"
    c.fix = "Build: cd webui && pnpm install && pnpm build"
    return c


# ─── Runner ───────────────────────────────────────────────────────────────────


ALL_CHECKS = [
    check_python_version,
    check_disk_space,
    check_ram,
    check_config,
    check_permissions,
    check_systemd_services,
    check_web_ui_build,
    check_makemkv,
    check_docker,
    check_zfs,
    check_rsync,
    check_network_connectivity,
    check_tailscale,
    check_local_brain,
    check_ollama,
    check_llm_keys,
]


async def run_doctor(fix: bool = False) -> DoctorReport:
    """Run all doctor checks and return a report.

    Args:
        fix: If True, attempt to auto-fix simple issues (mkdir, etc.). Currently
             reserved for future use.

    Returns:
        DoctorReport with all check results.
    """
    report = DoctorReport()
    for check_fn in ALL_CHECKS:
        try:
            result = await check_fn()
            report.checks.append(result)
        except Exception as exc:
            report.checks.append(
                Check(
                    name=check_fn.__name__.replace("check_", "").replace("_", " ").title(),
                    category="system",
                    status="fail",
                    detail=f"Check crashed: {exc}",
                )
            )
    return report


# ─── Display ──────────────────────────────────────────────────────────────────

_STATUS_ICON = {
    "pass": "[bold green]✓[/bold green]",
    "warn": "[bold yellow]⚠[/bold yellow]",
    "fail": "[bold red]✗[/bold red]",
    "skip": "[dim]○[/dim]",
}


def print_report(report: DoctorReport) -> None:
    """Print a human-readable doctor report."""
    console.print()
    console.print("[bold cyan]  MK Doctor — System Readiness Check[/bold cyan]")
    console.print("  [dim]─────────────────────────────────────────[/dim]")
    console.print()

    # Group by category
    categories = {}
    for check in report.checks:
        categories.setdefault(check.category, []).append(check)

    category_order = ["system", "storage", "containers", "network", "ai", "security"]
    for cat in category_order:
        checks = categories.get(cat, [])
        if not checks:
            continue
        console.print(f"  [bold]{cat.title()}[/bold]")
        for check in checks:
            icon = _STATUS_ICON.get(check.status, "?")
            detail = f" [dim]— {check.detail}[/dim]" if check.detail else ""
            console.print(f"    {icon} {check.name}{detail}")
            if check.fix and check.status in ("fail", "warn"):
                console.print(f"      [dim yellow]→ {check.fix}[/dim yellow]")
        console.print()

    # Summary
    console.print("  [dim]─────────────────────────────────────────[/dim]")
    total = len(report.checks)
    if report.healthy:
        console.print(
            f"  [bold green]All clear[/bold green] — {report.passed}/{total} passed, "
            f"{report.warnings} warning(s)"
        )
    else:
        console.print(
            f"  [bold red]{report.failures} issue(s) to fix[/bold red] — "
            f"{report.passed}/{total} passed, {report.warnings} warning(s)"
        )
    console.print()


# ─── CLI Entry Point ──────────────────────────────────────────────────────────


def cli_entry() -> None:
    """CLI entry point for the 'mk-doctor' command."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="mk-doctor",
        description="MK Doctor — check system readiness for MK OS",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Attempt to auto-fix simple issues (reserved for future use)",
    )
    args = parser.parse_args()

    report = asyncio.run(run_doctor(fix=args.fix))

    if args.json:
        print(json_module.dumps(report.to_dict(), indent=2))
    else:
        print_report(report)

    # Exit code: 0 if healthy, 1 if failures
    sys.exit(0 if report.healthy else 1)


if __name__ == "__main__":
    cli_entry()
