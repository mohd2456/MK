"""Comprehensive tests for the MK server management module."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest


# === Storage Tests ===


@pytest.mark.asyncio
async def test_list_drives_success():
    """Test listing drives with mocked lsblk."""
    from mk.server.storage import list_drives

    mock_data = {
        "blockdevices": [
            {
                "name": "sda",
                "size": "500G",
                "type": "disk",
                "mountpoint": None,
                "fstype": None,
                "model": "Samsung SSD",
                "children": [
                    {
                        "name": "sda1",
                        "size": "499G",
                        "type": "part",
                        "mountpoint": "/",
                        "fstype": "ext4",
                    }
                ],
            }
        ]
    }
    mock_output = json.dumps(mock_data)

    with patch("mk.server.storage.asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(mock_output.encode(), b""))
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        result = await list_drives()
        assert result["success"] is True
        assert len(result["drives"]) == 1
        assert result["drives"][0]["name"] == "sda"
        assert result["drives"][0]["model"] == "Samsung SSD"
        assert len(result["drives"][0]["children"]) == 1


@pytest.mark.asyncio
async def test_list_drives_failure():
    """Test list_drives handles command failure."""
    from mk.server.storage import list_drives

    with patch("mk.server.storage.asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b"lsblk not found"))
        mock_proc.returncode = 1
        mock_exec.return_value = mock_proc

        result = await list_drives()
        assert result["success"] is False
        assert "error" in result


@pytest.mark.asyncio
async def test_check_smart_health():
    """Test SMART health check."""
    from mk.server.storage import check_smart_health

    mock_data = {
        "smart_status": {"passed": True},
        "temperature": {"current": 35},
        "model_name": "Samsung SSD 860",
        "serial_number": "ABC123",
        "ata_smart_attributes": {
            "table": [
                {"name": "Power_On_Hours", "raw": {"value": 5000}},
                {"name": "Reallocated_Sector_Ct", "raw": {"value": 0}},
            ]
        },
    }
    mock_output = json.dumps(mock_data)

    with patch("mk.server.storage.asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(mock_output.encode(), b""))
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        result = await check_smart_health("/dev/sda")
        assert result["success"] is True
        assert result["healthy"] is True
        assert result["temperature_c"] == 35
        assert result["power_on_hours"] == 5000
        assert result["reallocated_sectors"] == 0


@pytest.mark.asyncio
async def test_get_disk_usage():
    """Test disk usage with mocked df output."""
    from mk.server.storage import get_disk_usage

    mock_output = (
        "Filesystem      Size  Used Avail Use% Mounted on\n"
        "/dev/sda1       500G  200G  300G  40% /\n"
        "tmpfs           4.0G  100M  3.9G   3% /tmp"
    )

    with patch("mk.server.storage.asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(mock_output.encode(), b""))
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        result = await get_disk_usage()
        assert result["success"] is True
        assert len(result["filesystems"]) == 2
        assert result["filesystems"][0]["use_percent"] == "40%"
        assert result["filesystems"][0]["mountpoint"] == "/"


# === Container Tests ===


@pytest.mark.asyncio
async def test_list_containers():
    """Test listing Docker containers."""
    from mk.server.containers import list_containers

    line = json.dumps({
        "ID": "abc123",
        "Names": "plex",
        "Image": "plexinc/pms-docker",
        "Status": "Up 2 days",
        "State": "running",
        "Ports": "32400/tcp",
        "CreatedAt": "2024-01-01",
    })

    with patch("mk.server.containers.asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(line.encode(), b""))
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        result = await list_containers()
        assert result["success"] is True
        assert len(result["containers"]) == 1
        assert result["containers"][0]["name"] == "plex"
        assert result["containers"][0]["state"] == "running"


@pytest.mark.asyncio
async def test_start_container():
    """Test starting a container."""
    from mk.server.containers import start_container

    with patch("mk.server.containers.asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"plex", b""))
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        result = await start_container("plex")
        assert result["success"] is True
        assert result["container"] == "plex"
        assert result["action"] == "start"


@pytest.mark.asyncio
async def test_stop_container():
    """Test stopping a container."""
    from mk.server.containers import stop_container

    with patch("mk.server.containers.asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"plex", b""))
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        result = await stop_container("plex")
        assert result["success"] is True
        assert result["action"] == "stop"


@pytest.mark.asyncio
async def test_restart_container():
    """Test restarting a container."""
    from mk.server.containers import restart_container

    with patch("mk.server.containers.asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"plex", b""))
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        result = await restart_container("plex")
        assert result["success"] is True
        assert result["action"] == "restart"


@pytest.mark.asyncio
async def test_get_container_logs():
    """Test getting container logs."""
    from mk.server.containers import get_container_logs

    mock_logs = "2024-01-01 Starting Plex\n2024-01-01 Server ready"

    with patch("mk.server.containers.asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(mock_logs.encode(), b""))
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        result = await get_container_logs("plex", lines=50)
        assert result["success"] is True
        assert "Starting Plex" in result["logs"]


@pytest.mark.asyncio
async def test_get_container_stats():
    """Test getting container resource stats."""
    from mk.server.containers import get_container_stats

    line = json.dumps({
        "Name": "plex",
        "CPUPerc": "2.5%",
        "MemUsage": "512MiB / 8GiB",
        "MemPerc": "6.25%",
        "NetIO": "1.2GB / 500MB",
        "BlockIO": "100MB / 50MB",
        "PIDs": "42",
    })

    with patch("mk.server.containers.asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(line.encode(), b""))
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        result = await get_container_stats("plex")
        assert result["success"] is True
        assert len(result["stats"]) == 1
        assert result["stats"][0]["cpu_percent"] == "2.5%"


@pytest.mark.asyncio
async def test_pull_image():
    """Test pulling a Docker image."""
    from mk.server.containers import pull_image

    with patch("mk.server.containers.asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"Pull complete", b""))
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        result = await pull_image("nginx:latest")
        assert result["success"] is True
        assert result["image"] == "nginx:latest"


@pytest.mark.asyncio
async def test_container_command_failure():
    """Test container command handles failure."""
    from mk.server.containers import start_container

    with patch("mk.server.containers.asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b"No such container"))
        mock_proc.returncode = 1
        mock_exec.return_value = mock_proc

        result = await start_container("nonexistent")
        assert result["success"] is False
        assert result["error"] is not None


# === Network Tests ===


@pytest.mark.asyncio
async def test_get_interfaces():
    """Test getting network interfaces."""
    from mk.server.network import get_interfaces

    mock_data = [
        {
            "ifname": "eth0",
            "operstate": "UP",
            "address": "00:11:22:33:44:55",
            "mtu": 1500,
            "addr_info": [
                {"local": "192.168.1.100", "prefixlen": 24, "family": "inet"}
            ],
        },
        {
            "ifname": "lo",
            "operstate": "UNKNOWN",
            "address": "00:00:00:00:00:00",
            "mtu": 65536,
            "addr_info": [
                {"local": "127.0.0.1", "prefixlen": 8, "family": "inet"}
            ],
        },
    ]
    mock_output = json.dumps(mock_data)

    with patch("mk.server.network.asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(mock_output.encode(), b""))
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        result = await get_interfaces()
        assert result["success"] is True
        assert len(result["interfaces"]) == 2
        assert result["interfaces"][0]["name"] == "eth0"
        assert result["interfaces"][0]["state"] == "UP"
        assert result["interfaces"][0]["addresses"][0]["address"] == "192.168.1.100"


@pytest.mark.asyncio
async def test_check_connectivity_success():
    """Test connectivity check when host is reachable."""
    from mk.server.network import check_connectivity

    mock_output = (
        "PING 8.8.8.8 (8.8.8.8) 56(84) bytes of data.\n"
        "64 bytes from 8.8.8.8: icmp_seq=1 ttl=118\n"
        "\n"
        "--- 8.8.8.8 ping statistics ---\n"
        "3 packets transmitted, 3 received, 0% packet loss, time 2003ms\n"
        "rtt min/avg/max/mdev = 10.123/12.456/14.789/1.234 ms"
    )

    with patch("mk.server.network.asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(mock_output.encode(), b""))
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        result = await check_connectivity()
        assert result["success"] is True
        assert result["reachable"] is True
        assert result["latency_avg"] == "12.456ms"


@pytest.mark.asyncio
async def test_check_connectivity_failure():
    """Test connectivity check when host is unreachable."""
    from mk.server.network import check_connectivity

    mock_output = (
        "PING 8.8.8.8 (8.8.8.8) 56(84) bytes of data.\n"
        "\n"
        "--- 8.8.8.8 ping statistics ---\n"
        "3 packets transmitted, 0 received, 100% packet loss, time 2002ms"
    )

    with patch("mk.server.network.asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(mock_output.encode(), b""))
        mock_proc.returncode = 1
        mock_exec.return_value = mock_proc

        result = await check_connectivity()
        assert result["success"] is True
        assert result["reachable"] is False


@pytest.mark.asyncio
async def test_get_active_connections():
    """Test getting active connections."""
    from mk.server.network import get_active_connections

    mock_output = (
        "Netid  State   Recv-Q  Send-Q  Local Address:Port  Peer Address:Port\n"
        "tcp    LISTEN  0       128     0.0.0.0:22           0.0.0.0:*\n"
        "tcp    LISTEN  0       128     0.0.0.0:80           0.0.0.0:*"
    )

    with patch("mk.server.network.asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(mock_output.encode(), b""))
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        result = await get_active_connections()
        assert result["success"] is True
        assert len(result["connections"]) == 2
        assert result["connections"][0]["protocol"] == "tcp"


@pytest.mark.asyncio
async def test_get_dns_config():
    """Test getting DNS configuration."""
    from mk.server.network import get_dns_config

    mock_output = "nameserver 8.8.8.8\nnameserver 8.8.4.4\nsearch local"

    with patch("mk.server.network.asyncio.create_subprocess_exec") as mock_exec:
        mock_proc_fail = AsyncMock()
        mock_proc_fail.communicate = AsyncMock(return_value=(b"", b"not found"))
        mock_proc_fail.returncode = 1

        mock_proc_ok = AsyncMock()
        mock_proc_ok.communicate = AsyncMock(return_value=(mock_output.encode(), b""))
        mock_proc_ok.returncode = 0

        mock_exec.side_effect = [mock_proc_fail, mock_proc_ok]

        result = await get_dns_config()
        assert result["success"] is True
        assert "8.8.8.8" in result["dns_servers"]
        assert "8.8.4.4" in result["dns_servers"]
        assert result["source"] == "resolv.conf"


# === Monitor Tests ===


@pytest.mark.asyncio
async def test_get_cpu_usage():
    """Test CPU usage monitoring."""
    from mk.server.monitor import get_cpu_usage

    loadavg = "0.50 0.75 0.60 1/200 12345"
    stat = "cpu  1000 200 300 5000 100 0 0 0 0 0\ncpu0  500 100 150 2500 50 0 0 0 0 0"
    cpuinfo = "processor\t: 0\nmodel name\t: Intel\n\nprocessor\t: 1\nmodel name\t: Intel\n"

    with patch("mk.server.monitor._read_proc_file") as mock_read:
        async def fake_read(path):
            if "loadavg" in path:
                return loadavg
            elif path == "/proc/stat":
                return stat
            elif "cpuinfo" in path:
                return cpuinfo
            return None
        mock_read.side_effect = fake_read

        with patch("mk.server.monitor.asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(return_value=(b"45000", b""))
            mock_proc.returncode = 0
            mock_exec.return_value = mock_proc

            result = await get_cpu_usage()
            assert result["success"] is True
            assert result["load_average"]["1min"] == 0.50
            assert result["cores"] == 2
            assert result["temperature_c"] == 45.0


@pytest.mark.asyncio
async def test_get_memory_usage():
    """Test memory usage monitoring."""
    from mk.server.monitor import get_memory_usage

    meminfo = (
        "MemTotal:        8000000 kB\n"
        "MemFree:         2000000 kB\n"
        "MemAvailable:    4000000 kB\n"
        "Buffers:          500000 kB\n"
        "Cached:          1500000 kB"
    )

    with patch("mk.server.monitor._read_proc_file") as mock_read:
        mock_read.return_value = meminfo

        result = await get_memory_usage()
        assert result["success"] is True
        assert result["total_kb"] == 8000000
        assert result["available_kb"] == 4000000
        assert result["usage_percent"] == 50.0


@pytest.mark.asyncio
async def test_get_uptime():
    """Test uptime reading."""
    from mk.server.monitor import get_uptime

    with patch("mk.server.monitor._read_proc_file") as mock_read:
        mock_read.return_value = "90061.23 180122.46"

        result = await get_uptime()
        assert result["success"] is True
        assert result["days"] == 1
        assert result["hours"] == 1
        assert result["minutes"] == 1


@pytest.mark.asyncio
async def test_get_disk_io():
    """Test disk I/O stats."""
    from mk.server.monitor import get_disk_io

    diskstats = "   8       0 sda 1000 200 5000 300 2000 400 8000 500 0 600 700"

    with patch("mk.server.monitor._read_proc_file") as mock_read:
        mock_read.return_value = diskstats

        result = await get_disk_io()
        assert result["success"] is True
        assert "sda" in result["devices"]
        assert result["devices"]["sda"]["reads_completed"] == 1000
        assert result["devices"]["sda"]["writes_completed"] == 2000


@pytest.mark.asyncio
async def test_get_network_throughput():
    """Test network throughput stats."""
    from mk.server.monitor import get_network_throughput

    netdev = (
        "Inter-|   Receive\n"
        " face |bytes    packets\n"
        "  eth0: 1000000  5000    0    0    0     0          0"
        "         0 2000000  3000    0    0    0     0       0          0"
    )

    with patch("mk.server.monitor._read_proc_file") as mock_read:
        mock_read.return_value = netdev

        result = await get_network_throughput()
        assert result["success"] is True
        assert "eth0" in result["interfaces"]
        assert result["interfaces"]["eth0"]["rx_bytes"] == 1000000
        assert result["interfaces"]["eth0"]["tx_bytes"] == 2000000


@pytest.mark.asyncio
async def test_get_top_processes():
    """Test getting top processes."""
    from mk.server.monitor import get_top_processes

    mock_output = (
        "root      1234  25.0  5.0 100000 50000 ?  S  Jan01 10:00 /usr/bin/plex\n"
        "nobody    5678  10.0  2.0  50000 20000 ?  S  Jan01  5:00 nginx: worker"
    )

    with patch("mk.server.monitor.asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(mock_output.encode(), b""))
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        result = await get_top_processes(count=5)
        assert result["success"] is True
        assert len(result["processes"]) == 2
        assert result["processes"][0]["cpu_percent"] == "25.0"


@pytest.mark.asyncio
async def test_health_score_green():
    """Test health score is green when everything is fine."""
    from mk.server.monitor import get_health_score

    with patch("mk.server.monitor.get_cpu_usage") as mock_cpu:
        mock_cpu.return_value = {
            "success": True,
            "load_average": {"1min": 0.5, "5min": 0.4, "15min": 0.3},
            "cores": 4,
            "temperature_c": 45.0,
        }
        with patch("mk.server.monitor.get_memory_usage") as mock_mem:
            mock_mem.return_value = {
                "success": True,
                "usage_percent": 50.0,
            }

            result = await get_health_score()
            assert result["success"] is True
            assert result["status"] == "green"
            assert result["score"] >= 70


# === Backup Tests ===


@pytest.mark.asyncio
async def test_create_backup():
    """Test creating a backup."""
    from mk.server.backup import create_backup

    with patch("mk.server.backup.asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        with patch("mk.server.backup.time.strftime", return_value="20240101_120000"):
            result = await create_backup(
                source_dirs=["/home/user/docs"],
                backup_dir="/backups",
                name="docs",
            )
            assert result["success"] is True
            assert "docs_20240101_120000" in result["filename"]
            assert result["compression"] == "gz"


@pytest.mark.asyncio
async def test_create_backup_no_sources():
    """Test create_backup rejects empty source list."""
    from mk.server.backup import create_backup

    result = await create_backup(source_dirs=[], backup_dir="/backups")
    assert result["success"] is False
    assert "No source" in result["error"]


@pytest.mark.asyncio
async def test_list_backups():
    """Test listing backups."""
    from mk.server.backup import list_backups

    with patch("mk.server.backup.asyncio.create_subprocess_exec") as mock_exec:
        mock_proc_find = AsyncMock()
        mock_proc_find.communicate = AsyncMock(return_value=(
            b"/backups/docs_20240101.tar.gz\n/backups/docs_20240102.tar.gz", b""
        ))
        mock_proc_find.returncode = 0

        mock_proc_stat = AsyncMock()
        mock_proc_stat.communicate = AsyncMock(return_value=(b"1024\n1704067200", b""))
        mock_proc_stat.returncode = 0

        mock_exec.side_effect = [mock_proc_find, mock_proc_stat, mock_proc_stat]

        result = await list_backups("/backups")
        assert result["success"] is True
        assert result["count"] == 2


@pytest.mark.asyncio
async def test_restore_backup():
    """Test restoring from backup."""
    from mk.server.backup import restore_backup

    with patch("mk.server.backup.asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        result = await restore_backup(
            backup_path="/backups/docs_20240101.tar.gz",
            restore_dir="/restore",
        )
        assert result["success"] is True
        assert result["restore_dir"] == "/restore"


@pytest.mark.asyncio
async def test_rotate_backups():
    """Test backup rotation keeps only N most recent."""
    from mk.server.backup import rotate_backups

    with patch("mk.server.backup.list_backups") as mock_list:
        mock_list.return_value = {
            "success": True,
            "backups": [
                {"path": "/b/new1.tar.gz", "filename": "new1.tar.gz",
                 "size_bytes": 100, "modified_timestamp": 3},
                {"path": "/b/new2.tar.gz", "filename": "new2.tar.gz",
                 "size_bytes": 100, "modified_timestamp": 2},
                {"path": "/b/old1.tar.gz", "filename": "old1.tar.gz",
                 "size_bytes": 100, "modified_timestamp": 1},
            ],
            "count": 3,
        }

        with patch("mk.server.backup.asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(return_value=(b"", b""))
            mock_proc.returncode = 0
            mock_exec.return_value = mock_proc

            result = await rotate_backups("/b", keep_last=2)
            assert result["success"] is True
            assert result["kept"] == 2
            assert result["deleted_count"] == 1
            assert "old1.tar.gz" in result["deleted"]


# === Services Tests ===


@pytest.mark.asyncio
async def test_list_services():
    """Test listing systemd services."""
    from mk.server.services import list_services

    mock_output = (
        "docker.service      loaded active running Docker Engine\n"
        "sshd.service        loaded active running OpenSSH server\n"
        "nginx.service       loaded active running nginx HTTP server"
    )

    with patch("mk.server.services.asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(mock_output.encode(), b""))
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        result = await list_services()
        assert result["success"] is True
        assert len(result["services"]) == 3
        assert result["services"][0]["name"] == "docker.service"
        assert result["services"][0]["active"] == "active"


@pytest.mark.asyncio
async def test_get_service_status():
    """Test getting service status."""
    from mk.server.services import get_service_status

    mock_output = (
        "ActiveState=active\n"
        "SubState=running\n"
        "LoadState=loaded\n"
        "Description=Docker Engine\n"
        "MainPID=1234\n"
        "MemoryCurrent=104857600\n"
        "ActiveEnterTimestamp=Mon 2024-01-01\n"
        "UnitFileState=enabled"
    )

    with patch("mk.server.services.asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(mock_output.encode(), b""))
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        result = await get_service_status("docker")
        assert result["success"] is True
        assert result["active_state"] == "active"
        assert result["sub_state"] == "running"
        assert result["enabled"] == "enabled"


@pytest.mark.asyncio
async def test_start_service():
    """Test starting a service."""
    from mk.server.services import start_service

    with patch("mk.server.services.asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        result = await start_service("docker")
        assert result["success"] is True
        assert result["action"] == "start"
        assert result["service"] == "docker.service"


@pytest.mark.asyncio
async def test_stop_service():
    """Test stopping a service."""
    from mk.server.services import stop_service

    with patch("mk.server.services.asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        result = await stop_service("nginx")
        assert result["success"] is True
        assert result["action"] == "stop"


@pytest.mark.asyncio
async def test_get_service_logs():
    """Test getting service logs."""
    from mk.server.services import get_service_logs

    mock_output = "Jan 01 12:00:00 server docker[1234]: Starting Docker"

    with patch("mk.server.services.asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(mock_output.encode(), b""))
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        result = await get_service_logs("docker", lines=20)
        assert result["success"] is True
        assert "Starting Docker" in result["logs"]


# === Shares Tests ===


def test_generate_share_config():
    """Test generating Samba share config."""
    from mk.server.shares import generate_share_config

    config = generate_share_config(
        name="media",
        path="/srv/media",
        comment="Media files",
        read_only=True,
        guest_ok=True,
        valid_users=["john", "jane"],
    )
    assert "[media]" in config
    assert "path = /srv/media" in config
    assert "read only = yes" in config
    assert "guest ok = yes" in config
    assert "valid users = john jane" in config
    assert "comment = Media files" in config


def test_generate_share_config_defaults():
    """Test generating config with defaults."""
    from mk.server.shares import generate_share_config

    config = generate_share_config(name="data", path="/srv/data")
    assert "[data]" in config
    assert "path = /srv/data" in config
    assert "read only = no" in config
    assert "guest ok = no" in config
    assert "browseable = yes" in config
    assert "valid users" not in config


@pytest.mark.asyncio
async def test_list_shares():
    """Test listing SMB shares."""
    from mk.server.shares import list_shares

    mock_config = (
        "[global]\n"
        "   workgroup = WORKGROUP\n"
        "\n"
        "[media]\n"
        "   path = /srv/media\n"
        "   read only = yes\n"
        "\n"
        "[backups]\n"
        "   path = /srv/backups\n"
        "   read only = no\n"
    )

    with patch("mk.server.shares.asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(mock_config.encode(), b""))
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        result = await list_shares()
        assert result["success"] is True
        assert len(result["shares"]) == 2
        share_names = [s["name"] for s in result["shares"]]
        assert "media" in share_names
        assert "backups" in share_names
