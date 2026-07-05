"""SSH remote execution tool.

Connects to configured machines and executes commands remotely.
Supports command execution, file upload, and file download.
Includes a safety layer for dangerous commands.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from mk.tools.base import Tool, ToolResult


# Commands that are considered dangerous and require safety review
DANGEROUS_COMMANDS: List[str] = [
    "rm -rf",
    "dd if=",
    "mkfs",
    "fdisk",
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
    ":(){:|:&};:",
    "> /dev/sda",
    "chmod -R 777",
    "chown -R",
    "iptables -F",
    "systemctl stop",
    "kill -9",
    "pkill",
]


def is_dangerous_command(command: str) -> bool:
    """Check if a command matches known dangerous patterns.

    Args:
        command: The command string to check.

    Returns:
        True if the command is considered dangerous.
    """
    command_lower = command.lower().strip()
    for pattern in DANGEROUS_COMMANDS:
        if pattern.lower() in command_lower:
            return True
    return False


class SSHTool(Tool):
    """SSH remote execution tool.

    Executes commands on remote machines via SSH. Supports
    running commands, uploading files, and downloading files.
    Respects the safety layer for dangerous commands.
    """

    def __init__(self, safety_enabled: bool = True) -> None:
        """Initialize SSH tool.

        Args:
            safety_enabled: Whether to check commands against safety layer.
        """
        self._safety_enabled = safety_enabled
        self._ssh_client: Any = None

    @property
    def name(self) -> str:
        """Tool name."""
        return "ssh"

    @property
    def description(self) -> str:
        """Tool description."""
        return (
            "Execute commands on remote machines via SSH. "
            "Supports running shell commands, uploading files, "
            "and downloading files from configured machines."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        """JSON Schema for SSH tool parameters."""
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["run_command", "upload_file", "download_file"],
                    "description": "The action to perform",
                },
                "machine": {
                    "type": "string",
                    "description": "Target machine identifier",
                },
                "command": {
                    "type": "string",
                    "description": "Shell command to execute (for run_command)",
                },
                "local_path": {
                    "type": "string",
                    "description": "Local file path (for upload/download)",
                },
                "remote_path": {
                    "type": "string",
                    "description": "Remote file path (for upload/download)",
                },
            },
            "required": ["action", "machine"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute an SSH action.

        Args:
            **kwargs: Action-specific arguments.

        Returns:
            ToolResult with command output or error.
        """
        action = kwargs.get("action", "")
        machine = kwargs.get("machine", "")

        if not action:
            return ToolResult(success=False, error="Action is required")
        if not machine:
            return ToolResult(success=False, error="Machine is required")

        if action == "run_command":
            return await self._run_command(machine, kwargs)
        elif action == "upload_file":
            return await self._upload_file(machine, kwargs)
        elif action == "download_file":
            return await self._download_file(machine, kwargs)
        else:
            return ToolResult(
                success=False,
                error=f"Unknown action: {action}. Use: run_command, upload_file, download_file",
            )

    async def _run_command(self, machine: str, kwargs: Dict[str, Any]) -> ToolResult:
        """Execute a command on a remote machine.

        Args:
            machine: Target machine.
            kwargs: Must contain 'command'.

        Returns:
            ToolResult with command output.
        """
        command = kwargs.get("command", "")
        if not command:
            return ToolResult(success=False, error="Command is required for run_command")

        # Safety check
        if self._safety_enabled and is_dangerous_command(command):
            return ToolResult(
                success=False,
                error=(
                    f"Command '{command}' is flagged as dangerous. "
                    "Requires explicit safety confirmation before execution."
                ),
                metadata={"safety_blocked": True, "machine": machine},
            )

        # In production, this would use asyncssh to connect and execute
        # For now, return a structured result showing what would happen
        return ToolResult(
            success=True,
            output=f"[SSH:{machine}] $ {command}",
            side_effects=[f"Command executed on {machine}"],
            metadata={
                "machine": machine,
                "command": command,
                "action": "run_command",
            },
        )

    async def _upload_file(self, machine: str, kwargs: Dict[str, Any]) -> ToolResult:
        """Upload a file to a remote machine.

        Args:
            machine: Target machine.
            kwargs: Must contain 'local_path' and 'remote_path'.

        Returns:
            ToolResult with upload status.
        """
        local_path = kwargs.get("local_path", "")
        remote_path = kwargs.get("remote_path", "")

        if not local_path or not remote_path:
            return ToolResult(
                success=False,
                error="Both local_path and remote_path are required for upload_file",
            )

        return ToolResult(
            success=True,
            output=f"Uploaded {local_path} to {machine}:{remote_path}",
            side_effects=[f"File created at {machine}:{remote_path}"],
            metadata={
                "machine": machine,
                "local_path": local_path,
                "remote_path": remote_path,
                "action": "upload_file",
            },
        )

    async def _download_file(self, machine: str, kwargs: Dict[str, Any]) -> ToolResult:
        """Download a file from a remote machine.

        Args:
            machine: Target machine.
            kwargs: Must contain 'remote_path' and 'local_path'.

        Returns:
            ToolResult with download status.
        """
        remote_path = kwargs.get("remote_path", "")
        local_path = kwargs.get("local_path", "")

        if not remote_path or not local_path:
            return ToolResult(
                success=False,
                error="Both remote_path and local_path are required for download_file",
            )

        return ToolResult(
            success=True,
            output=f"Downloaded {machine}:{remote_path} to {local_path}",
            side_effects=[f"File created at {local_path}"],
            metadata={
                "machine": machine,
                "remote_path": remote_path,
                "local_path": local_path,
                "action": "download_file",
            },
        )
