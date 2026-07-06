"""Tests for server module imports and public API integrity."""

from __future__ import annotations

import importlib


class TestServerImports:
    """Tests that all server modules import cleanly."""

    def test_import_server_package(self):
        import mk.server

    def test_import_shell_module(self):
        import mk.server._shell

    def test_import_tools_module(self):
        import mk.server.tools

    def test_import_manager_module(self):
        import mk.server.manager

    def test_import_storage_module(self):
        import mk.server.storage

    def test_import_containers_module(self):
        import mk.server.containers

    def test_import_network_module(self):
        import mk.server.network

    def test_import_services_module(self):
        import mk.server.services

    def test_import_backups_module(self):
        import mk.server.backups

    def test_import_users_module(self):
        import mk.server.users

    def test_import_models_module(self):
        import mk.server.models


class TestServerPublicAPI:
    """Tests that __all__ is complete and correct."""

    def test_all_is_defined(self):
        import mk.server
        assert hasattr(mk.server, "__all__")

    def test_all_contains_server_manager(self):
        from mk.server import __all__
        assert "ServerManager" in __all__

    def test_all_contains_storage_manager(self):
        from mk.server import __all__
        assert "StorageManager" in __all__

    def test_all_contains_container_manager(self):
        from mk.server import __all__
        assert "ContainerManager" in __all__

    def test_all_contains_network_manager(self):
        from mk.server import __all__
        assert "NetworkManager" in __all__

    def test_all_contains_service_manager(self):
        from mk.server import __all__
        assert "ServiceManager" in __all__

    def test_all_contains_backup_manager(self):
        from mk.server import __all__
        assert "BackupManager" in __all__

    def test_all_contains_user_manager(self):
        from mk.server import __all__
        assert "UserManager" in __all__

    def test_all_contains_server_tool(self):
        from mk.server import __all__
        assert "ServerTool" in __all__

    def test_all_contains_create_server_tools(self):
        from mk.server import __all__
        assert "create_server_tools" in __all__

    def test_all_exports_are_importable(self):
        """Every name in __all__ should be importable from the package."""
        import mk.server
        for name in mk.server.__all__:
            obj = getattr(mk.server, name, None)
            assert obj is not None, f"{name} listed in __all__ but not importable"

    def test_no_unexpected_exports(self):
        """__all__ should only contain known public names."""
        from mk.server import __all__
        expected = {
            "ServerManager",
            "StorageManager",
            "ContainerManager",
            "NetworkManager",
            "ServiceManager",
            "BackupManager",
            "UserManager",
            "VMManager",
            "LXCManager",
            "HomelabManager",
            "DiscRipper",
            "ServerTool",
            "create_server_tools",
        }
        assert set(__all__) == expected
