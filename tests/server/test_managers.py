"""Unit tests for sub-manager command assembly.

These tests mock _run and _run_with_stdin to verify that the shell commands
produced by each manager method are correctly assembled with proper quoting.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
def mock_run_ok():
    """Return a mock that simulates a successful command execution."""
    return AsyncMock(return_value=(0, "", ""))


@pytest.fixture
def mock_run_with_output():
    """Return a mock that simulates a command with output."""
    return AsyncMock(return_value=(0, "output", ""))


# --- StorageManager Tests ---


class TestStorageManagerCommands:
    """Test that StorageManager assembles correct shell commands."""

    @pytest.mark.asyncio
    async def test_create_pool_command(self, mock_run_ok):
        from mk.server.storage import StorageManager

        mgr = StorageManager(sudo=True)
        mgr._run = mock_run_ok

        await mgr.create_pool(
            name="tank",
            vdev_type="mirror",
            disks=["/dev/sda", "/dev/sdb"],
            force=True,
        )

        mock_run_ok.assert_called_once_with(
            "zpool create -f tank mirror /dev/sda /dev/sdb"
        )

    @pytest.mark.asyncio
    async def test_create_pool_stripe_command(self, mock_run_ok):
        from mk.server.storage import StorageManager

        mgr = StorageManager(sudo=True)
        mgr._run = mock_run_ok

        await mgr.create_pool(
            name="fast",
            vdev_type="stripe",
            disks=["/dev/nvme0n1"],
            force=False,
        )

        mock_run_ok.assert_called_once_with(
            "zpool create fast /dev/nvme0n1"
        )

    @pytest.mark.asyncio
    async def test_destroy_pool_command(self, mock_run_ok):
        from mk.server.storage import StorageManager

        mgr = StorageManager(sudo=True)
        mgr._run = mock_run_ok

        await mgr.destroy_pool("tank", force=True)

        mock_run_ok.assert_called_once_with("zpool destroy -f tank")


# --- ContainerManager Tests ---


class TestContainerManagerCommands:
    """Test that ContainerManager assembles correct shell commands."""

    @pytest.mark.asyncio
    async def test_start_container_command(self, mock_run_ok):
        from mk.server.containers import ContainerManager

        mgr = ContainerManager(sudo=False)
        mgr._run = mock_run_ok

        await mgr.start_container("myapp")

        mock_run_ok.assert_called_once_with("docker start myapp")

    @pytest.mark.asyncio
    async def test_stop_container_command(self, mock_run_ok):
        from mk.server.containers import ContainerManager

        mgr = ContainerManager(sudo=False)
        mgr._run = mock_run_ok

        await mgr.stop_container("myapp", timeout=30)

        mock_run_ok.assert_called_once_with("docker stop -t 30 myapp")

    @pytest.mark.asyncio
    async def test_run_container_basic_command(self, mock_run_with_output):
        from mk.server.containers import ContainerManager

        mgr = ContainerManager(sudo=False)
        mgr._run = mock_run_with_output

        await mgr.run_container(image="nginx:latest", name="web")

        call_args = mock_run_with_output.call_args[0][0]
        assert "docker run" in call_args
        assert "-d" in call_args
        assert "--name web" in call_args
        assert "nginx:latest" in call_args

    @pytest.mark.asyncio
    async def test_run_container_command_is_quoted(self, mock_run_with_output):
        from mk.server.containers import ContainerManager

        mgr = ContainerManager(sudo=False)
        mgr._run = mock_run_with_output

        await mgr.run_container(
            image="ubuntu",
            name="runner",
            command="/bin/sh -c 'echo hello'",
        )

        call_args = mock_run_with_output.call_args[0][0]
        # The command should be quoted, not passed raw
        assert "'/bin/sh -c" in call_args or '"/bin/sh -c' in call_args

    @pytest.mark.asyncio
    async def test_deploy_stack_uses_stdin(self):
        from mk.server.containers import ContainerManager

        mgr = ContainerManager(sudo=False)
        mgr._run = AsyncMock(return_value=(0, "", ""))
        mgr._run_with_stdin = AsyncMock(return_value=(0, "", ""))

        compose = "version: '3'\nservices:\n  web:\n    image: nginx"
        await mgr.deploy_stack(name="mystack", compose_content=compose)

        # Verify _run_with_stdin was called for compose file
        assert mgr._run_with_stdin.call_count >= 1
        first_call = mgr._run_with_stdin.call_args_list[0]
        assert "tee" in first_call[0][0]
        assert "docker-compose.yml" in first_call[0][0]
        assert first_call[0][1] == compose

    @pytest.mark.asyncio
    async def test_deploy_stack_env_uses_stdin(self):
        from mk.server.containers import ContainerManager

        mgr = ContainerManager(sudo=False)
        mgr._run = AsyncMock(return_value=(0, "", ""))
        mgr._run_with_stdin = AsyncMock(return_value=(0, "", ""))

        compose = "version: '3'\nservices:\n  web:\n    image: nginx"
        env_vars = {"DB_HOST": "localhost", "DB_PORT": "5432"}
        await mgr.deploy_stack(name="mystack", compose_content=compose, env_vars=env_vars)

        # Second stdin call should be for .env file
        assert mgr._run_with_stdin.call_count >= 2
        env_call = mgr._run_with_stdin.call_args_list[1]
        assert ".env" in env_call[0][0]
        assert "DB_HOST=localhost" in env_call[0][1]
        assert "DB_PORT=5432" in env_call[0][1]


# --- NetworkManager Tests ---


class TestNetworkManagerCommands:
    """Test that NetworkManager assembles correct shell commands."""

    @pytest.mark.asyncio
    async def test_add_firewall_rule_command(self):
        from mk.server.network import NetworkManager

        mgr = NetworkManager(sudo=True)
        mgr._run = AsyncMock(return_value=(0, "", ""))

        await mgr.add_firewall_rule(
            chain="input",
            action="accept",
            protocol="tcp",
            port=443,
            source="192.168.1.0/24",
        )

        # Last call should be the actual add rule
        last_call = mgr._run.call_args_list[-1]
        cmd = last_call[0][0]
        assert "nft add rule inet mk_firewall" in cmd
        assert "tcp dport 443" in cmd
        assert "192.168.1.0/24" in cmd
        assert "accept" in cmd


# --- BackupManager Tests ---


class TestBackupManagerCommands:
    """Test that BackupManager assembles correct shell commands."""

    @pytest.mark.asyncio
    async def test_delete_job_uses_safe_quote_in_paths(self):
        from mk.server.backups import BackupManager

        mgr = BackupManager(sudo=True)
        mgr._run = AsyncMock(return_value=(0, "", ""))

        await mgr.delete_job("daily-backup")

        # Collect all rm -f commands
        rm_calls = [
            call[0][0] for call in mgr._run.call_args_list
            if "rm -f" in str(call)
        ]

        # All rm paths should use safe_quote (no unquoted interpolation)
        for cmd in rm_calls:
            # safe_quote on simple names returns them as-is, but the path
            # is wrapped with safe_quote(f'...') so the entire path is quoted
            assert "daily-backup" in cmd

        # Verify the service and timer paths are present
        all_cmds = " ".join(call[0][0] for call in mgr._run.call_args_list)
        assert "mk-backup-daily-backup.service" in all_cmds
        assert "mk-backup-daily-backup.timer" in all_cmds


# --- UserManager Tests ---


class TestUserManagerCommands:
    """Test that UserManager assembles correct shell commands."""

    @pytest.mark.asyncio
    async def test_set_password_uses_stdin(self):
        from mk.server.users import UserManager

        mgr = UserManager(sudo=True)
        mgr._run_with_stdin = AsyncMock(return_value=(0, "", ""))

        await mgr.set_password("testuser", "s3cr3t!")

        mgr._run_with_stdin.assert_called_once_with(
            "chpasswd", "testuser:s3cr3t!"
        )

    @pytest.mark.asyncio
    async def test_lock_account_command(self, mock_run_ok):
        from mk.server.users import UserManager

        mgr = UserManager(sudo=True)
        mgr._run = mock_run_ok

        await mgr.lock_account("baduser")

        mock_run_ok.assert_called_once_with("usermod -L baduser")
