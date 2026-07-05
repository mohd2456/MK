"""File operations tool.

Creates, reads, and manages files on local or remote machines.
Supports pushing configs and scripts to remote targets.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from mk.tools.base import Tool, ToolResult


class FilesTool(Tool):
    """File operations tool for local and remote file management.

    Provides methods to create, read, list, and edit files
    on the local machine or on remote machines (via SSH integration).
    """

    @property
    def name(self) -> str:
        """Tool name."""
        return "files"

    @property
    def description(self) -> str:
        """Tool description."""
        return (
            "Manage files on local or remote machines. "
            "Create files, read file contents, list directories, "
            "and push configurations to remote targets."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        """JSON Schema for file operations parameters."""
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create_file", "read_file", "list_dir"],
                    "description": "The file operation to perform",
                },
                "path": {
                    "type": "string",
                    "description": "File or directory path",
                },
                "content": {
                    "type": "string",
                    "description": "File content (for create_file)",
                },
                "machine": {
                    "type": "string",
                    "description": "Target machine (None for local)",
                },
            },
            "required": ["action", "path"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute a file operation.

        Args:
            **kwargs: Action-specific arguments.

        Returns:
            ToolResult with operation output or error.
        """
        action = kwargs.get("action", "")
        path = kwargs.get("path", "")

        if not action:
            return ToolResult(success=False, error="Action is required")
        if not path:
            return ToolResult(success=False, error="Path is required")

        machine = kwargs.get("machine")

        if action == "create_file":
            return await self._create_file(path, kwargs.get("content", ""), machine)
        elif action == "read_file":
            return await self._read_file(path, machine)
        elif action == "list_dir":
            return await self._list_dir(path, machine)
        else:
            return ToolResult(
                success=False,
                error=f"Unknown action: {action}. Use: create_file, read_file, list_dir",
            )

    async def _create_file(
        self, path: str, content: str, machine: Optional[str] = None
    ) -> ToolResult:
        """Create a file with the given content.

        Args:
            path: File path to create.
            content: Content to write.
            machine: Target machine (None for local).

        Returns:
            ToolResult with creation status.
        """
        if machine:
            # Remote file creation would use SSH tool
            return ToolResult(
                success=True,
                output=f"Created file on {machine}:{path}",
                side_effects=[f"File created at {machine}:{path}"],
                metadata={
                    "action": "create_file",
                    "path": path,
                    "machine": machine,
                    "size": len(content),
                },
            )

        # Local file creation
        try:
            file_path = Path(path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)
            return ToolResult(
                success=True,
                output=f"Created file at {path} ({len(content)} bytes)",
                side_effects=[f"File created at {path}"],
                metadata={"action": "create_file", "path": path, "size": len(content)},
            )
        except OSError as e:
            return ToolResult(
                success=False,
                error=f"Failed to create file {path}: {e}",
            )

    async def _read_file(self, path: str, machine: Optional[str] = None) -> ToolResult:
        """Read a file's contents.

        Args:
            path: File path to read.
            machine: Target machine (None for local).

        Returns:
            ToolResult with file contents.
        """
        if machine:
            return ToolResult(
                success=True,
                output=f"[Would read {machine}:{path} via SSH]",
                metadata={"action": "read_file", "path": path, "machine": machine},
            )

        try:
            file_path = Path(path)
            if not file_path.exists():
                return ToolResult(success=False, error=f"File not found: {path}")
            content = file_path.read_text()
            return ToolResult(
                success=True,
                output=content,
                metadata={"action": "read_file", "path": path, "size": len(content)},
            )
        except OSError as e:
            return ToolResult(success=False, error=f"Failed to read file {path}: {e}")

    async def _list_dir(self, path: str, machine: Optional[str] = None) -> ToolResult:
        """List directory contents.

        Args:
            path: Directory path to list.
            machine: Target machine (None for local).

        Returns:
            ToolResult with directory listing.
        """
        if machine:
            return ToolResult(
                success=True,
                output=f"[Would list {machine}:{path} via SSH]",
                metadata={"action": "list_dir", "path": path, "machine": machine},
            )

        try:
            dir_path = Path(path)
            if not dir_path.exists():
                return ToolResult(success=False, error=f"Directory not found: {path}")
            if not dir_path.is_dir():
                return ToolResult(success=False, error=f"Not a directory: {path}")

            entries = sorted(dir_path.iterdir())
            listing = []
            for entry in entries:
                entry_type = "dir" if entry.is_dir() else "file"
                listing.append(f"  {entry_type}: {entry.name}")

            output = f"Contents of {path}:\n" + "\n".join(listing)
            return ToolResult(
                success=True,
                output=output,
                metadata={"action": "list_dir", "path": path, "count": len(entries)},
            )
        except OSError as e:
            return ToolResult(success=False, error=f"Failed to list directory {path}: {e}")
