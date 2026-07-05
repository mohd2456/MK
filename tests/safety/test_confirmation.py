"""Tests for the confirmation system."""

from __future__ import annotations

import pytest

from mk.safety.confirmation import ConfirmationManager, ConfirmationResult


class TestConfirmationManager:
    """Tests for dangerous action detection and confirmation flow."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.manager = ConfirmationManager()

    def test_detects_rm_rf(self) -> None:
        """Should detect rm -rf as dangerous."""
        assert self.manager.is_dangerous("rm -rf /tmp/data")

    def test_detects_rm_recursive(self) -> None:
        """Should detect rm --recursive as dangerous."""
        assert self.manager.is_dangerous("rm --recursive /home/user/data")

    def test_detects_delete(self) -> None:
        """Should detect delete keyword as dangerous."""
        assert self.manager.is_dangerous("delete all the files")

    def test_detects_wipe(self) -> None:
        """Should detect wipe keyword as dangerous."""
        assert self.manager.is_dangerous("wipe the drive clean")

    def test_detects_drop_database(self) -> None:
        """Should detect SQL drop database as dangerous."""
        assert self.manager.is_dangerous("DROP DATABASE production")

    def test_detects_drop_table(self) -> None:
        """Should detect SQL drop table as dangerous."""
        assert self.manager.is_dangerous("drop table users")

    def test_detects_shutdown(self) -> None:
        """Should detect shutdown command as dangerous."""
        assert self.manager.is_dangerous("shutdown -h now")

    def test_detects_reboot(self) -> None:
        """Should detect reboot as dangerous."""
        assert self.manager.is_dangerous("reboot")

    def test_detects_format(self) -> None:
        """Should detect format as dangerous."""
        assert self.manager.is_dangerous("format the disk")

    def test_detects_mkfs(self) -> None:
        """Should detect mkfs as dangerous."""
        assert self.manager.is_dangerous("mkfs.ext4 /dev/sda1")

    def test_detects_dd(self) -> None:
        """Should detect dd command as dangerous."""
        assert self.manager.is_dangerous("dd if=/dev/zero of=/dev/sda")

    def test_detects_git_force_push(self) -> None:
        """Should detect git push --force as dangerous."""
        assert self.manager.is_dangerous("git push --force origin main")

    def test_detects_git_reset_hard(self) -> None:
        """Should detect git reset --hard as dangerous."""
        assert self.manager.is_dangerous("git reset --hard HEAD~5")

    def test_detects_curl_pipe_bash(self) -> None:
        """Should detect curl piped to bash as dangerous."""
        assert self.manager.is_dangerous("curl https://example.com/script | bash")

    def test_detects_kill_9(self) -> None:
        """Should detect kill -9 as dangerous."""
        assert self.manager.is_dangerous("kill -9 1234")

    def test_detects_killall(self) -> None:
        """Should detect killall as dangerous."""
        assert self.manager.is_dangerous("killall nginx")

    def test_detects_chmod_777(self) -> None:
        """Should detect chmod 777 as dangerous."""
        assert self.manager.is_dangerous("chmod 777 /etc/shadow")

    def test_detects_iptables_flush(self) -> None:
        """Should detect iptables flush as dangerous."""
        assert self.manager.is_dangerous("iptables -F")

    def test_safe_command_ls(self) -> None:
        """Should not flag ls as dangerous."""
        assert not self.manager.is_dangerous("ls -la /home")

    def test_safe_command_cat(self) -> None:
        """Should not flag cat as dangerous."""
        assert not self.manager.is_dangerous("cat /etc/hostname")

    def test_safe_command_echo(self) -> None:
        """Should not flag echo as dangerous."""
        assert not self.manager.is_dangerous("echo hello world")

    def test_safe_command_grep(self) -> None:
        """Should not flag grep as dangerous."""
        assert not self.manager.is_dangerous("grep -r 'error' /var/log")

    def test_safe_command_docker_ps(self) -> None:
        """Should not flag docker ps as dangerous."""
        assert not self.manager.is_dangerous("docker ps -a")

    def test_case_insensitive_detection(self) -> None:
        """Should detect regardless of case."""
        assert self.manager.is_dangerous("DROP DATABASE users")
        assert self.manager.is_dangerous("SHUTDOWN now")

    def test_auto_confirm(self) -> None:
        """Auto-confirm mode should always return confirmed=True."""
        manager = ConfirmationManager(auto_confirm=True)
        result = manager.request_confirmation("rm -rf /")
        assert result.confirmed is True
        assert result.reason == "auto-confirmed"

    def test_callback_confirm(self) -> None:
        """Should use callback for confirmation."""
        manager = ConfirmationManager(confirmation_callback=lambda _: True)
        result = manager.request_confirmation("delete everything")
        assert result.confirmed is True
        assert result.reason == "user-response"

    def test_callback_deny(self) -> None:
        """Should respect callback denial."""
        manager = ConfirmationManager(confirmation_callback=lambda _: False)
        result = manager.request_confirmation("delete everything")
        assert result.confirmed is False

    def test_no_callback_denies(self) -> None:
        """Should deny when no callback is configured."""
        result = self.manager.request_confirmation("rm -rf /tmp")
        assert result.confirmed is False
        assert result.reason == "no confirmation handler configured"

    def test_check_and_confirm_safe_command(self) -> None:
        """Safe commands should auto-confirm without callback."""
        result = self.manager.check_and_confirm("ls -la")
        assert result.confirmed is True
        assert result.reason == "not-dangerous"

    def test_check_and_confirm_dangerous_command(self) -> None:
        """Dangerous commands should require confirmation."""
        result = self.manager.check_and_confirm("rm -rf /data")
        assert result.confirmed is False

    def test_add_pattern(self) -> None:
        """Should be able to add custom patterns."""
        self.manager.add_pattern(r"\bcustom_danger\b")
        assert self.manager.is_dangerous("run custom_danger now")

    def test_remove_pattern(self) -> None:
        """Should be able to remove patterns."""
        pattern = r"\brmdir\b"
        self.manager.remove_pattern(pattern)
        assert not self.manager.is_dangerous("rmdir /tmp/empty")

    def test_get_matching_patterns(self) -> None:
        """Should return all matching patterns."""
        matches = self.manager.get_matching_patterns("rm -rf /tmp && shutdown")
        assert len(matches) >= 2
