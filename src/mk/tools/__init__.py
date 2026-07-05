"""Tool system for MK.

Provides an extensible tool framework with auto-discovery,
abstract base class, and registry. Core tools include SSH,
file operations, Docker management, media services, and
system monitoring.
"""

from mk.tools.base import Tool, ToolResult
from mk.tools.registry import ToolRegistry

__all__ = [
    "Tool",
    "ToolResult",
    "ToolRegistry",
]
