"""Change preview — show exactly what will change before execution.

Before MK executes anything that modifies state, the change preview
system generates a human-readable diff showing:
- What will be created/modified/deleted
- What policies apply
- Whether a snapshot will be taken
- How to undo the change

This turns "confirm before rm -rf" into "here's exactly what
will be deleted, and here's how to restore it."
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ChangeType(str, Enum):
    """Types of changes MK can make."""

    CREATE = "create"       # Creating something new
    MODIFY = "modify"       # Changing existing state
    DELETE = "delete"       # Removing something
    RESTART = "restart"     # Restarting a service/container
    EXECUTE = "execute"     # Running a command
    TRANSFER = "transfer"   # Moving/copying files


@dataclass
class Change:
    """A single atomic change in a preview.

    Describes one thing that will change, what it is now,
    and what it will become.
    """

    change_type: ChangeType
    target: str              # What is being changed
    description: str         # Human-readable description
    before: Optional[str] = None  # Current state (if applicable)
    after: Optional[str] = None   # New state (if applicable)
    reversible: bool = True  # Whether this can be undone
    risk_level: str = "low"  # low, medium, high, critical

    def format(self) -> str:
        """Format the change for display."""
        icons = {
            ChangeType.CREATE: "➕",
            ChangeType.MODIFY: "📝",
            ChangeType.DELETE: "🗑️",
            ChangeType.RESTART: "🔄",
            ChangeType.EXECUTE: "⚡",
            ChangeType.TRANSFER: "📦",
        }
        icon = icons.get(self.change_type, "•")
        reversible_mark = "" if self.reversible else " ⚠️ IRREVERSIBLE"

        lines = [f"{icon} {self.description}{reversible_mark}"]
        lines.append(f"   Target: {self.target}")
        if self.before:
            lines.append(f"   Before: {self.before}")
        if self.after:
            lines.append(f"   After:  {self.after}")
        return "\n".join(lines)


@dataclass
class ChangePreview:
    """Complete preview of all changes an operation will make.

    Generated before execution so the user (or the critique gate)
    can review exactly what will happen.
    """

    title: str
    changes: List[Change] = field(default_factory=list)
    policies_applied: List[str] = field(default_factory=list)
    snapshot_planned: bool = False
    snapshot_targets: List[str] = field(default_factory=list)
    rollback_available: bool = False
    estimated_duration: Optional[str] = None
    created_at: float = field(default_factory=time.time)

    @property
    def change_count(self) -> int:
        """Total number of changes."""
        return len(self.changes)

    @property
    def has_destructive(self) -> bool:
        """Whether any changes are destructive/irreversible."""
        return any(
            not c.reversible or c.change_type == ChangeType.DELETE
            for c in self.changes
        )

    @property
    def has_high_risk(self) -> bool:
        """Whether any changes are high risk."""
        return any(
            c.risk_level in ("high", "critical")
            for c in self.changes
        )

    @property
    def risk_summary(self) -> str:
        """One-line risk summary."""
        if self.has_high_risk:
            return "HIGH RISK — contains irreversible or dangerous changes"
        if self.has_destructive:
            return "MODERATE — contains deletions (snapshot planned)"
        return "LOW RISK — all changes are reversible"

    def add_change(self, change: Change) -> None:
        """Add a change to the preview."""
        self.changes.append(change)

    def format(self) -> str:
        """Format the complete preview for display."""
        lines = [f"📋 **Change Preview: {self.title}**"]
        lines.append(f"   Risk: {self.risk_summary}")
        lines.append(f"   Changes: {self.change_count}")
        if self.estimated_duration:
            lines.append(f"   Estimated time: {self.estimated_duration}")
        lines.append("")

        # Changes grouped by type
        for change in self.changes:
            lines.append(change.format())
            lines.append("")

        # Policies
        if self.policies_applied:
            lines.append("📜 Policies applied:")
            for p in self.policies_applied:
                lines.append(f"   • {p}")
            lines.append("")

        # Snapshot info
        if self.snapshot_planned:
            lines.append("📸 Pre-execution snapshot planned:")
            for target in self.snapshot_targets:
                lines.append(f"   • {target}")
            lines.append("   (Rollback available if anything goes wrong)")
        elif self.rollback_available:
            lines.append("🔄 Rollback available from existing snapshot")

        return "\n".join(lines)

    def format_compact(self) -> str:
        """Compact format for Telegram/chat notifications."""
        lines = [f"**{self.title}** ({self.change_count} changes)"]
        lines.append(self.risk_summary)

        for change in self.changes[:5]:  # Max 5 in compact mode
            icons = {
                ChangeType.CREATE: "+",
                ChangeType.MODIFY: "~",
                ChangeType.DELETE: "-",
                ChangeType.RESTART: "↺",
                ChangeType.EXECUTE: "!",
                ChangeType.TRANSFER: ">",
            }
            icon = icons.get(change.change_type, "•")
            reversible = "" if change.reversible else " ⚠️"
            lines.append(f"  {icon} {change.description}{reversible}")

        if len(self.changes) > 5:
            lines.append(f"  ...and {len(self.changes) - 5} more")

        if self.snapshot_planned:
            lines.append("📸 Snapshot will be taken before execution")

        return "\n".join(lines)


def generate_preview(
    title: str,
    tool: str,
    action: str,
    args: Dict[str, Any],
    policies: Optional[List[str]] = None,
) -> ChangePreview:
    """Generate a change preview for a tool call.

    Analyzes the tool and action to determine what changes
    will be made, and packages them into a ChangePreview.

    Args:
        title: Operation title.
        tool: Tool being used.
        action: Action being performed.
        args: Tool arguments.
        policies: Policies that apply.

    Returns:
        ChangePreview for the operation.
    """
    preview = ChangePreview(
        title=title,
        policies_applied=policies or [],
    )

    # Infer changes from tool + action
    if tool == "docker":
        _preview_docker(preview, action, args)
    elif tool == "ssh":
        _preview_ssh(preview, action, args)
    elif tool == "files":
        _preview_files(preview, action, args)
    elif tool == "media":
        _preview_media(preview, action, args)
    else:
        # Generic
        preview.add_change(Change(
            change_type=ChangeType.EXECUTE,
            target=f"{tool}.{action}",
            description=f"Execute {tool}.{action}",
        ))

    return preview


def _preview_docker(preview: ChangePreview, action: str, args: Dict[str, Any]) -> None:
    """Generate preview for Docker operations."""
    container = args.get("container_name", args.get("container", "unknown"))

    if action in ("stop_container", "stop"):
        preview.add_change(Change(
            change_type=ChangeType.MODIFY,
            target=f"container:{container}",
            description=f"Stop container '{container}'",
            before="running",
            after="stopped",
            risk_level="medium",
        ))

    elif action in ("restart_container", "restart"):
        preview.add_change(Change(
            change_type=ChangeType.RESTART,
            target=f"container:{container}",
            description=f"Restart container '{container}' (brief downtime)",
            risk_level="low",
        ))

    elif action in ("start_container", "start"):
        preview.add_change(Change(
            change_type=ChangeType.MODIFY,
            target=f"container:{container}",
            description=f"Start container '{container}'",
            before="stopped",
            after="running",
            risk_level="low",
        ))

    elif action == "deploy_compose":
        preview.add_change(Change(
            change_type=ChangeType.CREATE,
            target=f"container:{container}",
            description=f"Deploy new container configuration",
            risk_level="medium",
        ))
        preview.snapshot_planned = True
        preview.snapshot_targets.append(f"docker-compose state")


def _preview_ssh(preview: ChangePreview, action: str, args: Dict[str, Any]) -> None:
    """Generate preview for SSH/command operations."""
    command = args.get("command", "")
    machine = args.get("machine", "local")

    if "rm " in command:
        preview.add_change(Change(
            change_type=ChangeType.DELETE,
            target=f"{machine}:{command}",
            description=f"Delete files on {machine}",
            reversible="rf" not in command,
            risk_level="high" if "-rf" in command else "medium",
        ))
        preview.snapshot_planned = True

    elif any(x in command for x in ("mv ", "cp ", "rsync")):
        preview.add_change(Change(
            change_type=ChangeType.TRANSFER,
            target=f"{machine}:{command}",
            description=f"Transfer files on {machine}",
            risk_level="low",
        ))

    else:
        preview.add_change(Change(
            change_type=ChangeType.EXECUTE,
            target=f"{machine}",
            description=f"Run command on {machine}: {command[:60]}",
            risk_level="low",
        ))


def _preview_files(preview: ChangePreview, action: str, args: Dict[str, Any]) -> None:
    """Generate preview for file operations."""
    path = args.get("path", "unknown")

    if action == "create_file":
        preview.add_change(Change(
            change_type=ChangeType.CREATE,
            target=path,
            description=f"Create file: {path}",
            risk_level="low",
        ))
    elif action == "read_file":
        # Read doesn't change state
        pass


def _preview_media(preview: ChangePreview, action: str, args: Dict[str, Any]) -> None:
    """Generate preview for media operations."""
    if action in ("request_movie", "request_show"):
        title = args.get("title", args.get("query", "unknown"))
        preview.add_change(Change(
            change_type=ChangeType.CREATE,
            target="download_queue",
            description=f"Add '{title}' to download queue",
            risk_level="low",
        ))
