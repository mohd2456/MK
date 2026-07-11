"""Tests for the audit logging system."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path


from mk.safety.audit import AuditLogger


class TestAuditLogger:
    """Tests for audit logging write and query."""

    def setup_method(self) -> None:
        """Set up test fixtures with a temp directory."""
        self._temp_dir = tempfile.mkdtemp()
        self.logger = AuditLogger(log_dir=self._temp_dir)

    def test_log_action_creates_entry(self) -> None:
        """Should create an audit entry with all fields."""
        entry = self.logger.log_action(
            action="test_action",
            params={"key": "value"},
            result="success",
            initiator="user",
        )
        assert entry.action == "test_action"
        assert entry.params == {"key": "value"}
        assert entry.result == "success"
        assert entry.initiator == "user"
        assert entry.success is True

    def test_log_action_writes_to_file(self) -> None:
        """Should write entry to the JSONL file."""
        self.logger.log_action(action="file_test", params={}, result="ok")

        log_path = Path(self._temp_dir) / "audit.jsonl"
        assert log_path.exists()

        content = log_path.read_text()
        lines = content.strip().split("\n")
        assert len(lines) == 1

        data = json.loads(lines[0])
        assert data["action"] == "file_test"

    def test_log_multiple_actions(self) -> None:
        """Should append multiple entries."""
        self.logger.log_action(action="action_1")
        self.logger.log_action(action="action_2")
        self.logger.log_action(action="action_3")

        log_path = Path(self._temp_dir) / "audit.jsonl"
        content = log_path.read_text()
        lines = content.strip().split("\n")
        assert len(lines) == 3

    def test_get_recent_actions(self) -> None:
        """Should return the N most recent actions."""
        for i in range(5):
            self.logger.log_action(action=f"action_{i}")

        recent = self.logger.get_recent_actions(n=3)
        assert len(recent) == 3
        assert recent[0].action == "action_2"
        assert recent[2].action == "action_4"

    def test_get_recent_actions_empty(self) -> None:
        """Should return empty list when no logs exist."""
        recent = self.logger.get_recent_actions()
        assert recent == []

    def test_search_actions_by_action_name(self) -> None:
        """Should find entries matching action name."""
        self.logger.log_action(action="ssh_connect", params={"host": "server1"})
        self.logger.log_action(action="file_read", params={"path": "/tmp"})
        self.logger.log_action(action="ssh_disconnect", params={"host": "server1"})

        results = self.logger.search_actions("ssh")
        assert len(results) == 2

    def test_search_actions_by_params(self) -> None:
        """Should find entries matching parameter content."""
        self.logger.log_action(action="execute", params={"cmd": "docker ps"})
        self.logger.log_action(action="execute", params={"cmd": "ls -la"})

        results = self.logger.search_actions("docker")
        assert len(results) == 1
        assert results[0].params["cmd"] == "docker ps"

    def test_search_actions_empty_result(self) -> None:
        """Should return empty list when nothing matches."""
        self.logger.log_action(action="test")
        results = self.logger.search_actions("nonexistent")
        assert results == []

    def test_get_actions_by_initiator(self) -> None:
        """Should filter by initiator."""
        self.logger.log_action(action="a1", initiator="user")
        self.logger.log_action(action="a2", initiator="system")
        self.logger.log_action(action="a3", initiator="user")

        user_actions = self.logger.get_actions_by_initiator("user")
        assert len(user_actions) == 2
        assert all(a.initiator == "user" for a in user_actions)

    def test_log_failure(self) -> None:
        """Should properly record failed actions."""
        entry = self.logger.log_action(
            action="deploy",
            params={"target": "prod"},
            result="connection timeout",
            success=False,
        )
        assert entry.success is False
        assert entry.result == "connection timeout"

    def test_log_with_duration(self) -> None:
        """Should record action duration."""
        entry = self.logger.log_action(
            action="slow_operation",
            duration_ms=1500.5,
        )
        assert entry.duration_ms == 1500.5

    def test_clear_removes_log(self) -> None:
        """Should remove the log file on clear."""
        self.logger.log_action(action="test")
        self.logger.clear()

        log_path = Path(self._temp_dir) / "audit.jsonl"
        assert not log_path.exists()

    def test_rotation_on_large_file(self) -> None:
        """Should rotate when file exceeds max size."""
        # Set a very small rotation threshold
        self.logger.max_file_size_bytes = 100

        # Write enough to exceed 100 bytes
        for i in range(10):
            self.logger.log_action(
                action=f"action_{i}",
                params={"data": "x" * 50},
            )

        # Check that a rotated file exists
        log_dir = Path(self._temp_dir)
        rotated_files = list(log_dir.glob("audit_*.jsonl"))
        assert len(rotated_files) >= 1

    def test_timestamp_is_iso_format(self) -> None:
        """Should use ISO format timestamps."""
        entry = self.logger.log_action(action="test")
        # Verify it can be parsed as ISO
        from datetime import datetime

        datetime.fromisoformat(entry.timestamp)
