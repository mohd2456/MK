"""Integration tests for network routes."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_interfaces(auth_client: AsyncClient):
    """Test listing network interfaces."""
    response = await auth_client.get("/api/v1/network/interfaces")
    assert response.status_code == 200
    data = response.json()
    assert "interfaces" in data


@pytest.mark.asyncio
async def test_firewall_crud(auth_client: AsyncClient):
    """Test firewall rules CRUD operations."""
    # List (empty)
    r = await auth_client.get("/api/v1/network/firewall")
    assert r.status_code == 200
    assert r.json()["rules"] == []

    # Create rule
    rule_data = {
        "chain": "input",
        "action": "accept",
        "protocol": "tcp",
        "source": "192.168.1.0/24",
        "port": 22,
        "comment": "Allow SSH from LAN",
    }
    r = await auth_client.post("/api/v1/network/firewall", json=rule_data)
    assert r.status_code == 200
    assert r.json()["status"] == "created"
    rule_id = r.json()["rule"]["id"]

    # Create second rule
    r = await auth_client.post(
        "/api/v1/network/firewall",
        json={"chain": "input", "action": "drop", "comment": "Drop all"},
    )
    assert r.status_code == 200
    rule_id_2 = r.json()["rule"]["id"]

    # List (should have 2)
    r = await auth_client.get("/api/v1/network/firewall")
    assert len(r.json()["rules"]) == 2

    # Update
    r = await auth_client.put(
        f"/api/v1/network/firewall/{rule_id}",
        json={"port": 2222, "comment": "Allow SSH on 2222"},
    )
    assert r.status_code == 200
    assert r.json()["rule"]["port"] == 2222

    # Reorder
    r = await auth_client.post(
        "/api/v1/network/firewall/reorder",
        json={"order": [rule_id_2, rule_id]},
    )
    assert r.status_code == 200
    rules = r.json()["rules"]
    assert rules[0]["id"] == rule_id_2
    assert rules[1]["id"] == rule_id

    # Delete
    r = await auth_client.delete(f"/api/v1/network/firewall/{rule_id}")
    assert r.status_code == 200

    # Verify deleted
    r = await auth_client.get("/api/v1/network/firewall")
    assert len(r.json()["rules"]) == 1


@pytest.mark.asyncio
async def test_firewall_not_found(auth_client: AsyncClient):
    """Test firewall operations on non-existent rule."""
    r = await auth_client.put("/api/v1/network/firewall/999", json={"action": "drop"})
    assert r.status_code == 404

    r = await auth_client.delete("/api/v1/network/firewall/999")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_wireguard_crud(auth_client: AsyncClient):
    """Test WireGuard interface and peer management."""
    # List interfaces (empty)
    r = await auth_client.get("/api/v1/network/wireguard")
    assert r.status_code == 200
    assert r.json()["interfaces"] == []

    # Create interface
    r = await auth_client.post(
        "/api/v1/network/wireguard",
        json={"name": "wg0", "listen_port": 51820, "address": "10.8.0.1/24"},
    )
    assert r.status_code == 200
    assert r.json()["interface"]["name"] == "wg0"

    # List peers (empty)
    r = await auth_client.get("/api/v1/network/wireguard/wg0/peers")
    assert r.status_code == 200
    assert r.json()["peers"] == []

    # Add peer
    r = await auth_client.post(
        "/api/v1/network/wireguard/wg0/peers",
        json={
            "name": "phone",
            "public_key": "aB3cXyZ123=",
            "allowed_ips": ["10.8.0.2/32"],
        },
    )
    assert r.status_code == 200
    peer_id = r.json()["peer"]["id"]

    # List peers (should have 1)
    r = await auth_client.get("/api/v1/network/wireguard/wg0/peers")
    assert len(r.json()["peers"]) == 1

    # Delete peer
    r = await auth_client.delete(f"/api/v1/network/wireguard/wg0/peers/{peer_id}")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_wireguard_not_found(auth_client: AsyncClient):
    """Test WireGuard operations on non-existent interface."""
    r = await auth_client.get("/api/v1/network/wireguard/nonexistent/peers")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_dns_config(auth_client: AsyncClient):
    """Test DNS configuration GET and PUT."""
    # Get
    r = await auth_client.get("/api/v1/network/dns")
    assert r.status_code == 200
    data = r.json()
    assert "primary" in data
    assert "secondary" in data

    # Update
    r = await auth_client.put(
        "/api/v1/network/dns",
        json={"primary": "9.9.9.9", "secondary": "1.0.0.1"},
    )
    assert r.status_code == 200
    assert r.json()["config"]["primary"] == "9.9.9.9"

    # Verify update persists
    r = await auth_client.get("/api/v1/network/dns")
    assert r.json()["primary"] == "9.9.9.9"


@pytest.mark.asyncio
async def test_proxy_crud(auth_client: AsyncClient):
    """Test reverse proxy site CRUD."""
    # List (empty)
    r = await auth_client.get("/api/v1/network/proxy")
    assert r.status_code == 200
    assert r.json()["sites"] == []

    # Create
    r = await auth_client.post(
        "/api/v1/network/proxy",
        json={"domain": "plex.example.com", "backend": "localhost:32400", "ssl": "auto"},
    )
    assert r.status_code == 200
    site_id = r.json()["site"]["id"]

    # Update
    r = await auth_client.put(
        f"/api/v1/network/proxy/{site_id}",
        json={"backend": "localhost:32401"},
    )
    assert r.status_code == 200
    assert r.json()["site"]["backend"] == "localhost:32401"

    # Delete
    r = await auth_client.delete(f"/api/v1/network/proxy/{site_id}")
    assert r.status_code == 200

    # Verify deleted
    r = await auth_client.get("/api/v1/network/proxy")
    assert r.json()["sites"] == []


@pytest.mark.asyncio
async def test_network_requires_auth(client: AsyncClient):
    """Test network endpoints require authentication."""
    for path in [
        "/api/v1/network/interfaces",
        "/api/v1/network/firewall",
        "/api/v1/network/wireguard",
        "/api/v1/network/dns",
        "/api/v1/network/proxy",
    ]:
        response = await client.get(path)
        assert response.status_code == 401, f"{path} should require auth"
