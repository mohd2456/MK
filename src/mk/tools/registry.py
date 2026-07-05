"""Auto-discovery tool registry.

Loads all tool implementations from the tools package and
provides access by name, listing, and prompt generation.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from typing import Any, Dict, List, Optional, Type

from mk.tools.base import Tool, ToolResult


class ToolRegistry:
    """Registry for discovering and managing tools.

    Supports both manual registration and auto-discovery of
    tool classes from the mk.tools package. Provides methods
    for looking up tools by name and generating tool descriptions
    for LLM prompts.
    """

    def __init__(self) -> None:
        """Initialize an empty tool registry."""
        self._tools: Dict[str, Tool] = {}

    @property
    def tool_count(self) -> int:
        """Return the number of registered tools."""
        return len(self._tools)

    def register(self, tool: Tool) -> None:
        """Register a tool instance.

        Args:
            tool: Tool instance to register.

        Raises:
            ValueError: If a tool with the same name is already registered.
        """
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")
        self._tools[tool.name] = tool

    def register_class(self, tool_class: Type[Tool], **kwargs: Any) -> None:
        """Register a tool by its class, instantiating it.

        Args:
            tool_class: Tool class to instantiate and register.
            **kwargs: Arguments to pass to the tool constructor.
        """
        tool = tool_class(**kwargs)
        self.register(tool)

    def get_tool(self, name: str) -> Optional[Tool]:
        """Get a registered tool by name.

        Args:
            name: The tool name to look up.

        Returns:
            The tool instance, or None if not found.
        """
        return self._tools.get(name)

    def list_tools(self) -> List[Tool]:
        """List all registered tools.

        Returns:
            List of all registered Tool instances.
        """
        return list(self._tools.values())

    def get_tool_names(self) -> List[str]:
        """Get the names of all registered tools.

        Returns:
            List of tool name strings.
        """
        return list(self._tools.keys())

    def get_tools_prompt(self) -> str:
        """Generate a prompt section describing all available tools.

        Creates a formatted string suitable for inclusion in an
        LLM system prompt that describes all registered tools
        and their parameters.

        Returns:
            Formatted string describing all tools.
        """
        if not self._tools:
            return "No tools available."

        lines = ["Available tools:"]
        for tool in self._tools.values():
            lines.append(f"\n## {tool.name}")
            lines.append(f"{tool.description}")
            schema = tool.parameters_schema
            if schema.get("properties"):
                lines.append("Parameters:")
                for param_name, param_info in schema["properties"].items():
                    param_type = param_info.get("type", "any")
                    param_desc = param_info.get("description", "")
                    required = param_name in schema.get("required", [])
                    req_str = " (required)" if required else " (optional)"
                    lines.append(f"  - {param_name}: {param_type}{req_str} - {param_desc}")

        return "\n".join(lines)

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Get tool definitions for LLM function calling.

        Returns:
            List of tool definition dictionaries.
        """
        return [tool.get_definition() for tool in self._tools.values()]

    async def execute_tool(self, name: str, **kwargs: Any) -> ToolResult:
        """Execute a tool by name with the given arguments.

        Args:
            name: Name of the tool to execute.
            **kwargs: Arguments to pass to the tool.

        Returns:
            ToolResult from the tool execution.
        """
        tool = self.get_tool(name)
        if tool is None:
            return ToolResult(
                success=False,
                error=f"Tool '{name}' not found. Available tools: {', '.join(self.get_tool_names())}",
            )
        return await tool.execute(**kwargs)

    def auto_discover(self) -> int:
        """Auto-discover and register all Tool subclasses from mk.tools.

        Scans all modules in the mk.tools package for classes that
        subclass Tool (excluding Tool itself) and registers them.

        Returns:
            Number of tools discovered and registered.
        """
        import mk.tools as tools_package

        discovered = 0

        for importer, module_name, is_pkg in pkgutil.iter_modules(
            tools_package.__path__, prefix="mk.tools."
        ):
            # Skip base, registry, and __init__
            if module_name in ("mk.tools.base", "mk.tools.registry"):
                continue

            try:
                module = importlib.import_module(module_name)
            except ImportError:
                continue

            for _, obj in inspect.getmembers(module, inspect.isclass):
                if (
                    issubclass(obj, Tool)
                    and obj is not Tool
                    and not inspect.isabstract(obj)
                    and obj.name.fget is not None  # type: ignore[attr-defined]
                ):
                    # Try to instantiate (only no-arg constructors)
                    try:
                        instance = obj()
                        if instance.name not in self._tools:
                            self.register(instance)
                            discovered += 1
                    except TypeError:
                        # Tool requires constructor args, skip auto-discovery
                        pass

        return discovered
