"""Tests for Docker tool with mocked API calls."""

from __future__ import annotations

import pytest

from mk.tools.docker import DockerTool


class TestDockerTool:
    """Tests for the DockerTool class."""

    def test_tool_properties(self) -> None:
        """Tool has correct name, description, and schema."""
        tool = DockerTool()
        assert tool.name == "docker"
        assert "container" in tool.description.lower() or "Docker" in tool.description
        schema = tool.parameters_schema
        assert "properties" in schema
        assert "action" in schema["properties"]

    @pytest.mark.asyncio
    async def test_list_containers(self) -> None:
        """list_containers returns successfully."""
        tool = DockerTool()
        result = await tool.execute(action="list_containers", machine="media-server")
        assert result.success is True
        assert "media-server" in result.output or "media-server" in str(result.metadata)

    @pytest.mark.asyncio
    async def test_start_container(self) -> None:
        """start_container with valid name succeeds."""
        tool = DockerTool()
        result = await tool.execute(
            action="start_container",
            machine="media-server",
            container_name="plex",
        )
        assert result.success is True
        assert "plex" in result.output
        assert "start" in result.output.lower() or "Started" in result.output

    @pytest.mark.asyncio
    async def test_start_container_missing_name(self) -> None:
        """start_container without name returns error."""
        tool = DockerTool()
        result = await tool.execute(action="start_container", machine="server1")
        assert result.success is False
        assert "container_name" in result.error

    @pytest.mark.asyncio
    async def test_stop_container(self) -> None:
        """stop_container with valid name succeeds."""
        tool = DockerTool()
        result = await tool.execute(
            action="stop_container",
            machine="media-server",
            container_name="sonarr",
        )
        assert result.success is True
        assert "sonarr" in result.output
        assert len(result.side_effects) > 0

    @pytest.mark.asyncio
    async def test_restart_container(self) -> None:
        """restart_container with valid name succeeds."""
        tool = DockerTool()
        result = await tool.execute(
            action="restart_container",
            machine="media-server",
            container_name="radarr",
        )
        assert result.success is True
        assert "radarr" in result.output

    @pytest.mark.asyncio
    async def test_container_logs(self) -> None:
        """container_logs returns log output."""
        tool = DockerTool()
        result = await tool.execute(
            action="container_logs",
            machine="media-server",
            container_name="nginx",
            lines=50,
        )
        assert result.success is True
        assert "nginx" in result.output
        assert result.metadata.get("lines") == 50

    @pytest.mark.asyncio
    async def test_container_logs_missing_name(self) -> None:
        """container_logs without container name returns error."""
        tool = DockerTool()
        result = await tool.execute(action="container_logs", machine="server1")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_deploy_compose(self) -> None:
        """deploy_compose with content succeeds."""
        tool = DockerTool()
        compose_yaml = "version: '3'\nservices:\n  web:\n    image: nginx"
        result = await tool.execute(
            action="deploy_compose",
            machine="web-server",
            compose_content=compose_yaml,
        )
        assert result.success is True
        assert "web-server" in result.output
        assert len(result.side_effects) > 0

    @pytest.mark.asyncio
    async def test_deploy_compose_missing_content(self) -> None:
        """deploy_compose without content returns error."""
        tool = DockerTool()
        result = await tool.execute(action="deploy_compose", machine="server1")
        assert result.success is False
        assert "compose_content" in result.error

    @pytest.mark.asyncio
    async def test_unknown_action(self) -> None:
        """Unknown action returns error."""
        tool = DockerTool()
        result = await tool.execute(action="destroy_all")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_missing_action(self) -> None:
        """Missing action returns error."""
        tool = DockerTool()
        result = await tool.execute(machine="server1")
        assert result.success is False

    def test_get_definition(self) -> None:
        """get_definition returns proper structure."""
        tool = DockerTool()
        definition = tool.get_definition()
        assert definition["name"] == "docker"
        assert "parameters" in definition
        actions = definition["parameters"]["properties"]["action"]["enum"]
        assert "list_containers" in actions
        assert "deploy_compose" in actions

    @pytest.mark.asyncio
    async def test_all_results_are_tool_result(self) -> None:
        """All actions return proper ToolResult objects."""
        tool = DockerTool()

        results = [
            await tool.execute(action="list_containers"),
            await tool.execute(action="start_container", container_name="x"),
            await tool.execute(action="stop_container", container_name="x"),
            await tool.execute(action="restart_container", container_name="x"),
            await tool.execute(action="container_logs", container_name="x"),
            await tool.execute(action="deploy_compose", compose_content="x"),
        ]

        for result in results:
            assert hasattr(result, "success")
            assert hasattr(result, "output")
            assert hasattr(result, "error")
            assert hasattr(result, "side_effects")
