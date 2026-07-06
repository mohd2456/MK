"""Server management tools registration for MK's tool system."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from mk.tools.base import Tool, ToolResult

from .manager import ServerManager

logger = logging.getLogger(__name__)

# Action-to-method mappings for each domain.
# Keys are action names exposed to the LLM, values are method names on the sub-manager.

SYSTEM_ACTIONS = {
    "overview": "system_overview",
    "health": "health_report",
    "hardware": "hardware_info",
    "reboot": "reboot",
    "shutdown": "shutdown",
    "cancel_shutdown": "cancel_shutdown",
    "check_updates": "check_updates",
    "apply_updates": "apply_updates",
    "quick_deploy": "quick_deploy_app",
}

STORAGE_ACTIONS = {
    "list_pools": "list_pools",
    "pool_status": "pool_status",
    "create_pool": "create_pool",
    "destroy_pool": "destroy_pool",
    "scrub_pool": "scrub_pool",
    "list_datasets": "list_datasets",
    "create_dataset": "create_dataset",
    "destroy_dataset": "destroy_dataset",
    "set_property": "set_property",
    "list_snapshots": "list_snapshots",
    "create_snapshot": "create_snapshot",
    "rollback_snapshot": "rollback_snapshot",
    "destroy_snapshot": "destroy_snapshot",
    "list_shares": "list_shares",
    "create_smb_share": "create_smb_share",
    "create_nfs_share": "create_nfs_share",
    "remove_share": "remove_share",
    "list_disks": "list_disks",
    "disk_smart": "disk_smart_health",
    "send_snapshot": "send_snapshot",
}

CONTAINER_ACTIONS = {
    "list": "list_containers",
    "stats": "container_stats",
    "start": "start_container",
    "stop": "stop_container",
    "restart": "restart_container",
    "remove": "remove_container",
    "logs": "container_logs",
    "inspect": "inspect_container",
    "run": "run_container",
    "list_stacks": "list_stacks",
    "deploy_stack": "deploy_stack",
    "update_stack": "update_stack",
    "destroy_stack": "destroy_stack",
    "stack_logs": "stack_logs",
    "list_images": "list_images",
    "pull_image": "pull_image",
    "prune_images": "prune_images",
    "list_volumes": "list_volumes",
    "create_volume": "create_volume",
    "list_networks": "list_networks",
    "create_network": "create_network",
    "system_prune": "system_prune",
    "disk_usage": "disk_usage",
}

NETWORK_ACTIONS = {
    "list_interfaces": "list_interfaces",
    "interface_status": "interface_status",
    "set_ip": "set_ip_address",
    "interface_up": "bring_interface_up",
    "interface_down": "bring_interface_down",
    "create_vlan": "create_vlan",
    "create_bridge": "create_bridge",
    "firewall_status": "firewall_status",
    "add_firewall_rule": "add_firewall_rule",
    "remove_firewall_rule": "remove_firewall_rule",
    "add_port_forward": "add_port_forward",
    "get_dns": "get_dns_config",
    "set_dns": "set_dns_servers",
    "wireguard_status": "wireguard_status",
    "create_wireguard": "create_wireguard_interface",
    "add_wg_peer": "add_wireguard_peer",
    "remove_wg_peer": "remove_wireguard_peer",
    "generate_wg_config": "generate_peer_config",
    "ping": "ping",
    "traceroute": "traceroute",
    "dns_lookup": "dns_lookup",
    "port_scan": "port_scan",
}

SERVICE_ACTIONS = {
    "list": "list_services",
    "status": "service_status",
    "start": "start_service",
    "stop": "stop_service",
    "restart": "restart_service",
    "reload": "reload_service",
    "enable": "enable_service",
    "disable": "disable_service",
    "logs": "service_logs",
    "system_logs": "system_logs",
    "create": "create_service",
    "delete": "delete_service",
    "list_timers": "list_timers",
    "create_timer": "create_timer",
    "failed": "failed_services",
    "boot_analysis": "system_boot_time",
    "daemon_reload": "reload_daemon",
}

BACKUP_ACTIONS = {
    "list_jobs": "list_jobs",
    "create_job": "create_job",
    "delete_job": "delete_job",
    "run_backup": "run_backup",
    "apply_retention": "apply_retention",
    "list_restore_points": "list_restore_points",
    "restore": "restore",
    "verify": "verify_backup",
    "health": "health_check",
}

USER_ACTIONS = {
    "list": "list_users",
    "info": "user_info",
    "create": "create_user",
    "delete": "delete_user",
    "modify": "modify_user",
    "list_groups": "list_groups",
    "create_group": "create_group",
    "delete_group": "delete_group",
    "add_to_group": "add_to_group",
    "remove_from_group": "remove_from_group",
    "list_ssh_keys": "list_ssh_keys",
    "add_ssh_key": "add_ssh_key",
    "remove_ssh_key": "remove_ssh_key",
    "generate_keypair": "generate_ssh_keypair",
    "grant_sudo": "grant_sudo",
    "revoke_sudo": "revoke_sudo",
    "get_acl": "get_acl",
    "set_acl": "set_acl",
    "remove_acl": "remove_acl",
    "set_password": "set_password",
    "lock": "lock_account",
    "unlock": "unlock_account",
}

VM_ACTIONS = {
    "list": "list_vms",
    "info": "vm_info",
    "create": "create_vm",
    "start": "start_vm",
    "stop": "stop_vm",
    "reboot": "reboot_vm",
    "pause": "pause_vm",
    "resume": "resume_vm",
    "delete": "delete_vm",
    "list_snapshots": "list_snapshots",
    "create_snapshot": "create_snapshot",
    "revert_snapshot": "revert_snapshot",
    "delete_snapshot": "delete_snapshot",
    "set_vcpus": "set_vcpus",
    "set_memory": "set_memory",
    "add_disk": "add_disk",
    "clone": "clone_vm",
    "console": "console_info",
    "autostart": "set_autostart",
}

LXC_ACTIONS = {
    "list": "list_containers",
    "info": "container_info",
    "create": "create_container",
    "start": "start_container",
    "stop": "stop_container",
    "restart": "restart_container",
    "destroy": "destroy_container",
    "exec": "exec_command",
    "list_snapshots": "list_snapshots",
    "create_snapshot": "create_snapshot",
    "restore_snapshot": "restore_snapshot",
    "clone": "clone_container",
    "autostart": "set_autostart",
    "set_memory": "set_memory_limit",
    "set_cpu": "set_cpu_limit",
    "add_mount": "add_mount",
}

HOMELAB_ACTIONS = {
    "wake": "wake_machine",
    "ups_status": "ups_status",
    "ups_battery": "ups_battery_percent",
    "proxy_status": "proxy_status",
    "add_proxy": "add_proxy_site",
    "remove_proxy": "remove_proxy_site",
    "ddns_status": "ddns_status",
    "ddns_update": "ddns_update_now",
    "public_ip": "get_public_ip",
    "temperatures": "system_temperatures",
    "speedtest": "speedtest",
    "top_processes": "top_processes",
    "check_port": "check_port_open",
    "list_certs": "list_certs",
    "renew_certs": "renew_certs",
    "list_cron": "list_cron_jobs",
    "disk_health": "disk_health_summary",
    "suspend": "suspend_system",
    "schedule_wake": "schedule_wake",
}

RIPPER_ACTIONS = {
    "detect_drive": "detect_drive",
    "disc_status": "disc_status",
    "rip": "rip_disc",
    "eject": "eject_disc",
    "close_tray": "close_tray",
    "watch": "watch_for_disc",
    "config": "get_config",
    "check_deps": "check_dependencies",
}

MIGRATION_ACTIONS = {
    "export": "export_state",
    "import": "import_state",
    "hardware_profile": "hardware_profile",
}


class ServerTool(Tool):
    """Unified server management tool.

    Routes to the appropriate sub-manager based on domain and action parameters.
    """

    def __init__(self, server_manager: ServerManager) -> None:
        self._mgr = server_manager

    @property
    def name(self) -> str:
        return "server"

    @property
    def description(self) -> str:
        return (
            "Manage the server: storage (ZFS), containers (Docker), "
            "vms (KVM/QEMU via libvirt), lxc (system containers), "
            "network (interfaces, firewall, DNS, VPN), "
            "services (systemd), backups (snapshots, replication), "
            "users (accounts, SSH keys, ACLs), "
            "homelab (WoL, UPS, reverse proxy, DDNS, monitoring), "
            "ripper (autonomous Blu-ray/DVD ripping to Plex/Jellyfin), "
            "and system (overview, health, power, updates)."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "enum": [
                        "system", "storage", "containers", "vms", "lxc",
                        "network", "services", "backups", "users", "homelab",
                        "ripper", "migration",
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
        """Route to the appropriate sub-manager action."""
        domain = kwargs.get("domain", "")
        action = kwargs.get("action", "")
        args = kwargs.get("args", {})

        if not domain:
            return ToolResult(success=False, error="Domain is required")
        if not action:
            return ToolResult(success=False, error="Action is required")

        # Map domains to (target_object, action_table)
        domain_map = {
            "system": (self._mgr, SYSTEM_ACTIONS),
            "storage": (self._mgr.storage, STORAGE_ACTIONS),
            "containers": (self._mgr.containers, CONTAINER_ACTIONS),
            "vms": (self._mgr.vms, VM_ACTIONS),
            "lxc": (self._mgr.lxc, LXC_ACTIONS),
            "network": (self._mgr.network, NETWORK_ACTIONS),
            "services": (self._mgr.services, SERVICE_ACTIONS),
            "backups": (self._mgr.backups, BACKUP_ACTIONS),
            "users": (self._mgr.users, USER_ACTIONS),
            "homelab": (self._mgr.homelab, HOMELAB_ACTIONS),
            "ripper": (self._mgr.ripper, RIPPER_ACTIONS),
            "migration": (self._mgr.migration, MIGRATION_ACTIONS),
        }

        entry = domain_map.get(domain)
        if not entry:
            return ToolResult(
                success=False,
                error=f"Unknown domain '{domain}'. Use: {', '.join(domain_map.keys())}",
            )

        target, action_table = entry
        method_name = action_table.get(action)
        if not method_name:
            return ToolResult(
                success=False,
                error=f"Unknown {domain} action '{action}'. Available: {', '.join(action_table.keys())}",
            )

        method = getattr(target, method_name, None)
        if method is None:
            return ToolResult(
                success=False,
                error=f"Method '{method_name}' not found on {domain} manager",
            )

        try:
            return await method(**args) if args else await method()
        except Exception as e:
            logger.error(f"Server tool error: {domain}.{action} - {e}")
            return ToolResult(success=False, error=f"Error in {domain}.{action}: {str(e)}")


def create_server_tools(server_manager: ServerManager) -> List[Tool]:
    """Create server management tool instances for MK's tool system."""
    return [ServerTool(server_manager)]
