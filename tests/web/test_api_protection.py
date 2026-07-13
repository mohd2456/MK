"""Integration tests for data protection routes."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_backup_jobs_empty(auth_client: AsyncClient):
    """Test listing backup jobs when none exist."""
    response = await auth_client.get("/api/v1/protection/jobs")
    assert response.status_code == 200
    data = response.json()
    assert "jobs" in data
    assert data["jobs"] == []


@pytest.mark.asyncio
async def test_create_backup_job(auth_client: AsyncClient):
    """Test creating a backup job."""
    job_data = {
        "name": "daily-media",
        "backup_type": "zfs_snapshot",
        "source": "tank/media",
        "destination": "backup/media",
        "schedule": "daily",
        "retention_count": 7,
    }
    response = await auth_client.post("/api/v1/protection/jobs", json=job_data)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "created"
    assert data["job"]["name"] == "daily-media"
    assert data["job"]["id"] == 1


@pytest.mark.asyncio
async def test_backup_job_crud_flow(auth_client: AsyncClient):
    """Test full CRUD flow for backup jobs."""
    # Create
    job_data = {
        "name": "test-backup",
        "backup_type": "rsync",
        "source": "/data/important",
        "destination": "/backup/important",
        "schedule": "hourly",
    }
    r = await auth_client.post("/api/v1/protection/jobs", json=job_data)
    assert r.status_code == 200
    job_id = r.json()["job"]["id"]

    # List - should contain the job
    r = await auth_client.get("/api/v1/protection/jobs")
    assert r.status_code == 200
    jobs = r.json()["jobs"]
    assert any(j["id"] == job_id for j in jobs)

    # Update
    r = await auth_client.put(
        f"/api/v1/protection/jobs/{job_id}",
        json={"schedule": "daily", "retention_count": 14},
    )
    assert r.status_code == 200
    assert r.json()["job"]["schedule"] == "daily"
    assert r.json()["job"]["retention_count"] == 14

    # Run
    r = await auth_client.post(f"/api/v1/protection/jobs/{job_id}/run")
    assert r.status_code == 200
    assert r.json()["status"] == "triggered"

    # History
    r = await auth_client.get(f"/api/v1/protection/jobs/{job_id}/history")
    assert r.status_code == 200
    assert len(r.json()["history"]) >= 1

    # Delete
    r = await auth_client.delete(f"/api/v1/protection/jobs/{job_id}")
    assert r.status_code == 200
    assert r.json()["status"] == "deleted"

    # Verify deleted
    r = await auth_client.get("/api/v1/protection/jobs")
    assert not any(j["id"] == job_id for j in r.json()["jobs"])


@pytest.mark.asyncio
async def test_run_backup_job_executes_for_real(auth_client: AsyncClient):
    """Running a job triggers real background execution that completes.

    In the test environment there is no ZFS/rsync target, so the backup is
    expected to finish with status 'failed' (fast-fail) rather than the old
    hard-coded instant 'success'. We assert the run record transitions out of
    'running' and records a real duration/outcome.
    """
    import asyncio

    job_data = {
        "name": "exec-check",
        "backup_type": "rsync",
        "source": "/nonexistent/source",
        "destination": "/nonexistent/dest",
        "schedule": "daily",
    }
    r = await auth_client.post("/api/v1/protection/jobs", json=job_data)
    job_id = r.json()["job"]["id"]

    r = await auth_client.post(f"/api/v1/protection/jobs/{job_id}/run")
    assert r.status_code == 200
    assert r.json()["status"] == "triggered"

    # Poll history until the background task records completion.
    record = None
    for _ in range(50):  # up to ~5s
        r = await auth_client.get(f"/api/v1/protection/jobs/{job_id}/history")
        history = r.json()["history"]
        assert history, "run should be recorded immediately"
        record = history[-1]
        if record["status"] != "running":
            break
        await asyncio.sleep(0.1)

    assert record is not None
    assert record["status"] in ("success", "failed")
    # A real execution records an actual (non-stub) duration and finish time.
    assert record.get("finished_at") is not None
    assert isinstance(record["duration_seconds"], (int, float))


@pytest.mark.asyncio
async def test_backup_job_not_found(auth_client: AsyncClient):
    """Test operations on non-existent job return 404."""
    r = await auth_client.put("/api/v1/protection/jobs/999", json={"name": "x"})
    assert r.status_code == 404

    r = await auth_client.delete("/api/v1/protection/jobs/999")
    assert r.status_code == 404

    r = await auth_client.post("/api/v1/protection/jobs/999/run")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_create_backup_job_schedules_when_enabled(tmp_path, monkeypatch):
    """When scheduling is enabled, create wires into BackupManager.create_job.

    Uses a mocked BackupManager so no real systemd/sudo is touched, and asserts
    the job is reported as scheduled.
    """
    from httpx import ASGITransport, AsyncClient as AC

    from mk.server.backups import BackupManager
    from mk.tools.base import ToolResult
    from mk.web.app import create_app

    calls = {}

    async def fake_create_job(self, **kwargs):
        calls.update(kwargs)
        return ToolResult(success=True, output="scheduled")

    monkeypatch.setattr(BackupManager, "create_job", fake_create_job)

    app = create_app(
        pin="1234",
        audit_log_dir=str(tmp_path / "audit"),
        enable_backup_scheduling=True,
    )
    transport = ASGITransport(app=app)
    async with AC(transport=transport, base_url="http://t") as c:
        tok = (await c.post("/api/v1/auth/login", json={"pin": "1234"})).json()["token"]
        c.headers["Authorization"] = f"Bearer {tok}"
        resp = await c.post(
            "/api/v1/protection/jobs",
            json={
                "name": "nightly",
                "backup_type": "zfs_snapshot",
                "source": "tank/data",
                "destination": "backup/data",
                "schedule": "daily",
            },
        )
        assert resp.status_code == 200
        job = resp.json()["job"]
        assert job["scheduled"] is True
        assert calls["name"] == "nightly"
        assert calls["backup_type"] == "zfs_snapshot"

    from mk.web import app as web_app

    store = getattr(web_app, "_chat_history", None)
    if store is not None:
        await store.close()


@pytest.mark.asyncio
async def test_scrub_schedules(auth_client: AsyncClient):
    """Test scrub schedule endpoints."""
    # List
    r = await auth_client.get("/api/v1/protection/scrubs")
    assert r.status_code == 200
    assert "scrubs" in r.json()

    # Get specific pool
    r = await auth_client.get("/api/v1/protection/scrubs/tank")
    assert r.status_code == 200
    assert r.json()["pool"] == "tank"

    # Update
    r = await auth_client.put(
        "/api/v1/protection/scrubs/tank",
        json={"schedule": "weekly", "day": "sunday"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "updated"

    # Run scrub (will fail in test env, but endpoint responds)
    r = await auth_client.post("/api/v1/protection/scrubs/tank/run")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_replication_tasks(auth_client: AsyncClient):
    """Test replication task CRUD."""
    # Create
    r = await auth_client.post(
        "/api/v1/protection/replication",
        json={"name": "offsite", "source": "tank", "target": "remote:backup"},
    )
    assert r.status_code == 200
    task_id = r.json()["task"]["id"]

    # List
    r = await auth_client.get("/api/v1/protection/replication")
    assert r.status_code == 200
    assert len(r.json()["tasks"]) >= 1

    # Delete
    r = await auth_client.delete(f"/api/v1/protection/replication/{task_id}")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_retention_policies(auth_client: AsyncClient):
    """Test retention policy CRUD."""
    # Create
    r = await auth_client.post(
        "/api/v1/protection/retention",
        json={"name": "standard", "keep_daily": 7, "keep_weekly": 4, "keep_monthly": 12},
    )
    assert r.status_code == 200
    policy_id = r.json()["policy"]["id"]

    # List
    r = await auth_client.get("/api/v1/protection/retention")
    assert r.status_code == 200
    assert len(r.json()["policies"]) >= 1

    # Update
    r = await auth_client.put(
        f"/api/v1/protection/retention/{policy_id}",
        json={"keep_daily": 14},
    )
    assert r.status_code == 200
    assert r.json()["policy"]["keep_daily"] == 14


@pytest.mark.asyncio
async def test_protection_requires_auth(client: AsyncClient):
    """Test protection endpoints require authentication."""
    for path in [
        "/api/v1/protection/jobs",
        "/api/v1/protection/scrubs",
        "/api/v1/protection/replication",
        "/api/v1/protection/retention",
    ]:
        response = await client.get(path)
        assert response.status_code == 401, f"{path} should require auth"
