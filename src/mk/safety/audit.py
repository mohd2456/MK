"""Audit logging system for MK.

Records every action MK takes with timestamp, action type, parameters,
result, and initiator. Writes to structured JSON log files with automatic
rotation when files get large.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AuditEntry(BaseModel):
    """A single audit log entry."""

    timestamp: str = Field(description="ISO format timestamp")
    action: str = Field(description="Action type or name")
    params: Dict[str, Any] = Field(default_factory=dict, description="Action parameters")
    result: str = Field(default="", description="Action result summary")
    initiator: str = Field(default="system", description="Who initiated the action")
    success: bool = Field(default=True, description="Whether the action succeeded")
    duration_ms: Optional[float] = Field(
        default=None, description="Action duration in milliseconds"
    )


@dataclass
class AuditLogger:
    """Structured audit logger with JSON output and rotation.

    Logs every action to a JSON lines file, supporting querying
    and automatic rotation when the log file exceeds a size threshold.

    Attributes:
        log_dir: Directory to store audit log files.
        max_file_size_bytes: Maximum size before rotating (default 10MB).
        current_file: Name of the current log file.
    """

    log_dir: str = field(default_factory=lambda: os.path.expanduser("~/.mk/audit"))
    max_file_size_bytes: int = 10 * 1024 * 1024  # 10MB

    def __post_init__(self) -> None:
        """Ensure the log directory exists."""
        Path(self.log_dir).mkdir(parents=True, exist_ok=True)

    @property
    def _current_log_path(self) -> Path:
        """Get the path to the current active log file."""
        return Path(self.log_dir) / "audit.jsonl"

    def _rotate_if_needed(self) -> None:
        """Rotate the log file if it exceeds the size threshold."""
        log_path = self._current_log_path
        if log_path.exists() and log_path.stat().st_size >= self.max_file_size_bytes:
            # Rotate: rename with timestamp
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            rotated_name = f"audit_{ts}.jsonl"
            log_path.rename(Path(self.log_dir) / rotated_name)

    def log_action(
        self,
        action: str,
        params: Optional[Dict[str, Any]] = None,
        result: str = "",
        initiator: str = "system",
        success: bool = True,
        duration_ms: Optional[float] = None,
    ) -> AuditEntry:
        """Log an action to the audit trail.

        Args:
            action: The action type or name (e.g., 'tool_execute', 'ssh_connect').
            params: Parameters passed to the action.
            result: Brief summary of the result.
            initiator: Who or what initiated the action (user, system, schedule).
            success: Whether the action completed successfully.
            duration_ms: How long the action took in milliseconds.

        Returns:
            The created AuditEntry.
        """
        self._rotate_if_needed()

        entry = AuditEntry(
            timestamp=datetime.utcnow().isoformat(),
            action=action,
            params=params or {},
            result=result,
            initiator=initiator,
            success=success,
            duration_ms=duration_ms,
        )

        with open(self._current_log_path, "a", encoding="utf-8") as f:
            f.write(entry.model_dump_json() + "\n")

        return entry

    def get_recent_actions(self, n: int = 10) -> List[AuditEntry]:
        """Get the N most recent audit entries.

        Args:
            n: Number of recent entries to retrieve.

        Returns:
            List of AuditEntry objects, most recent last.
        """
        log_path = self._current_log_path
        if not log_path.exists():
            return []

        entries: List[AuditEntry] = []
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # Take the last N lines
        for line in lines[-n:]:
            line = line.strip()
            if line:
                data = json.loads(line)
                entries.append(AuditEntry(**data))

        return entries

    def search_actions(self, query: str) -> List[AuditEntry]:
        """Search audit entries by action name or parameter content.

        Args:
            query: Search string to match against action names and params.

        Returns:
            List of matching AuditEntry objects.
        """
        log_path = self._current_log_path
        if not log_path.exists():
            return []

        results: List[AuditEntry] = []
        query_lower = query.lower()

        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if query_lower in line.lower():
                    data = json.loads(line)
                    results.append(AuditEntry(**data))

        return results

    def get_actions_by_initiator(self, initiator: str) -> List[AuditEntry]:
        """Get all actions initiated by a specific source.

        Args:
            initiator: The initiator to filter by.

        Returns:
            List of matching AuditEntry objects.
        """
        log_path = self._current_log_path
        if not log_path.exists():
            return []

        results: List[AuditEntry] = []
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                if data.get("initiator") == initiator:
                    results.append(AuditEntry(**data))

        return results

    def clear(self) -> None:
        """Clear all audit logs. Use with caution."""
        log_path = self._current_log_path
        if log_path.exists():
            log_path.unlink()
