"""Tests for tool registration, discovery, and schema generation."""

from __future__ import annotations

from typing import Any, Dict

import pytest

from mk.tools.base import Tool, ToolResult
from mk.tools.registry import ToolRegistry


class MockTool(Tool):
    """A mock tool for testing."""

    @property
    def name(self) -> str:
        return "mock_tool"

    @property
    def description(self) -> str:
        return "A mock tool for testing purposes"

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "A test message",
                },
            },
            "required": ["message"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        message = kwargs.get("message", "")
        return ToolResult(
            success=True,
            output=f"Mock executed: {message}",
            metadata={"message": message},
        )


class AnotherMockTool(Tool):
    """Another mock tool for testing."""

    @property
    def name(self) -> str:
        return "another_tool"

    @property
    def description(self) -> str:
        return "Another mock tool"

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        return ToolResult(success=True, output="Another tool executed")


class TestToolRegistry:
    """Tests for the ToolRegistry class."""

    def test_empty_registry(self) -> None:
        """New registry starts empty."""
        registry = ToolRegistry()
        assert registry.tool_count == 0
        assert registry.list_tools() == []
        assert registry.get_tool_names() == []

    def test_register_tool(self) -> None:
        """Registering a tool makes it available."""
        registry = ToolRegistry()
        tool = MockTool()
        registry.register(tool)

        assert registry.tool_count == 1
        assert registry.get_tool("mock_tool") is tool

    def test_register_duplicate_raises(self) -> None:
        """Registering a duplicate tool name raises ValueError."""
        registry = ToolRegistry()
        registry.register(MockTool())

        with pytest.raises(ValueError, match="already registered"):
            registry.register(MockTool())

    def test_register_class(self) -> None:
        """register_class instantiates and registers a tool class."""
        registry = ToolRegistry()
        registry.register_class(MockTool)

        assert registry.tool_count == 1
        assert registry.get_tool("mock_tool") is not None

    def test_get_tool_not_found(self) -> None:
        """get_tool returns None for unknown tools."""
        registry = ToolRegistry()
        assert registry.get_tool("nonexistent") is None

    def test_list_tools(self) -> None:
        """list_tools returns all registered tools."""
        registry = ToolRegistry()
        registry.register(MockTool())
        registry.register(AnotherMockTool())

        tools = registry.list_tools()
        assert len(tools) == 2

    def test_get_tool_names(self) -> None:
        """get_tool_names returns all tool names."""
        registry = ToolRegistry()
        registry.register(MockTool())
        registry.register(AnotherMockTool())

        names = registry.get_tool_names()
        assert "mock_tool" in names
        assert "another_tool" in names

    def test_get_tools_prompt_empty(self) -> None:
        """get_tools_prompt with no tools returns appropriate message."""
        registry = ToolRegistry()
        prompt = registry.get_tools_prompt()
        assert "No tools available" in prompt

    def test_get_tools_prompt_with_tools(self) -> None:
        """get_tools_prompt generates formatted tool descriptions."""
        registry = ToolRegistry()
        registry.register(MockTool())

        prompt = registry.get_tools_prompt()
        assert "mock_tool" in prompt
        assert "A mock tool for testing" in prompt
        assert "message" in prompt

    def test_get_tool_definitions(self) -> None:
        """get_tool_definitions returns LLM-compatible definitions."""
        registry = ToolRegistry()
        registry.register(MockTool())

        definitions = registry.get_tool_definitions()
        assert len(definitions) == 1
        assert definitions[0]["name"] == "mock_tool"
        assert "parameters" in definitions[0]
        assert "description" in definitions[0]

    @pytest.mark.asyncio
    async def test_execute_tool_success(self) -> None:
        """execute_tool runs the specified tool."""
        registry = ToolRegistry()
        registry.register(MockTool())

        result = await registry.execute_tool("mock_tool", message="hello")
        assert result.success is True
        assert "Mock executed: hello" in result.output

    @pytest.mark.asyncio
    async def test_execute_tool_not_found(self) -> None:
        """execute_tool returns error for unknown tools."""
        registry = ToolRegistry()

        result = await registry.execute_tool("nonexistent")
        assert result.success is False
        assert "not found" in result.error

    def test_auto_discover(self) -> None:
        """auto_discover finds tool implementations."""
        registry = ToolRegistry()
        discovered = registry.auto_discover()

        # Should discover at least the core tools
        assert discovered >= 1
        assert registry.tool_count >= 1

        # Should find our known tools
        tool_names = registry.get_tool_names()
        # SSHTool requires safety_enabled param but has default, so should be found
        assert "ssh" in tool_names or "docker" in tool_names or "files" in tool_names
