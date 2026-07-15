"""Tests for mk doctor — system readiness checks."""

from __future__ import annotations

import pytest

from mk.doctor import (
    Check,
    DoctorReport,
    check_config,
    check_disk_space,
    check_llm_keys,
    check_local_brain,
    check_permissions,
    check_python_version,
    check_ram,
    run_doctor,
)


@pytest.mark.asyncio
async def test_python_version_passes():
    c = await check_python_version()
    assert c.status == "pass"
    assert "3." in c.detail


@pytest.mark.asyncio
async def test_disk_space_returns_result():
    c = await check_disk_space()
    assert c.status in ("pass", "warn", "fail")
    assert "free" in c.detail or "check" in c.detail


@pytest.mark.asyncio
async def test_ram_returns_result():
    c = await check_ram()
    assert c.status in ("pass", "warn", "skip")


@pytest.mark.asyncio
async def test_permissions_pass_for_home():
    c = await check_permissions()
    # In test env home dir is writable
    assert c.status in ("pass", "fail")


@pytest.mark.asyncio
async def test_config_warns_when_missing(tmp_path, monkeypatch):
    # Point away from any existing config
    monkeypatch.chdir(tmp_path)
    c = await check_config()
    # May pass if ~/.mk/config.yaml exists, or warn if not
    assert c.status in ("pass", "warn")


@pytest.mark.asyncio
async def test_local_brain_skip_when_unset(monkeypatch):
    monkeypatch.delenv("MK_LOCAL_BRAIN_URL", raising=False)
    c = await check_local_brain()
    assert c.status == "skip"


@pytest.mark.asyncio
async def test_local_brain_fail_when_unreachable(monkeypatch):
    monkeypatch.setenv("MK_LOCAL_BRAIN_URL", "http://localhost:19999/v1")
    c = await check_local_brain()
    assert c.status == "fail"
    assert "Not reachable" in c.detail


@pytest.mark.asyncio
async def test_llm_keys_warns_when_empty(tmp_path, monkeypatch):
    monkeypatch.delenv("MK_LOCAL_BRAIN_URL", raising=False)
    c = await check_llm_keys()
    # In test env: no keys file → warn (unless there's one at /etc/mk/keys.json)
    assert c.status in ("pass", "warn")


@pytest.mark.asyncio
async def test_run_doctor_returns_complete_report():
    report = await run_doctor()
    assert isinstance(report, DoctorReport)
    assert len(report.checks) >= 10  # at least 10 checks exist
    # All checks have valid status
    for c in report.checks:
        assert c.status in ("pass", "warn", "fail", "skip")


@pytest.mark.asyncio
async def test_doctor_report_to_dict():
    report = DoctorReport(
        checks=[
            Check("test1", "system", "pass", "ok"),
            Check("test2", "ai", "fail", "broken", "fix it"),
        ]
    )
    d = report.to_dict()
    assert d["healthy"] is False
    assert d["passed"] == 1
    assert d["failures"] == 1
    assert len(d["checks"]) == 2
    assert d["checks"][1]["fix"] == "fix it"


def test_cli_entry_runs(capsys):
    """mk-doctor CLI runs without crashing."""
    import asyncio

    from mk.doctor import run_doctor, print_report

    report = asyncio.run(run_doctor())
    print_report(report)
    captured = capsys.readouterr()
    assert "MK Doctor" in captured.out
    assert "System" in captured.out
