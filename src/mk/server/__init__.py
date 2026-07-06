"""MK Server Management Layer.

The AI-managed server operating system layer. Provides TrueNAS/Proxmox/Unraid-level
functionality through natural language — no web UI needed. MK IS the interface.

Modules:
    storage: ZFS pool/dataset management, snapshots, shares (SMB/NFS)
    containers: Docker lifecycle, compose orchestration, resource limits
    network: Interfaces, firewall (nftables), DNS, VPN (WireGuard)
    services: Systemd service control, health monitoring, auto-restart
    backups: Scheduled snapshots, replication, restore points
    users: User/group management, ACLs, SSH keys
    manager: Top-level ServerManager orchestrator
    tools: Tool registration for MK's agent system
"""

from mk.server.manager import ServerManager
from mk.server.storage import StorageManager
from mk.server.containers import ContainerManager
from mk.server.network import NetworkManager
from mk.server.services import ServiceManager
from mk.server.backups import BackupManager
from mk.server.users import UserManager
from mk.server.tools import ServerTool, create_server_tools

__all__ = [
    "ServerManager",
    "StorageManager",
    "ContainerManager",
    "NetworkManager",
    "ServiceManager",
    "BackupManager",
    "UserManager",
    "ServerTool",
    "create_server_tools",
]
