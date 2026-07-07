"""Built-in health checks for proactive monitoring.

Each check is an async function that inspects some aspect of the
system and returns a CheckResult. Checks are designed to be:
- Self-contained: Each check runs independently
- Lightweight: Quick to execute, no heavy computation
- Actionable: Results include what's wrong AND what to do about it

Built-in checks:
- container_health: Docker container status and restart counts
- disk_prediction: Usage trend analysis with fill-date estimation
- backup_freshness: How old are the latest backups
- cert_expiry: TLS certificate expiration dates
- cost_tracking: LLM API spend summarization
- service_health: HTTP endpoint availability
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional


class CheckSeverity(str, Enum):
    """Severity of a check result.

    Determines how the alert manager routes the notification.
    """

    OK = "ok"               # Everything fine, no action needed
    INFO = "info"           # Informational, log only
    WARNING = "warning"     # Something needs attention soon
    CRITICAL = "critical"   # Immediate action required
    UNKNOWN = "unknown"     # Check couldn't determine state


@dataclass
class CheckResult:
    """Result of a health check execution.

    Contains the severity, a human-readable message, structured
    data for programmatic consumption, and optional recommendations.
    """

    name: str
    severity: CheckSeverity
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    @property
    def is_ok(self) -> bool:
        """Whether the check passed."""
        return self.severity in (CheckSeverity.OK, CheckSeverity.INFO)

    @property
    def needs_alert(self) -> bool:
        """Whether this result should trigger an alert."""
        return self.severity in (CheckSeverity.WARNING, CheckSeverity.CRITICAL)

    def format(self) -> str:
        """Format the result for display."""
        icon = {
            CheckSeverity.OK: "✓",
            CheckSeverity.INFO: "ℹ",
            CheckSeverity.WARNING: "⚠",
            CheckSeverity.CRITICAL: "🔴",
            CheckSeverity.UNKNOWN: "?",
        }[self.severity]

        lines = [f"{icon} [{self.name}] {self.message}"]
        if self.recommendations:
            for rec in self.recommendations:
                lines.append(f"  → {rec}")
        return "\n".join(lines)


@dataclass
class Check:
    """A registered health check.

    Wraps the check function with metadata and execution tracking.
    """

    name: str
    handler: Callable[..., Coroutine]
    description: str = ""
    category: str = "general"
    last_result: Optional[CheckResult] = None
    last_run: Optional[float] = None
    run_count: int = 0
    failure_count: int = 0

    async def run(self) -> CheckResult:
        """Execute the check and record the result."""
        self.run_count += 1
        self.last_run = time.time()

        try:
            result = await self.handler()
            if not isinstance(result, CheckResult):
                result = CheckResult(
                    name=self.name,
                    severity=CheckSeverity.OK,
                    message=str(result),
                )
            self.last_result = result
            return result
        except Exception as e:
            self.failure_count += 1
            result = CheckResult(
                name=self.name,
                severity=CheckSeverity.UNKNOWN,
                message=f"Check failed: {type(e).__name__}: {e}",
            )
            self.last_result = result
            return result


class CheckRegistry:
    """Registry of all available health checks.

    Manages built-in and custom checks. Provides methods for
    running all checks, filtering by category, and retrieving results.
    """

    def __init__(self) -> None:
        """Initialize with empty registry."""
        self._checks: Dict[str, Check] = {}

    @property
    def check_count(self) -> int:
        """Number of registered checks."""
        return len(self._checks)

    def register(
        self,
        name: str,
        handler: Callable[..., Coroutine],
        description: str = "",
        category: str = "general",
    ) -> Check:
        """Register a health check.

        Args:
            name: Unique check name.
            handler: Async function that returns a CheckResult.
            description: Human-readable description.
            category: Category for grouping (e.g., "containers", "storage").

        Returns:
            The registered Check.
        """
        check = Check(
            name=name,
            handler=handler,
            description=description,
            category=category,
        )
        self._checks[name] = check
        return check

    def get_check(self, name: str) -> Optional[Check]:
        """Get a check by name."""
        return self._checks.get(name)

    def get_checks_by_category(self, category: str) -> List[Check]:
        """Get all checks in a category."""
        return [c for c in self._checks.values() if c.category == category]

    async def run_all(self) -> List[CheckResult]:
        """Run all registered checks.

        Returns:
            List of CheckResult from all checks.
        """
        results: List[CheckResult] = []
        for check in self._checks.values():
            result = await check.run()
            results.append(result)
        return results

    async def run_category(self, category: str) -> List[CheckResult]:
        """Run all checks in a category.

        Args:
            category: Category to run.

        Returns:
            List of CheckResult from matching checks.
        """
        results: List[CheckResult] = []
        for check in self.get_checks_by_category(category):
            result = await check.run()
            results.append(result)
        return results

    def get_all_results(self) -> List[CheckResult]:
        """Get the last result from each check (without re-running)."""
        return [c.last_result for c in self._checks.values() if c.last_result]

    def summary(self) -> str:
        """Get a formatted summary of all check statuses."""
        lines = [f"Health Checks ({self.check_count} registered):"]
        for check in self._checks.values():
            if check.last_result:
                lines.append(f"  {check.last_result.format()}")
            else:
                lines.append(f"  ? [{check.name}] Not yet run")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# Built-in Check Implementations
# ═══════════════════════════════════════════════════════════════


async def container_health() -> CheckResult:
    """Check Docker container health status.

    In production: runs `docker ps --format json` and checks
    for unhealthy, restarting, or exited containers.
    """
    # Simulated — in production this runs actual docker commands
    # via SSH or Docker socket

    # Would parse: docker ps --format '{{.Names}}\t{{.Status}}\t{{.State}}'
    containers = [
        {"name": "plex", "state": "running", "restarts": 0},
        {"name": "sonarr", "state": "running", "restarts": 0},
        {"name": "radarr", "state": "running", "restarts": 0},
        {"name": "transmission", "state": "running", "restarts": 0},
    ]

    unhealthy = [c for c in containers if c["state"] != "running"]
    restarting = [c for c in containers if c["restarts"] > 3]

    if unhealthy:
        names = [c["name"] for c in unhealthy]
        return CheckResult(
            name="container_health",
            severity=CheckSeverity.CRITICAL,
            message=f"Containers down: {', '.join(names)}",
            data={"unhealthy": unhealthy, "total": len(containers)},
            recommendations=[
                f"Check logs: docker logs {names[0]}",
                f"Try restart: docker restart {names[0]}",
            ],
        )

    if restarting:
        names = [c["name"] for c in restarting]
        return CheckResult(
            name="container_health",
            severity=CheckSeverity.WARNING,
            message=f"Containers restart-looping: {', '.join(names)}",
            data={"restarting": restarting, "total": len(containers)},
            recommendations=[
                "Check for OOM kills: dmesg | grep -i oom",
                "Check container logs for crash reason",
            ],
        )

    return CheckResult(
        name="container_health",
        severity=CheckSeverity.OK,
        message=f"All {len(containers)} containers healthy",
        data={"total": len(containers)},
    )


async def disk_prediction() -> CheckResult:
    """Predict when disks will fill up based on usage trends.

    In production: reads `df` output over time, calculates
    growth rate, and estimates days until full.
    """
    # Simulated disk state
    pools = [
        {"name": "/data", "used_pct": 72.5, "growth_gb_per_day": 1.2, "free_gb": 850},
        {"name": "/", "used_pct": 45.0, "growth_gb_per_day": 0.1, "free_gb": 55},
    ]

    warnings = []
    for pool in pools:
        if pool["growth_gb_per_day"] > 0:
            days_until_full = pool["free_gb"] / pool["growth_gb_per_day"]
            pool["days_until_full"] = round(days_until_full, 1)

            if days_until_full < 7:
                warnings.append(pool)
            elif days_until_full < 30:
                warnings.append(pool)

    if any(p.get("days_until_full", 999) < 7 for p in pools):
        critical_pools = [p for p in pools if p.get("days_until_full", 999) < 7]
        return CheckResult(
            name="disk_prediction",
            severity=CheckSeverity.CRITICAL,
            message=f"Disk {critical_pools[0]['name']} fills in {critical_pools[0]['days_until_full']} days!",
            data={"pools": pools},
            recommendations=[
                "Clean old Docker images: docker image prune -a",
                "Check /data/rips/ for unprocessed rips",
                "Run backup cleanup to remove old snapshots",
            ],
        )

    if warnings:
        return CheckResult(
            name="disk_prediction",
            severity=CheckSeverity.WARNING,
            message=f"Disk trending full within 30 days",
            data={"pools": pools, "warnings": warnings},
            recommendations=["Monitor growth rate", "Plan capacity expansion"],
        )

    return CheckResult(
        name="disk_prediction",
        severity=CheckSeverity.OK,
        message="Disk capacity healthy across all pools",
        data={"pools": pools},
    )


async def backup_freshness() -> CheckResult:
    """Check if backups are fresh (not stale).

    In production: checks latest ZFS snapshot age and restic
    backup timestamps.
    """
    # Simulated — in production this runs zfs list -t snapshot
    backup_age_hours = 18.0  # Hours since last backup
    max_acceptable_hours = 24.0

    if backup_age_hours > max_acceptable_hours * 2:
        return CheckResult(
            name="backup_freshness",
            severity=CheckSeverity.CRITICAL,
            message=f"Backups are {backup_age_hours:.0f}h old (>48h stale!)",
            data={"age_hours": backup_age_hours, "threshold": max_acceptable_hours},
            recommendations=[
                "Run manual backup immediately",
                "Check backup cron job: crontab -l",
                "Verify backup target is reachable",
            ],
        )

    if backup_age_hours > max_acceptable_hours:
        return CheckResult(
            name="backup_freshness",
            severity=CheckSeverity.WARNING,
            message=f"Backups are {backup_age_hours:.0f}h old (threshold: {max_acceptable_hours:.0f}h)",
            data={"age_hours": backup_age_hours, "threshold": max_acceptable_hours},
            recommendations=["Check if nightly backup ran"],
        )

    return CheckResult(
        name="backup_freshness",
        severity=CheckSeverity.OK,
        message=f"Backups fresh ({backup_age_hours:.0f}h old)",
        data={"age_hours": backup_age_hours, "threshold": max_acceptable_hours},
    )


async def cert_expiry() -> CheckResult:
    """Check TLS certificate expiration dates.

    In production: connects to each HTTPS endpoint and reads
    certificate expiry, or checks certbot renewal status.
    """
    # Simulated certificates
    certs = [
        {"domain": "plex.home.local", "days_remaining": 45},
        {"domain": "grafana.home.local", "days_remaining": 12},
        {"domain": "*.home.local", "days_remaining": 60},
    ]

    expiring_soon = [c for c in certs if c["days_remaining"] < 14]
    expiring_month = [c for c in certs if 14 <= c["days_remaining"] < 30]

    if expiring_soon:
        names = [c["domain"] for c in expiring_soon]
        return CheckResult(
            name="cert_expiry",
            severity=CheckSeverity.WARNING,
            message=f"Certificates expiring soon: {', '.join(names)}",
            data={"certs": certs, "expiring_soon": expiring_soon},
            recommendations=[
                "Run certbot renew: certbot renew --force-renewal",
                "Check ACME challenge is accessible",
            ],
        )

    if expiring_month:
        return CheckResult(
            name="cert_expiry",
            severity=CheckSeverity.INFO,
            message=f"{len(expiring_month)} cert(s) expiring within 30 days",
            data={"certs": certs},
        )

    return CheckResult(
        name="cert_expiry",
        severity=CheckSeverity.OK,
        message=f"All {len(certs)} certificates valid",
        data={"certs": certs},
    )


async def cost_tracking() -> CheckResult:
    """Track LLM API costs and alert on budget overruns.

    In production: reads from the audit log / LLM router stats
    to calculate spend per provider per day/week/month.
    """
    # Simulated cost data
    daily_spend = 0.45  # USD
    weekly_spend = 2.80
    monthly_budget = 20.0
    projected_monthly = daily_spend * 30

    if projected_monthly > monthly_budget * 1.5:
        return CheckResult(
            name="cost_tracking",
            severity=CheckSeverity.WARNING,
            message=f"LLM spend trending high: ${projected_monthly:.2f}/mo projected (budget: ${monthly_budget:.0f})",
            data={
                "daily": daily_spend,
                "weekly": weekly_spend,
                "projected_monthly": projected_monthly,
                "budget": monthly_budget,
            },
            recommendations=[
                "Switch heavy tasks to cheaper models",
                "Increase response caching TTL",
                "Check for unnecessary API calls in logs",
            ],
        )

    return CheckResult(
        name="cost_tracking",
        severity=CheckSeverity.OK,
        message=f"LLM spend normal: ${daily_spend:.2f}/day (${projected_monthly:.1f}/mo projected)",
        data={
            "daily": daily_spend,
            "weekly": weekly_spend,
            "projected_monthly": projected_monthly,
            "budget": monthly_budget,
        },
    )


async def service_health() -> CheckResult:
    """Check HTTP service availability.

    In production: pings each configured service endpoint
    and reports response times and failures.
    """
    # Simulated service checks
    services = [
        {"name": "plex", "url": "http://localhost:32400/identity", "status": 200, "ms": 45},
        {"name": "sonarr", "url": "http://localhost:8989/api/v3/health", "status": 200, "ms": 120},
        {"name": "radarr", "url": "http://localhost:7878/api/v3/health", "status": 200, "ms": 95},
        {"name": "overseerr", "url": "http://localhost:5055/api/v1/status", "status": 200, "ms": 210},
    ]

    down = [s for s in services if s["status"] != 200]
    slow = [s for s in services if s["ms"] > 500]

    if down:
        names = [s["name"] for s in down]
        return CheckResult(
            name="service_health",
            severity=CheckSeverity.CRITICAL,
            message=f"Services unreachable: {', '.join(names)}",
            data={"services": services, "down": down},
            recommendations=[
                f"Check container: docker logs {names[0]}",
                f"Restart: docker restart {names[0]}",
            ],
        )

    if slow:
        names = [s["name"] for s in slow]
        return CheckResult(
            name="service_health",
            severity=CheckSeverity.WARNING,
            message=f"Services slow (>500ms): {', '.join(names)}",
            data={"services": services, "slow": slow},
            recommendations=["Check system load", "Possible memory pressure"],
        )

    return CheckResult(
        name="service_health",
        severity=CheckSeverity.OK,
        message=f"All {len(services)} services responding normally",
        data={"services": services},
    )
