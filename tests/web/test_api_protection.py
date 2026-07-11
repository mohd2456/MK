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
async def test_backup_job_not_found(auth_client: AsyncClient):
    """Test operations on non-existent job return 404."""
    r = await auth_client.put("/api/v1/protection/jobs/999", json={"name": "x"})
    assert r.status_code == 404

    r = await auth_client.delete("/api/v1/protection/jobs/999")
    assert r.status_code == 404

    r = await auth_client.post("/api/v1/protection/jobs/999/run")
    assert r.status_code == 404


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
