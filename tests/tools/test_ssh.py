"""Tests for SSH tool with mocked connections."""

from __future__ import annotations

import pytest

from mk.tools.ssh import SSHTool, is_dangerous_command


class TestIsDangerousCommand:
    """Tests for the dangerous command detection."""

    def test_safe_command(self) -> None:
        """Normal commands are not flagged."""
        assert not is_dangerous_command("ls -la")
        assert not is_dangerous_command("cat /etc/hostname")
        assert not is_dangerous_command("docker ps")
        assert not is_dangerous_command("systemctl status nginx")

    def test_rm_rf_dangerous(self) -> None:
        """rm -rf is flagged as dangerous."""
        assert is_dangerous_command("rm -rf /")
        assert is_dangerous_command("rm -rf /home/user")
        assert is_dangerous_command("sudo rm -rf /var")

    def test_dd_dangerous(self) -> None:
        """dd with if= is flagged as dangerous."""
        assert is_dangerous_command("dd if=/dev/zero of=/dev/sda")

    def test_mkfs_dangerous(self) -> None:
        """mkfs commands are flagged."""
        assert is_dangerous_command("mkfs.ext4 /dev/sda1")

    def test_shutdown_dangerous(self) -> None:
        """shutdown/reboot/halt are flagged."""
        assert is_dangerous_command("shutdown -h now")
        assert is_dangerous_command("reboot")
        assert is_dangerous_command("halt")
        assert is_dangerous_command("poweroff")

    def test_iptables_flush_dangerous(self) -> None:
        """Flushing iptables is flagged."""
        assert is_dangerous_command("iptables -F")

    def test_kill_9_dangerous(self) -> None:
        """kill -9 is flagged."""
        assert is_dangerous_command("kill -9 1234")
        assert is_dangerous_command("pkill nginx")


class TestSSHTool:
    """Tests for the SSHTool class."""

    def test_tool_properties(self) -> None:
        """Tool has correct name, description, and schema."""
        tool = SSHTool()
        assert tool.name == "ssh"
        assert "remote" in tool.description.lower() or "SSH" in tool.description
        assert "properties" in tool.parameters_schema
        assert "machine" in tool.parameters_schema["properties"]

    @pytest.mark.asyncio
    async def test_run_command_success(self) -> None:
        """Running a safe command succeeds."""
        tool = SSHTool(safety_enabled=True)
        result = await tool.execute(
            action="run_command",
            machine="test-server",
            command="ls -la /home",
        )
        assert result.success is True
        assert "test-server" in result.output
        assert "ls -la /home" in result.output

    @pytest.mark.asyncio
    async def test_run_command_safety_blocked(self) -> None:
        """Dangerous commands are blocked by safety layer."""
        tool = SSHTool(safety_enabled=True)
        result = await tool.execute(
            action="run_command",
            machine="test-server",
            command="rm -rf /",
        )
        assert result.success is False
        assert "dangerous" in result.error.lower()
        assert result.metadata.get("safety_blocked") is True

    @pytest.mark.asyncio
    async def test_run_command_safety_disabled(self) -> None:
        """With safety disabled, dangerous commands are allowed."""
        tool = SSHTool(safety_enabled=False)
        result = await tool.execute(
            action="run_command",
            machine="test-server",
            command="rm -rf /tmp/test",
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_run_command_missing_command(self) -> None:
        """Missing command parameter returns error."""
        tool = SSHTool()
        result = await tool.execute(action="run_command", machine="server1")
        assert result.success is False
        assert "required" in result.error.lower()

    @pytest.mark.asyncio
    async def test_upload_file(self) -> None:
        """Upload file action works correctly."""
        tool = SSHTool()
        result = await tool.execute(
            action="upload_file",
            machine="test-server",
            local_path="/tmp/config.yaml",
            remote_path="/etc/myapp/config.yaml",
        )
        assert result.success is True
        assert "upload" in result.output.lower() or "Uploaded" in result.output
        assert "test-server" in result.metadata["machine"]

    @pytest.mark.asyncio
    async def test_upload_file_missing_paths(self) -> None:
        """Upload without paths returns error."""
        tool = SSHTool()
        result = await tool.execute(
            action="upload_file",
            machine="test-server",
        )
        assert result.success is False

    @pytest.mark.asyncio
    async def test_download_file(self) -> None:
        """Download file action works correctly."""
        tool = SSHTool()
        result = await tool.execute(
            action="download_file",
            machine="test-server",
            remote_path="/var/log/app.log",
            local_path="/tmp/app.log",
        )
        assert result.success is True
        assert "Download" in result.output or "download" in result.output

    @pytest.mark.asyncio
    async def test_missing_action(self) -> None:
        """Missing action returns error."""
        tool = SSHTool()
        result = await tool.execute(machine="server1")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_missing_machine(self) -> None:
        """Missing machine returns error."""
        tool = SSHTool()
        result = await tool.execute(action="run_command")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_unknown_action(self) -> None:
        """Unknown action returns error."""
        tool = SSHTool()
        result = await tool.execute(action="explode", machine="server1")
        assert result.success is False
        assert "Unknown action" in result.error

    def test_get_definition(self) -> None:
        """get_definition returns proper structure."""
        tool = SSHTool()
        definition = tool.get_definition()
        assert definition["name"] == "ssh"
        assert "description" in definition
        assert "parameters" in definition
