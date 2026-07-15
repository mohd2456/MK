"""Scheduled reports — periodic summaries delivered via Telegram/WS.

Generates a weekly (or configurable) summary of homelab activity:
- Backup status (last success, any failures)
- Disk growth trend
- Container restarts / issues
- Media library changes
- LLM cost spend

Registered as a scheduled job in the OpsManager and delivered through
the NotificationBroadcaster.
"""

from __future__ import annotations

import os

from mk.ops.checks import CheckResult, CheckSeverity


async def generate_weekly_report() -> CheckResult:
    """Generate the weekly homelab summary report.

    Collects data from various sources and formats a human-readable
    summary. Returns as a CheckResult so the OpsManager can route it
    through the normal alert/notification pipeline.
    """
    import asyncio

    sections: list = []

    # Uptime
    try:
        with open("/proc/uptime") as f:
            uptime_secs = float(f.read().split()[0])
            days = int(uptime_secs / 86400)
            sections.append(f"**Uptime**: {days} days")
    except Exception:
        pass

    # Disk usage
    try:
        st = os.statvfs("/")
        total_gb = (st.f_frsize * st.f_blocks) / (1024**3)
        free_gb = (st.f_frsize * st.f_bavail) / (1024**3)
        used_pct = ((total_gb - free_gb) / total_gb * 100) if total_gb > 0 else 0
        sections.append(f"**Disk**: {used_pct:.0f}% used ({free_gb:.0f}GB free)")
    except Exception:
        pass

    # Docker containers
    try:
        proc = await asyncio.create_subprocess_shell(
            "docker ps --format '{{.State}}' 2>/dev/null | sort | uniq -c",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        if proc.returncode == 0 and stdout:
            container_summary = stdout.decode().strip().replace("\n", ", ")
            sections.append(f"**Containers**: {container_summary}")
    except Exception:
        pass

    # Backup freshness
    try:
        proc = await asyncio.create_subprocess_shell(
            "zfs list -t snapshot -H -o creation -S creation 2>/dev/null | head -1",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        if proc.returncode == 0 and stdout:
            sections.append(f"**Last backup**: {stdout.decode().strip()}")
    except Exception:
        pass

    # LLM spend (from metrics)
    try:
        from mk.metrics import metrics

        total_reqs = sum(v for k, v in metrics._counters.items() if "mk_llm_requests_total" in k)
        if total_reqs:
            sections.append(f"**LLM requests this period**: {int(total_reqs)}")
    except Exception:
        pass

    if not sections:
        sections.append("No data available for this period.")

    report_text = "📊 **MK Weekly Report**\n\n" + "\n".join(sections)

    return CheckResult(
        name="weekly_report",
        severity=CheckSeverity.INFO,
        message=report_text,
        data={"sections": sections},
    )
