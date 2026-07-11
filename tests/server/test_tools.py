"""Tests for the ServerTool routing logic."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from mk.tools.base import ToolResult
from mk.server.tools import (
    BACKUP_ACTIONS,
    CONTAINER_ACTIONS,
    NETWORK_ACTIONS,
    SERVICE_ACTIONS,
    STORAGE_ACTIONS,
    SYSTEM_ACTIONS,
    USER_ACTIONS,
    ServerTool,
    create_server_tools,
)


@pytest.fixture
def mock_server_manager():
    """Create a mock ServerManager with mock sub-managers."""
    mgr = MagicMock()
    mgr.storage = MagicMock()
    mgr.containers = MagicMock()
    mgr.network = MagicMock()
    mgr.services = MagicMock()
    mgr.backups = MagicMock()
    mgr.users = MagicMock()
    return mgr


@pytest.fixture
def server_tool(mock_server_manager):
    """Create a ServerTool instance with mocked manager."""
    return ServerTool(mock_server_manager)


class TestServerToolProperties:
    """Tests for ServerTool basic properties."""

    def test_name(self, server_tool):
        assert server_tool.name == "server"

    def test_description_is_nonempty(self, server_tool):
        assert len(server_tool.description) > 0

    def test_parameters_schema_has_domain(self, server_tool):
        schema = server_tool.parameters_schema
        assert "domain" in schema["properties"]
        assert "domain" in schema["required"]

    def test_parameters_schema_has_action(self, server_tool):
        schema = server_tool.parameters_schema
        assert "action" in schema["properties"]
        assert "action" in schema["required"]

    def test_parameters_schema_has_args(self, server_tool):
        schema = server_tool.parameters_schema
        assert "args" in schema["properties"]


class TestServerToolRouting:
    """Tests for the execute routing logic."""

    async def test_missing_domain_returns_error(self, server_tool):
        result = await server_tool.execute(action="list")
        assert result.success is False
        assert "Domain is required" in result.error

    async def test_missing_action_returns_error(self, server_tool):
        result = await server_tool.execute(domain="storage")
        assert result.success is False
        assert "Action is required" in result.error

    async def test_unknown_domain_returns_error(self, server_tool):
        result = await server_tool.execute(domain="bogus", action="list")
        assert result.success is False
        assert "Unknown domain" in result.error
        assert "bogus" in result.error

    async def test_unknown_action_returns_error(self, server_tool):
        result = await server_tool.execute(domain="storage", action="nonexistent")
        assert result.success is False
        assert "Unknown storage action" in result.error
        assert "nonexistent" in result.error

    async def test_routes_storage_list_pools(self, mock_server_manager, server_tool):
        expected = ToolResult(success=True, output="pool list")
        mock_server_manager.storage.list_pools = AsyncMock(return_value=expected)

        result = await server_tool.execute(domain="storage", action="list_pools")
        assert result.success is True
        assert result.output == "pool list"
        mock_server_manager.storage.list_pools.assert_awaited_once()

    async def test_routes_storage_create_pool_with_args(self, mock_server_manager, server_tool):
        expected = ToolResult(success=True, output="pool created")
        mock_server_manager.storage.create_pool = AsyncMock(return_value=expected)

        result = await server_tool.execute(
            domain="storage", action="create_pool", args={"name": "tank", "vdevs": "/dev/sda"}
        )
        assert result.success is True
        mock_server_manager.storage.create_pool.assert_awaited_once_with(
            name="tank", vdevs="/dev/sda"
        )

    async def test_routes_containers_list(self, mock_server_manager, server_tool):
        expected = ToolResult(success=True, output="containers")
        mock_server_manager.containers.list_containers = AsyncMock(return_value=expected)

        result = await server_tool.execute(domain="containers", action="list")
        assert result.success is True
        mock_server_manager.containers.list_containers.assert_awaited_once()

    async def test_routes_network_ping(self, mock_server_manager, server_tool):
        expected = ToolResult(success=True, output="pong")
        mock_server_manager.network.ping = AsyncMock(return_value=expected)

        result = await server_tool.execute(
            domain="network", action="ping", args={"host": "1.1.1.1"}
        )
        assert result.success is True
        mock_server_manager.network.ping.assert_awaited_once_with(host="1.1.1.1")

    async def test_routes_services_status(self, mock_server_manager, server_tool):
        expected = ToolResult(success=True, output="running")
        mock_server_manager.services.service_status = AsyncMock(return_value=expected)

        result = await server_tool.execute(
            domain="services", action="status", args={"name": "nginx"}
        )
        assert result.success is True
        mock_server_manager.services.service_status.assert_awaited_once_with(name="nginx")

    async def test_routes_backups_list_jobs(self, mock_server_manager, server_tool):
        expected = ToolResult(success=True, output="jobs")
        mock_server_manager.backups.list_jobs = AsyncMock(return_value=expected)

        result = await server_tool.execute(domain="backups", action="list_jobs")
        assert result.success is True
        mock_server_manager.backups.list_jobs.assert_awaited_once()

    async def test_routes_users_list(self, mock_server_manager, server_tool):
        expected = ToolResult(success=True, output="users")
        mock_server_manager.users.list_users = AsyncMock(return_value=expected)

        result = await server_tool.execute(domain="users", action="list")
        assert result.success is True
        mock_server_manager.users.list_users.assert_awaited_once()

    async def test_routes_system_overview(self, mock_server_manager, server_tool):
        expected = ToolResult(success=True, output="overview")
        mock_server_manager.system_overview = AsyncMock(return_value=expected)

        result = await server_tool.execute(domain="system", action="overview")
        assert result.success is True
        mock_server_manager.system_overview.assert_awaited_once()

    async def test_method_exception_returns_error(self, mock_server_manager, server_tool):
        mock_server_manager.storage.list_pools = AsyncMock(side_effect=RuntimeError("disk failure"))

        result = await server_tool.execute(domain="storage", action="list_pools")
        assert result.success is False
        assert "disk failure" in result.error

    async def test_method_not_found_returns_error(self, mock_server_manager, server_tool):
        # Simulate a method name in the action table that does not exist on the object
        mock_server_manager.storage.list_pools = None
        # getattr returns None for the method
        del mock_server_manager.storage.list_pools

        result = await server_tool.execute(domain="storage", action="list_pools")
        assert result.success is False
        assert "not found" in result.error


class TestCreateServerTools:
    """Tests for the factory function."""

    def test_returns_list_with_server_tool(self, mock_server_manager):
        tools = create_server_tools(mock_server_manager)
        assert len(tools) == 1
        assert isinstance(tools[0], ServerTool)

    def test_tool_has_correct_name(self, mock_server_manager):
        tools = create_server_tools(mock_server_manager)
        assert tools[0].name == "server"


class TestActionTables:
    """Tests verifying action table consistency."""

    def test_system_actions_nonempty(self):
        assert len(SYSTEM_ACTIONS) > 0

    def test_storage_actions_nonempty(self):
        assert len(STORAGE_ACTIONS) > 0

    def test_container_actions_nonempty(self):
        assert len(CONTAINER_ACTIONS) > 0

    def test_network_actions_nonempty(self):
        assert len(NETWORK_ACTIONS) > 0

    def test_service_actions_nonempty(self):
        assert len(SERVICE_ACTIONS) > 0

    def test_backup_actions_nonempty(self):
        assert len(BACKUP_ACTIONS) > 0

    def test_user_actions_nonempty(self):
        assert len(USER_ACTIONS) > 0

    def test_all_action_values_are_strings(self):
        for table in [
            SYSTEM_ACTIONS,
            STORAGE_ACTIONS,
            CONTAINER_ACTIONS,
            NETWORK_ACTIONS,
            SERVICE_ACTIONS,
            BACKUP_ACTIONS,
            USER_ACTIONS,
        ]:
            for key, value in table.items():
                assert isinstance(key, str), f"Key {key!r} is not a string"
                assert isinstance(value, str), f"Value {value!r} for key {key!r} is not a string"
