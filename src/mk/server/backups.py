"""Backup Manager - Scheduled snapshots, replication, and restore."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from mk.tools.base import ToolResult

from ._shell import safe_quote, validate_name

logger = logging.getLogger(__name__)

DEFAULT_RETENTION = {
    "hourly": 24,
    "daily": 7,
    "weekly": 4,
    "monthly": 12,
}


class BackupManager:
    """Manages backup jobs, snapshots, replication, and restores.

    Supports ZFS snapshots, ZFS send/receive, restic, and rsync.
    """

    def __init__(
        self,
        sudo: bool = True,
        config_dir: str = "/etc/mk/backups",
        state_dir: str = "/var/lib/mk/backups",
    ) -> None:
        self._sudo = sudo
        self._cmd_prefix = "sudo " if sudo else ""
        self._config_dir = config_dir
        self._state_dir = state_dir

    async def _run(self, cmd: str, check: bool = True, timeout: int = 3600) -> Tuple[int, str, str]:
        """Execute a shell command asynchronously."""
        full_cmd = f"{self._cmd_prefix}{cmd}" if not cmd.startswith("sudo") else cmd
        logger.debug(f"Backup exec: {full_cmd}")

        proc = await asyncio.create_subprocess_shell(
            full_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return 1, "", f"Command timed out after {timeout}s"

        rc = proc.returncode or 0
        out = stdout.decode().strip()
        err = stderr.decode().strip()

        if rc != 0 and check:
            logger.debug(f"Command failed ({rc}): {full_cmd}\n{err}")

        return rc, out, err

    async def _run_with_stdin(self, cmd: str, input_data: str) -> Tuple[int, str, str]:
        """Execute a shell command with data passed via stdin."""
        full_cmd = f"{self._cmd_prefix}{cmd}" if not cmd.startswith("sudo") else cmd
        logger.debug(f"Backup exec (stdin): {full_cmd}")

        proc = await asyncio.create_subprocess_shell(
            full_cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate(input=input_data.encode())
        rc = proc.returncode or 0
        return rc, stdout.decode().strip(), stderr.decode().strip()

    # Backup Job Management

    async def list_jobs(self) -> ToolResult:
        """List all configured backup jobs."""
        rc, out, err = await self._run(
            f"find {safe_quote(self._config_dir)} -name '*.json' 2>/dev/null", check=False
        )

        jobs: List[Dict[str, Any]] = []
        if out:
            for config_file in out.splitlines():
                if config_file.strip():
                    rc2, content, _ = await self._run(
                        f"cat {safe_quote(config_file.strip())}", check=False
                    )
                    if rc2 == 0:
                        try:
                            job = json.loads(content)
                            jobs.append(job)
                        except json.JSONDecodeError:
                            continue

        return ToolResult(
            success=True,
            output=json.dumps(jobs, indent=2) if jobs else "No backup jobs configured",
            metadata={"job_count": len(jobs), "jobs": jobs},
        )

    async def create_job(
        self,
        name: str,
        backup_type: str,
        source: str,
        destination: str,
        schedule: str = "daily",
        retention_count: int = 7,
        cron_expression: Optional[str] = None,
    ) -> ToolResult:
        """Create a new backup job."""
        validate_name(name, "job name")

        valid_types = ["zfs_snapshot", "zfs_send", "rsync", "restic"]
        if backup_type not in valid_types:
            return ToolResult(
                success=False,
                error=f"Invalid backup type. Use: {', '.join(valid_types)}",
            )

        valid_schedules = ["hourly", "daily", "weekly", "monthly", "custom"]
        if schedule not in valid_schedules:
            return ToolResult(
                success=False,
                error=f"Invalid schedule. Use: {', '.join(valid_schedules)}",
            )

        if schedule == "custom" and not cron_expression:
            return ToolResult(
                success=False,
                error="cron_expression required when schedule is 'custom'",
            )

        job_config = {
            "name": name,
            "backup_type": backup_type,
            "source": source,
            "destination": destination,
            "schedule": schedule,
            "cron_expression": cron_expression,
            "retention_count": retention_count,
            "enabled": True,
            "created": datetime.now().isoformat(),
            "last_run": None,
            "last_status": None,
        }

        await self._run(f"mkdir -p {safe_quote(self._config_dir)}")

        config_path = f"{self._config_dir}/{name}.json"
        config_json = json.dumps(job_config, indent=2)

        # Write config via stdin to avoid interpolation issues
        rc, _, err = await self._run_with_stdin(
            f"tee {safe_quote(config_path)} > /dev/null", config_json
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to save job config: {err}")

        # Create corresponding systemd timer
        calendar_map = {
            "hourly": "*-*-* *:00:00",
            "daily": "*-*-* 02:00:00",
            "weekly": "Mon *-*-* 02:00:00",
            "monthly": "*-*-01 02:00:00",
        }
        on_calendar = (
            cron_expression
            if schedule == "custom"
            else calendar_map.get(schedule, "*-*-* 02:00:00")
        )

        service_content = f"""[Unit]
Description=MK Backup Job: {name}
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/mk-backup-run {name}
StandardOutput=journal
StandardError=journal
"""
        service_path = f"/etc/systemd/system/mk-backup-{name}.service"
        await self._run_with_stdin(f"tee {safe_quote(service_path)} > /dev/null", service_content)

        timer_content = f"""[Unit]
Description=MK Backup Timer: {name}

[Timer]
OnCalendar={on_calendar}
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
"""
        timer_path = f"/etc/systemd/system/mk-backup-{name}.timer"
        await self._run_with_stdin(f"tee {safe_quote(timer_path)} > /dev/null", timer_content)

        await self._run("systemctl daemon-reload")
        await self._run(f"systemctl enable --now mk-backup-{safe_quote(name)}.timer")

        return ToolResult(
            success=True,
            output=f"Backup job '{name}' created (type: {backup_type}, schedule: {schedule})",
            side_effects=[
                f"Job config saved to {config_path}",
                "Systemd timer created and enabled",
                f"Next run scheduled: {on_calendar}",
            ],
            metadata={
                "job": name,
                "type": backup_type,
                "schedule": schedule,
                "config_path": config_path,
            },
        )

    async def delete_job(self, name: str) -> ToolResult:
        """Delete a backup job and its timer."""
        validate_name(name, "job name")

        await self._run(f"systemctl stop mk-backup-{safe_quote(name)}.timer", check=False)
        await self._run(f"systemctl disable mk-backup-{safe_quote(name)}.timer", check=False)

        await self._run(
            f"rm -f {safe_quote(f'/etc/systemd/system/mk-backup-{name}.service')}", check=False
        )
        await self._run(
            f"rm -f {safe_quote(f'/etc/systemd/system/mk-backup-{name}.timer')}", check=False
        )
        await self._run(f"rm -f {safe_quote(f'{self._config_dir}/{name}.json')}", check=False)
        await self._run("systemctl daemon-reload")

        return ToolResult(
            success=True,
            output=f"Backup job '{name}' deleted",
            side_effects=[f"Job '{name}' removed with timer and config"],
            metadata={"job": name, "action": "delete"},
        )

    # Manual Backup Execution

    async def run_backup(self, name: str) -> ToolResult:
        """Manually trigger a backup job."""
        validate_name(name, "job name")
        config_path = f"{self._config_dir}/{name}.json"
        rc, content, err = await self._run(f"cat {safe_quote(config_path)}")
        if rc != 0:
            return ToolResult(success=False, error=f"Job '{name}' not found: {err}")

        try:
            job = json.loads(content)
        except json.JSONDecodeError:
            return ToolResult(success=False, error=f"Invalid job config for '{name}'")

        result = await self.run_backup_config(job)

        # Update job state
        status = "success" if result.success else "failed"
        job["last_run"] = datetime.now().isoformat()
        job["last_status"] = status
        updated_json = json.dumps(job, indent=2)
        await self._run_with_stdin(f"tee {safe_quote(config_path)} > /dev/null", updated_json)

        return result

    async def run_backup_config(self, job: Dict[str, Any]) -> ToolResult:
        """Execute a backup from an explicit job config dict.

        Unlike :meth:`run_backup`, this does not require an on-disk job config
        file — it dispatches purely on the provided dict. This lets callers that
        manage their own job records (e.g. the web API's in-memory store) run a
        real backup without first materializing a config file.

        Args:
            job: Mapping with at least ``name`` and ``backup_type``; ``source``
                and ``destination`` as required by the backup type.

        Returns:
            ToolResult describing the outcome.
        """
        name = job.get("name") or "adhoc"
        validate_name(name, "job name")
        backup_type = job.get("backup_type", "")
        source = job.get("source", "")
        destination = job.get("destination", "")

        if backup_type == "zfs_snapshot":
            return await self._run_zfs_snapshot(source, name)
        elif backup_type == "zfs_send":
            return await self._run_zfs_send(source, destination)
        elif backup_type == "rsync":
            return await self._run_rsync(source, destination)
        elif backup_type == "restic":
            return await self._run_restic(source, destination)
        return ToolResult(success=False, error=f"Unknown backup type: {backup_type}")

    async def _run_zfs_snapshot(self, dataset: str, job_name: str) -> ToolResult:
        """Execute a ZFS snapshot backup."""
        validate_name(dataset, "dataset")
        snap_name = f"mk-backup-{job_name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        full_name = f"{dataset}@{snap_name}"

        rc, out, err = await self._run(f"zfs snapshot -r {safe_quote(full_name)}")
        if rc != 0:
            return ToolResult(success=False, error=f"Snapshot failed: {err}")

        return ToolResult(
            success=True,
            output=f"Backup snapshot created: {full_name}",
            side_effects=[f"ZFS snapshot '{full_name}' created"],
            metadata={"snapshot": full_name, "type": "zfs_snapshot"},
        )

    async def _run_zfs_send(self, source: str, destination: str) -> ToolResult:
        """Execute a ZFS send/receive replication."""
        validate_name(source, "source dataset")

        rc, out, err = await self._run(
            f"zfs list -t snapshot -H -o name -S creation {safe_quote(source)} | head -1"
        )
        if rc != 0 or not out:
            snap_name = f"mk-replicate-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            await self._run(f"zfs snapshot {safe_quote(source)}@{safe_quote(snap_name)}")
            latest_snap = f"{source}@{snap_name}"
        else:
            latest_snap = out.strip()

        if ":" in destination:
            host, target = destination.split(":", 1)
            cmd = (
                f"zfs send -R {safe_quote(latest_snap)} | "
                f"ssh {safe_quote(host)} zfs receive -F {safe_quote(target)}"
            )
        else:
            cmd = (
                f"zfs send -R {safe_quote(latest_snap)} | zfs receive -F {safe_quote(destination)}"
            )

        rc, out, err = await self._run(cmd, timeout=7200)
        if rc != 0:
            return ToolResult(success=False, error=f"Replication failed: {err}")

        return ToolResult(
            success=True,
            output=f"Replicated {latest_snap} -> {destination}",
            side_effects=[f"Dataset replicated to {destination}"],
            metadata={"snapshot": latest_snap, "destination": destination, "type": "zfs_send"},
        )

    async def _run_rsync(self, source: str, destination: str) -> ToolResult:
        """Execute an rsync backup."""
        rc, out, err = await self._run(
            f"rsync -avz --delete --stats {safe_quote(source)}/ {safe_quote(destination)}/",
            timeout=7200,
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Rsync failed: {err}")

        return ToolResult(
            success=True,
            output=f"Rsync complete: {source} -> {destination}\n{out}",
            side_effects=[f"Directory synced to {destination}"],
            metadata={"source": source, "destination": destination, "type": "rsync"},
        )

    async def _run_restic(self, source: str, repository: str) -> ToolResult:
        """Execute a restic backup."""
        rc, out, err = await self._run(
            f"restic -r {safe_quote(repository)} backup {safe_quote(source)} --json",
            timeout=7200,
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Restic backup failed: {err}")

        return ToolResult(
            success=True,
            output=f"Restic backup complete: {source} -> {repository}\n{out}",
            side_effects=[f"Backup stored in restic repo: {repository}"],
            metadata={"source": source, "repository": repository, "type": "restic"},
        )

    # Retention / Cleanup

    async def apply_retention(self, job_name: str) -> ToolResult:
        """Apply retention policy -- remove old backups exceeding retention count."""
        validate_name(job_name, "job name")
        config_path = f"{self._config_dir}/{job_name}.json"
        rc, content, err = await self._run(f"cat {safe_quote(config_path)}")
        if rc != 0:
            return ToolResult(success=False, error=f"Job '{job_name}' not found")

        try:
            job = json.loads(content)
        except json.JSONDecodeError:
            return ToolResult(success=False, error="Invalid job config")

        backup_type = job.get("backup_type", "")
        source = job.get("source", "")
        retention = job.get("retention_count", 7)

        removed: List[str] = []

        if backup_type in ("zfs_snapshot", "zfs_send"):
            rc, out, err = await self._run(
                f"zfs list -t snapshot -H -o name -S creation -r {safe_quote(source)} 2>/dev/null | "
                f"grep 'mk-backup-{job_name}'",
                check=False,
            )

            if rc == 0 and out:
                snapshots = [s.strip() for s in out.splitlines() if s.strip()]
                to_remove = snapshots[retention:]
                for snap in to_remove:
                    rc2, _, _ = await self._run(f"zfs destroy {safe_quote(snap)}", check=False)
                    if rc2 == 0:
                        removed.append(snap)

        elif backup_type == "restic":
            repository = job.get("destination", "")
            rc, out, err = await self._run(
                f"restic -r {safe_quote(repository)} forget --keep-last {int(retention)} --prune --json",
                check=False,
            )
            if rc == 0:
                removed.append(f"Restic pruned to last {retention} snapshots")

        return ToolResult(
            success=True,
            output=f"Retention applied for '{job_name}': removed {len(removed)} old backups",
            side_effects=[f"Removed: {snap}" for snap in removed]
            if removed
            else ["Nothing to remove"],
            metadata={"job": job_name, "removed_count": len(removed), "retention": retention},
        )

    # Restore Operations

    async def list_restore_points(self, job_name: str) -> ToolResult:
        """List available restore points for a backup job."""
        validate_name(job_name, "job name")
        config_path = f"{self._config_dir}/{job_name}.json"
        rc, content, err = await self._run(f"cat {safe_quote(config_path)}")
        if rc != 0:
            return ToolResult(success=False, error=f"Job '{job_name}' not found")

        try:
            job = json.loads(content)
        except json.JSONDecodeError:
            return ToolResult(success=False, error="Invalid job config")

        backup_type = job.get("backup_type", "")
        source = job.get("source", "")
        destination = job.get("destination", "")

        points: List[Dict[str, Any]] = []

        if backup_type in ("zfs_snapshot", "zfs_send"):
            rc, out, _ = await self._run(
                f"zfs list -t snapshot -Hp -o name,used,creation -S creation -r {safe_quote(source)} 2>/dev/null | "
                f"grep 'mk-backup-{job_name}'",
                check=False,
            )
            if rc == 0 and out:
                for line in out.splitlines():
                    parts = line.split("\t")
                    if len(parts) >= 3:
                        points.append(
                            {
                                "id": parts[0],
                                "size_bytes": int(parts[1]),
                                "created": parts[2],
                            }
                        )

        elif backup_type == "restic":
            rc, out, _ = await self._run(
                f"restic -r {safe_quote(destination)} snapshots --json",
                check=False,
            )
            if rc == 0 and out:
                try:
                    snapshots = json.loads(out)
                    for snap in snapshots:
                        points.append(
                            {
                                "id": snap.get("short_id", snap.get("id", "")),
                                "created": snap.get("time", ""),
                                "paths": snap.get("paths", []),
                            }
                        )
                except json.JSONDecodeError:
                    pass

        return ToolResult(
            success=True,
            output=json.dumps(points, indent=2) if points else "No restore points found",
            metadata={"job": job_name, "point_count": len(points)},
        )

    async def restore(
        self,
        job_name: str,
        restore_point_id: str,
        target_path: Optional[str] = None,
    ) -> ToolResult:
        """Restore from a backup restore point."""
        validate_name(job_name, "job name")
        config_path = f"{self._config_dir}/{job_name}.json"
        rc, content, err = await self._run(f"cat {safe_quote(config_path)}")
        if rc != 0:
            return ToolResult(success=False, error=f"Job '{job_name}' not found")

        try:
            job = json.loads(content)
        except json.JSONDecodeError:
            return ToolResult(success=False, error="Invalid job config")

        backup_type = job.get("backup_type", "")
        source = job.get("source", "")
        destination = job.get("destination", "")

        if backup_type in ("zfs_snapshot", "zfs_send"):
            rc, out, err = await self._run(f"zfs rollback -r {safe_quote(restore_point_id)}")
            if rc != 0:
                return ToolResult(success=False, error=f"ZFS rollback failed: {err}")

            return ToolResult(
                success=True,
                output=f"Restored to snapshot: {restore_point_id}",
                side_effects=[
                    f"Dataset rolled back to {restore_point_id}",
                    "Newer data has been overwritten",
                ],
                metadata={"restore_point": restore_point_id, "type": "zfs_rollback"},
            )

        elif backup_type == "restic":
            restore_target = target_path or source
            rc, out, err = await self._run(
                f"restic -r {safe_quote(destination)} restore {safe_quote(restore_point_id)} "
                f"--target {safe_quote(restore_target)}",
                timeout=7200,
            )
            if rc != 0:
                return ToolResult(success=False, error=f"Restic restore failed: {err}")

            return ToolResult(
                success=True,
                output=f"Restored from restic snapshot {restore_point_id} to {restore_target}",
                side_effects=[f"Files restored to {restore_target}"],
                metadata={
                    "restore_point": restore_point_id,
                    "target": restore_target,
                    "type": "restic",
                },
            )

        elif backup_type == "rsync":
            restore_target = target_path or source
            rc, out, err = await self._run(
                f"rsync -avz --stats {safe_quote(destination)}/ {safe_quote(restore_target)}/",
                timeout=7200,
            )
            if rc != 0:
                return ToolResult(success=False, error=f"Rsync restore failed: {err}")

            return ToolResult(
                success=True,
                output=f"Restored from rsync mirror: {destination} -> {restore_target}",
                side_effects=[f"Files restored to {restore_target}"],
                metadata={"source": destination, "target": restore_target, "type": "rsync"},
            )

        return ToolResult(success=False, error=f"Unsupported backup type: {backup_type}")

    # Verification

    async def verify_backup(self, job_name: str) -> ToolResult:
        """Verify the integrity of the latest backup for a job."""
        validate_name(job_name, "job name")
        config_path = f"{self._config_dir}/{job_name}.json"
        rc, content, err = await self._run(f"cat {safe_quote(config_path)}")
        if rc != 0:
            return ToolResult(success=False, error=f"Job '{job_name}' not found")

        try:
            job = json.loads(content)
        except json.JSONDecodeError:
            return ToolResult(success=False, error="Invalid job config")

        backup_type = job.get("backup_type", "")
        destination = job.get("destination", "")

        if backup_type == "restic":
            rc, out, err = await self._run(
                f"restic -r {safe_quote(destination)} check --json",
                timeout=3600,
            )
            if rc != 0:
                return ToolResult(
                    success=False,
                    error=f"Verification FAILED: {err}",
                    metadata={"verified": False, "job": job_name},
                )
            return ToolResult(
                success=True,
                output=f"Backup verification PASSED for '{job_name}'\n{out}",
                metadata={"verified": True, "job": job_name},
            )

        elif backup_type in ("zfs_snapshot", "zfs_send"):
            source = job.get("source", "")
            pool = source.split("/")[0] if "/" in source else source
            validate_name(pool, "pool")
            rc, out, err = await self._run(f"zpool scrub {safe_quote(pool)}")
            if rc != 0:
                return ToolResult(success=False, error=f"Scrub failed: {err}")
            return ToolResult(
                success=True,
                output=f"ZFS scrub initiated on pool '{pool}' to verify data integrity",
                metadata={"verified": True, "job": job_name, "pool": pool},
            )

        return ToolResult(
            success=True,
            output=f"No automated verification available for {backup_type} backups",
            metadata={"verified": False, "job": job_name},
        )

    # Backup Health Summary

    async def health_check(self) -> ToolResult:
        """Check the health of all backup jobs."""
        result = await self.list_jobs()
        if not result.success:
            return result

        jobs = result.metadata.get("jobs", [])
        issues: List[str] = []
        healthy_count = 0

        for job in jobs:
            name = job.get("name", "unknown")
            last_status = job.get("last_status")
            last_run = job.get("last_run")
            enabled = job.get("enabled", True)

            if not enabled:
                continue

            if last_status == "failed":
                issues.append(f"FAILED: Job '{name}' last run failed")
            elif last_run is None:
                issues.append(f"NEVER RUN: Job '{name}' has never executed")
            else:
                try:
                    last_dt = datetime.fromisoformat(last_run)
                    age_hours = (datetime.now() - last_dt).total_seconds() / 3600

                    schedule = job.get("schedule", "daily")
                    max_age = {"hourly": 2, "daily": 26, "weekly": 170, "monthly": 744}
                    threshold = max_age.get(schedule, 48)

                    if age_hours > threshold:
                        issues.append(
                            f"STALE: Job '{name}' last ran {age_hours:.0f}h ago "
                            f"(expected every {schedule})"
                        )
                    else:
                        healthy_count += 1
                except (ValueError, TypeError):
                    healthy_count += 1

        summary = f"Backup Health: {healthy_count}/{len(jobs)} jobs healthy"
        if issues:
            summary += f"\n\nIssues ({len(issues)}):\n" + "\n".join(f"  - {i}" for i in issues)

        return ToolResult(
            success=len(issues) == 0,
            output=summary,
            metadata={
                "healthy_count": healthy_count,
                "total_jobs": len(jobs),
                "issues": issues,
            },
        )
