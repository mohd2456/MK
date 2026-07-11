"""Base classes for the MK tool system.

Defines the abstract Tool class and ToolResult model that all
tool implementations must use.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    """Result of a tool execution.

    All tools return this structured object to ensure consistent
    handling by the agent loop.
    """

    success: bool = Field(description="Whether the tool execution succeeded")
    output: str = Field(default="", description="Tool output content")
    error: Optional[str] = Field(default=None, description="Error message if execution failed")
    side_effects: List[str] = Field(
        default_factory=list,
        description="Description of side effects (e.g., 'file created at /tmp/x')",
    )
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional result metadata")


class Tool(ABC):
    """Abstract base class for all MK tools.

    All tool implementations must subclass this and provide:
    - name: unique tool identifier
    - description: human-readable description for LLM prompts
    - parameters_schema: JSON Schema describing accepted parameters
    - execute(): async method that performs the tool action
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this tool."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description for LLM prompt generation."""
        ...

    @property
    @abstractmethod
    def parameters_schema(self) -> Dict[str, Any]:
        """JSON Schema describing the tool's parameters.

        Should follow standard JSON Schema format with type,
        properties, and required fields.
        """
        ...

    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute the tool with the given arguments.

        Args:
            **kwargs: Tool-specific arguments matching the parameters_schema.

        Returns:
            ToolResult with success/failure status and output.
        """
        ...

    def get_definition(self) -> Dict[str, Any]:
        """Get the tool definition for LLM prompt generation.

        Returns:
            Dictionary with name, description, and parameters schema
            suitable for inclusion in LLM tool definitions.
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters_schema,
        }
