"""Server management tools registration for MK's tool system.

Exposes the ServerManager's capabilities as Tool instances that
MK's agent loop can discover, reason about, and execute.

These tools are the bridge between natural language requests
and actual server operations.
"""

from __future__ import annotations

from typing import Any, Dict, List

from mk.tools.base import Tool, ToolResult

from .manager import ServerManager


class ServerTool(Tool):
    """Unified server management tool.

    A single tool that routes to the appropriate sub-manager
    based on the 'domain' and 'action' parameters. This keeps
    the LLM's tool list clean while exposing all server operations.
    """

    def __init__(self, server_manager: ServerManager) -> None:
        """Initialize with a ServerManager instance.

        Args:
            server_manager: The initialized ServerManager.
        """
        self._mgr = server_manager

    @property
    def name(self) -> str:
        return "server"

    @property
    def description(self) -> str:
        return (
            "Manage the server: storage (ZFS pools, datasets, snapshots, shares), "
            "containers (Docker lifecycle, compose stacks), "
            "network (interfaces, firewall, DNS, WireGuard VPN), "
            "services (systemd units, timers, logs), "
            "backups (scheduled jobs, restore points, replication), "
            "users (accounts, groups, SSH keys, ACLs), "
            "and system (overview, health, power, updates, hardware)."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "enum": [
                        "system", "storage", "containers",
                        "network", "services", "backups", "users",
                    ],
                    "description": "Server management domain",
                },
                "action": {
                    "type": "string",
                    "description": "Action to perform within the domain",
                },
                "args": {
                    "type": "object",
                    "description": "Action-specific arguments",
                },
            },
            "required": ["domain", "action"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Route to the appropriate sub-manager action.

        Args:
            **kwargs: Must include 'domain' and 'action', optionally 'args'.

        Returns:
            ToolResult from the executed action.
        """
        domain = kwargs.get("domain", "")
        action = kwargs.get("action", "")
        args = kwargs.get("args", {})

        if not domain:
            return ToolResult(success=False, error="Domain is required")
        if not action:
            return ToolResult(success=False, error="Action is required")

        # Route to the appropriate handler
        router = {
            "system": self._handle_system,
            "storage": self._handle_storage,
            "containers": self._handle_containers,
            "network": self._handle_network,
            "services": self._handle_services,
            "backups": self._handle_backups,
            "users": self._handle_users,
        }

        handler = router.get(domain)
        if not handler:
            return ToolResult(
                success=False,
                error=f"Unknown domain '{domain}'. Use: {', '.join(router.keys())}",
            )

        try:
            return await handler(action, args)
        except Exception as e:
            logger.error(f"Server tool error: {domain}.{action} - {e}")
            return ToolResult(success=False, error=f"Error in {domain}.{action}: {str(e)}")


    async def _handle_system(self, action: str, args: Dict[str, Any]) -> ToolResult:
        """Handle system-level actions."""
        actions = {
            "overview": lambda: self._mgr.system_overview(),
            "health": lambda: self._mgr.health_report(),
            "hardware": lambda: self._mgr.hardware_info(),
            "reboot": lambda: self._mgr.reboot(**args),
            "shutdown": lambda: self._mgr.shutdown(**args),
            "cancel_shutdown": lambda: self._mgr.cancel_shutdown(),
            "check_updates": lambda: self._mgr.check_updates(),
            "apply_updates": lambda: self._mgr.apply_updates(**args),
            "quick_deploy": lambda: self._mgr.quick_deploy_app(**args),
        }
        fn = actions.get(action)
        if not fn:
            return ToolResult(
                success=False,
                error=f"Unknown system action '{action}'. Available: {', '.join(actions.keys())}",
            )
        return await fn()

    async def _handle_storage(self, action: str, args: Dict[str, Any]) -> ToolResult:
        """Handle storage actions."""
        actions = {
            "list_pools": lambda: self._mgr.storage.list_pools(),
            "pool_status": lambda: self._mgr.storage.pool_status(**args),
            "create_pool": lambda: self._mgr.storage.create_pool(**args),
            "destroy_pool": lambda: self._mgr.storage.destroy_pool(**args),
            "scrub_pool": lambda: self._mgr.storage.scrub_pool(**args),
            "list_datasets": lambda: self._mgr.storage.list_datasets(**args),
            "create_dataset": lambda: self._mgr.storage.create_dataset(**args),
            "destroy_dataset": lambda: self._mgr.storage.destroy_dataset(**args),
            "set_property": lambda: self._mgr.storage.set_property(**args),
            "list_snapshots": lambda: self._mgr.storage.list_snapshots(**args),
            "create_snapshot": lambda: self._mgr.storage.create_snapshot(**args),
            "rollback_snapshot": lambda: self._mgr.storage.rollback_snapshot(**args),
            "destroy_snapshot": lambda: self._mgr.storage.destroy_snapshot(**args),
            "list_shares": lambda: self._mgr.storage.list_shares(),
            "create_smb_share": lambda: self._mgr.storage.create_smb_share(**args),
            "create_nfs_share": lambda: self._mgr.storage.create_nfs_share(**args),
            "remove_share": lambda: self._mgr.storage.remove_share(**args),
            "list_disks": lambda: self._mgr.storage.list_disks(),
            "disk_smart": lambda: self._mgr.storage.disk_smart_health(**args),
            "send_snapshot": lambda: self._mgr.storage.send_snapshot(**args),
        }
        fn = actions.get(action)
        if not fn:
            return ToolResult(
                success=False,
                error=f"Unknown storage action '{action}'. Available: {', '.join(actions.keys())}",
            )
        return await fn()

    async def _handle_containers(self, action: str, args: Dict[str, Any]) -> ToolResult:
        """Handle container actions."""
        actions = {
            "list": lambda: self._mgr.containers.list_containers(**args),
            "stats": lambda: self._mgr.containers.container_stats(**args),
            "start": lambda: self._mgr.containers.start_container(**args),
            "stop": lambda: self._mgr.containers.stop_container(**args),
            "restart": lambda: self._mgr.containers.restart_container(**args),
            "remove": lambda: self._mgr.containers.remove_container(**args),
            "logs": lambda: self._mgr.containers.container_logs(**args),
            "inspect": lambda: self._mgr.containers.inspect_container(**args),
            "run": lambda: self._mgr.containers.run_container(**args),
            "list_stacks": lambda: self._mgr.containers.list_stacks(),
            "deploy_stack": lambda: self._mgr.containers.deploy_stack(**args),
            "update_stack": lambda: self._mgr.containers.update_stack(**args),
            "destroy_stack": lambda: self._mgr.containers.destroy_stack(**args),
            "stack_logs": lambda: self._mgr.containers.stack_logs(**args),
            "list_images": lambda: self._mgr.containers.list_images(),
            "pull_image": lambda: self._mgr.containers.pull_image(**args),
            "prune_images": lambda: self._mgr.containers.prune_images(**args),
            "list_volumes": lambda: self._mgr.containers.list_volumes(),
            "create_volume": lambda: self._mgr.containers.create_volume(**args),
            "list_networks": lambda: self._mgr.containers.list_networks(),
            "create_network": lambda: self._mgr.containers.create_network(**args),
            "system_prune": lambda: self._mgr.containers.system_prune(**args),
            "disk_usage": lambda: self._mgr.containers.disk_usage(),
        }
        fn = actions.get(action)
        if not fn:
            return ToolResult(
                success=False,
                error=f"Unknown container action '{action}'. Available: {', '.join(actions.keys())}",
            )
        return await fn()


    async def _handle_network(self, action: str, args: Dict[str, Any]) -> ToolResult:
        """Handle network actions."""
        actions = {
            "list_interfaces": lambda: self._mgr.network.list_interfaces(),
            "interface_status": lambda: self._mgr.network.interface_status(**args),
            "set_ip": lambda: self._mgr.network.set_ip_address(**args),
            "interface_up": lambda: self._mgr.network.bring_interface_up(**args),
            "interface_down": lambda: self._mgr.network.bring_interface_down(**args),
            "create_vlan": lambda: self._mgr.network.create_vlan(**args),
            "create_bridge": lambda: self._mgr.network.create_bridge(**args),
            "firewall_status": lambda: self._mgr.network.firewall_status(),
            "add_firewall_rule": lambda: self._mgr.network.add_firewall_rule(**args),
            "remove_firewall_rule": lambda: self._mgr.network.remove_firewall_rule(**args),
            "add_port_forward": lambda: self._mgr.network.add_port_forward(**args),
            "get_dns": lambda: self._mgr.network.get_dns_config(),
            "set_dns": lambda: self._mgr.network.set_dns_servers(**args),
            "wireguard_status": lambda: self._mgr.network.wireguard_status(),
            "create_wireguard": lambda: self._mgr.network.create_wireguard_interface(**args),
            "add_wg_peer": lambda: self._mgr.network.add_wireguard_peer(**args),
            "remove_wg_peer": lambda: self._mgr.network.remove_wireguard_peer(**args),
            "generate_wg_config": lambda: self._mgr.network.generate_peer_config(**args),
            "ping": lambda: self._mgr.network.ping(**args),
            "traceroute": lambda: self._mgr.network.traceroute(**args),
            "dns_lookup": lambda: self._mgr.network.dns_lookup(**args),
            "port_scan": lambda: self._mgr.network.port_scan(**args),
        }
        fn = actions.get(action)
        if not fn:
            return ToolResult(
                success=False,
                error=f"Unknown network action '{action}'. Available: {', '.join(actions.keys())}",
            )
        return await fn()

    async def _handle_services(self, action: str, args: Dict[str, Any]) -> ToolResult:
        """Handle service actions."""
        actions = {
            "list": lambda: self._mgr.services.list_services(**args),
            "status": lambda: self._mgr.services.service_status(**args),
            "start": lambda: self._mgr.services.start_service(**args),
            "stop": lambda: self._mgr.services.stop_service(**args),
            "restart": lambda: self._mgr.services.restart_service(**args),
            "reload": lambda: self._mgr.services.reload_service(**args),
            "enable": lambda: self._mgr.services.enable_service(**args),
            "disable": lambda: self._mgr.services.disable_service(**args),
            "logs": lambda: self._mgr.services.service_logs(**args),
            "system_logs": lambda: self._mgr.services.system_logs(**args),
            "create": lambda: self._mgr.services.create_service(**args),
            "delete": lambda: self._mgr.services.delete_service(**args),
            "list_timers": lambda: self._mgr.services.list_timers(),
            "create_timer": lambda: self._mgr.services.create_timer(**args),
            "failed": lambda: self._mgr.services.failed_services(),
            "boot_analysis": lambda: self._mgr.services.system_boot_time(),
            "daemon_reload": lambda: self._mgr.services.reload_daemon(),
        }
        fn = actions.get(action)
        if not fn:
            return ToolResult(
                success=False,
                error=f"Unknown service action '{action}'. Available: {', '.join(actions.keys())}",
            )
        return await fn()

    async def _handle_backups(self, action: str, args: Dict[str, Any]) -> ToolResult:
        """Handle backup actions."""
        actions = {
            "list_jobs": lambda: self._mgr.backups.list_jobs(),
            "create_job": lambda: self._mgr.backups.create_job(**args),
            "delete_job": lambda: self._mgr.backups.delete_job(**args),
            "run_backup": lambda: self._mgr.backups.run_backup(**args),
            "apply_retention": lambda: self._mgr.backups.apply_retention(**args),
            "list_restore_points": lambda: self._mgr.backups.list_restore_points(**args),
            "restore": lambda: self._mgr.backups.restore(**args),
            "verify": lambda: self._mgr.backups.verify_backup(**args),
            "health": lambda: self._mgr.backups.health_check(),
        }
        fn = actions.get(action)
        if not fn:
            return ToolResult(
                success=False,
                error=f"Unknown backup action '{action}'. Available: {', '.join(actions.keys())}",
            )
        return await fn()

    async def _handle_users(self, action: str, args: Dict[str, Any]) -> ToolResult:
        """Handle user/identity actions."""
        actions = {
            "list": lambda: self._mgr.users.list_users(**args),
            "info": lambda: self._mgr.users.user_info(**args),
            "create": lambda: self._mgr.users.create_user(**args),
            "delete": lambda: self._mgr.users.delete_user(**args),
            "modify": lambda: self._mgr.users.modify_user(**args),
            "list_groups": lambda: self._mgr.users.list_groups(**args),
            "create_group": lambda: self._mgr.users.create_group(**args),
            "delete_group": lambda: self._mgr.users.delete_group(**args),
            "add_to_group": lambda: self._mgr.users.add_to_group(**args),
            "remove_from_group": lambda: self._mgr.users.remove_from_group(**args),
            "list_ssh_keys": lambda: self._mgr.users.list_ssh_keys(**args),
            "add_ssh_key": lambda: self._mgr.users.add_ssh_key(**args),
            "remove_ssh_key": lambda: self._mgr.users.remove_ssh_key(**args),
            "generate_keypair": lambda: self._mgr.users.generate_ssh_keypair(**args),
            "grant_sudo": lambda: self._mgr.users.grant_sudo(**args),
            "revoke_sudo": lambda: self._mgr.users.revoke_sudo(**args),
            "get_acl": lambda: self._mgr.users.get_acl(**args),
            "set_acl": lambda: self._mgr.users.set_acl(**args),
            "remove_acl": lambda: self._mgr.users.remove_acl(**args),
            "set_password": lambda: self._mgr.users.set_password(**args),
            "lock": lambda: self._mgr.users.lock_account(**args),
            "unlock": lambda: self._mgr.users.unlock_account(**args),
        }
        fn = actions.get(action)
        if not fn:
            return ToolResult(
                success=False,
                error=f"Unknown user action '{action}'. Available: {', '.join(actions.keys())}",
            )
        return await fn()


# ─── Logger for error handling ────────────────────────────────────────────────
import logging
logger = logging.getLogger(__name__)


def create_server_tools(server_manager: ServerManager) -> List[Tool]:
    """Create all server management tool instances.

    Factory function that returns registered tools for MK's tool system.

    Args:
        server_manager: Initialized ServerManager instance.

    Returns:
        List of Tool instances ready for registration.
    """
    return [ServerTool(server_manager)]
