"""Security tests for BackupManager.create_job input handling.

Focus: a custom cron_expression is interpolated into a systemd timer unit file,
so it must be rejected if it could inject additional unit directives. Validation
happens before any subprocess/file write, so a malicious value produces a clean
failure with no side effects.
"""

from __future__ import annotations

import pytest

from mk.server.backups import BackupManager


@pytest.mark.asyncio
async def test_create_job_rejects_cron_newline_injection():
    mgr = BackupManager(sudo=False)
    malicious = "*-*-* 02:00:00\n[Service]\nExecStart=/bin/touch /tmp/pwned"
    result = await mgr.create_job(
        name="evil",
        backup_type="rsync",
        source="/data",
        destination="/backup",
        schedule="custom",
        cron_expression=malicious,
    )
    assert result.success is False
    assert "cron_expression" in (result.error or "")


@pytest.mark.asyncio
async def test_create_job_rejects_cron_directive_brackets():
    mgr = BackupManager(sudo=False)
    result = await mgr.create_job(
        name="evil2",
        backup_type="rsync",
        source="/data",
        destination="/backup",
        schedule="custom",
        cron_expression="[Timer]",
    )
    assert result.success is False
    assert "cron_expression" in (result.error or "")


@pytest.mark.asyncio
async def test_create_job_rejects_unsafe_name():
    mgr = BackupManager(sudo=False)
    with pytest.raises(ValueError):
        await mgr.create_job(
            name="evil;reboot",
            backup_type="rsync",
            source="/data",
            destination="/backup",
            schedule="daily",
        )
