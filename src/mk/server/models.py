"""Data models for the MK server management layer.

Defines structured representations of storage pools, containers,
network interfaces, services, backup jobs, and users.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ─── Storage Models ───────────────────────────────────────────────────────────


class PoolStatus(str, Enum):
    """ZFS pool health status."""
    ONLINE = "online"
    DEGRADED = "degraded"
    FAULTED = "faulted"
    OFFLINE = "offline"
    UNAVAIL = "unavailable"
    REMOVED = "removed"


class VDevType(str, Enum):
    """ZFS virtual device types."""
    MIRROR = "mirror"
    RAIDZ1 = "raidz1"
    RAIDZ2 = "raidz2"
    RAIDZ3 = "raidz3"
    STRIPE = "stripe"
    SPARE = "spare"
    LOG = "log"
    CACHE = "cache"


class ZPool(BaseModel):
    """ZFS storage pool."""
    name: str = Field(description="Pool name")
    status: PoolStatus = Field(description="Pool health status")
    size_bytes: int = Field(description="Total pool size in bytes")
    used_bytes: int = Field(description="Used space in bytes")
    free_bytes: int = Field(description="Free space in bytes")
    fragmentation: int = Field(default=0, description="Fragmentation percentage")
    vdev_type: VDevType = Field(description="VDEV topology type")
    disks: List[str] = Field(default_factory=list, description="Member disk devices")
    datasets: List[str] = Field(default_factory=list, description="Child datasets")


class Dataset(BaseModel):
    """ZFS dataset (filesystem or volume)."""
    name: str = Field(description="Full dataset path (pool/dataset)")
    pool: str = Field(description="Parent pool name")
    mountpoint: str = Field(default="", description="Mount point path")
    used_bytes: int = Field(default=0, description="Used space")
    available_bytes: int = Field(default=0, description="Available space")
    compression: str = Field(default="lz4", description="Compression algorithm")
    quota_bytes: Optional[int] = Field(default=None, description="Quota limit")
    snapshots: List[str] = Field(default_factory=list, description="Snapshot names")


class Snapshot(BaseModel):
    """ZFS snapshot."""
    name: str = Field(description="Full snapshot name (pool/dataset@snap)")
    dataset: str = Field(description="Parent dataset")
    created: datetime = Field(description="Creation timestamp")
    used_bytes: int = Field(default=0, description="Space consumed by snapshot")
    referenced_bytes: int = Field(default=0, description="Referenced data size")


class ShareType(str, Enum):
    """Network share protocol."""
    SMB = "smb"
    NFS = "nfs"


class Share(BaseModel):
    """Network file share."""
    name: str = Field(description="Share name")
    path: str = Field(description="Filesystem path being shared")
    share_type: ShareType = Field(description="Share protocol")
    enabled: bool = Field(default=True, description="Whether share is active")
    read_only: bool = Field(default=False, description="Read-only share")
    allowed_hosts: List[str] = Field(default_factory=list, description="Allowed hosts/networks")
    allowed_users: List[str] = Field(default_factory=list, description="Allowed users")


# ─── Container Models ─────────────────────────────────────────────────────────


class ContainerState(str, Enum):
    """Container lifecycle state."""
    RUNNING = "running"
    STOPPED = "stopped"
    PAUSED = "paused"
    RESTARTING = "restarting"
    CREATING = "creating"
    REMOVING = "removing"
    DEAD = "dead"


class ContainerInfo(BaseModel):
    """Docker container information."""
    id: str = Field(description="Container ID (short)")
    name: str = Field(description="Container name")
    image: str = Field(description="Image name:tag")
    state: ContainerState = Field(description="Current state")
    created: datetime = Field(description="Creation time")
    ports: Dict[str, str] = Field(default_factory=dict, description="Port mappings host:container")
    volumes: List[str] = Field(default_factory=list, description="Volume mounts")
    cpu_percent: float = Field(default=0.0, description="CPU usage %")
    memory_mb: float = Field(default=0.0, description="Memory usage MB")
    restart_count: int = Field(default=0, description="Number of restarts")
    labels: Dict[str, str] = Field(default_factory=dict, description="Container labels")


class ComposeStack(BaseModel):
    """Docker Compose stack."""
    name: str = Field(description="Stack name")
    path: str = Field(description="Compose file path")
    services: List[str] = Field(default_factory=list, description="Service names")
    running: int = Field(default=0, description="Running service count")
    total: int = Field(default=0, description="Total service count")


# ─── Network Models ───────────────────────────────────────────────────────────


class InterfaceType(str, Enum):
    """Network interface type."""
    ETHERNET = "ethernet"
    BRIDGE = "bridge"
    BOND = "bond"
    VLAN = "vlan"
    LOOPBACK = "loopback"
    WIREGUARD = "wireguard"


class InterfaceState(str, Enum):
    """Network interface state."""
    UP = "up"
    DOWN = "down"
    UNKNOWN = "unknown"


class NetworkInterface(BaseModel):
    """Network interface configuration."""
    name: str = Field(description="Interface name (e.g., eth0)")
    iface_type: InterfaceType = Field(description="Interface type")
    state: InterfaceState = Field(description="Current state")
    mac_address: str = Field(default="", description="MAC address")
    ipv4_addresses: List[str] = Field(default_factory=list, description="IPv4 addresses with CIDR")
    ipv6_addresses: List[str] = Field(default_factory=list, description="IPv6 addresses with CIDR")
    mtu: int = Field(default=1500, description="MTU size")
    speed_mbps: Optional[int] = Field(default=None, description="Link speed in Mbps")
    rx_bytes: int = Field(default=0, description="Received bytes")
    tx_bytes: int = Field(default=0, description="Transmitted bytes")


class FirewallRule(BaseModel):
    """Firewall rule (nftables)."""
    id: int = Field(description="Rule ID/handle")
    chain: str = Field(default="input", description="Chain (input/output/forward)")
    action: str = Field(description="Action (accept/drop/reject)")
    protocol: Optional[str] = Field(default=None, description="Protocol (tcp/udp/icmp)")
    source: Optional[str] = Field(default=None, description="Source address/network")
    destination: Optional[str] = Field(default=None, description="Destination address/network")
    port: Optional[int] = Field(default=None, description="Destination port")
    comment: str = Field(default="", description="Rule description")
    enabled: bool = Field(default=True, description="Whether rule is active")


class WireGuardPeer(BaseModel):
    """WireGuard VPN peer."""
    name: str = Field(description="Peer friendly name")
    public_key: str = Field(description="Peer's public key")
    allowed_ips: List[str] = Field(description="Allowed IP ranges")
    endpoint: Optional[str] = Field(default=None, description="Peer endpoint address:port")
    last_handshake: Optional[datetime] = Field(default=None, description="Last handshake time")
    tx_bytes: int = Field(default=0, description="Bytes transmitted")
    rx_bytes: int = Field(default=0, description="Bytes received")


class WireGuardInterface(BaseModel):
    """WireGuard VPN interface."""
    name: str = Field(description="Interface name (e.g., wg0)")
    private_key_set: bool = Field(description="Whether private key is configured")
    listen_port: int = Field(description="Listening port")
    address: str = Field(description="Interface address with CIDR")
    peers: List[WireGuardPeer] = Field(default_factory=list, description="Connected peers")


# ─── Service Models ───────────────────────────────────────────────────────────


class ServiceState(str, Enum):
    """Systemd service state."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    FAILED = "failed"
    ACTIVATING = "activating"
    DEACTIVATING = "deactivating"


class RestartPolicy(str, Enum):
    """Service restart policy."""
    ALWAYS = "always"
    ON_FAILURE = "on-failure"
    NEVER = "no"


class ServiceInfo(BaseModel):
    """Systemd service information."""
    name: str = Field(description="Service unit name")
    description: str = Field(default="", description="Service description")
    state: ServiceState = Field(description="Current state")
    enabled: bool = Field(default=False, description="Whether service starts on boot")
    pid: Optional[int] = Field(default=None, description="Main process PID")
    uptime_seconds: Optional[float] = Field(default=None, description="Time since last start")
    restart_policy: RestartPolicy = Field(default=RestartPolicy.ON_FAILURE)
    restart_count: int = Field(default=0, description="Number of restarts")
    cpu_percent: float = Field(default=0.0, description="CPU usage")
    memory_mb: float = Field(default=0.0, description="Memory usage MB")


# ─── Backup Models ────────────────────────────────────────────────────────────


class BackupType(str, Enum):
    """Backup method type."""
    ZFS_SNAPSHOT = "zfs_snapshot"
    ZFS_SEND = "zfs_send"
    RSYNC = "rsync"
    RESTIC = "restic"


class BackupSchedule(str, Enum):
    """Backup schedule frequency."""
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    CUSTOM = "custom"


class BackupJob(BaseModel):
    """Backup job configuration."""
    name: str = Field(description="Job name")
    backup_type: BackupType = Field(description="Backup method")
    source: str = Field(description="Source path/dataset")
    destination: str = Field(description="Destination path/target")
    schedule: BackupSchedule = Field(description="Backup frequency")
    cron_expression: Optional[str] = Field(default=None, description="Custom cron if schedule=custom")
    retention_count: int = Field(default=7, description="Number of backups to retain")
    enabled: bool = Field(default=True, description="Whether job is active")
    last_run: Optional[datetime] = Field(default=None, description="Last execution time")
    last_status: Optional[str] = Field(default=None, description="Last run status")
    last_duration_seconds: Optional[float] = Field(default=None, description="Last run duration")


class RestorePoint(BaseModel):
    """Available restore point."""
    id: str = Field(description="Restore point identifier")
    job_name: str = Field(description="Parent backup job name")
    created: datetime = Field(description="When this point was created")
    size_bytes: int = Field(default=0, description="Backup size")
    verified: bool = Field(default=False, description="Whether integrity was verified")


# ─── User Models ──────────────────────────────────────────────────────────────


class UserAccount(BaseModel):
    """System user account."""
    username: str = Field(description="Username")
    uid: int = Field(description="User ID")
    gid: int = Field(description="Primary group ID")
    home: str = Field(description="Home directory")
    shell: str = Field(default="/bin/bash", description="Login shell")
    groups: List[str] = Field(default_factory=list, description="Group memberships")
    ssh_keys: List[str] = Field(default_factory=list, description="Authorized SSH public keys")
    locked: bool = Field(default=False, description="Whether account is locked")
    last_login: Optional[datetime] = Field(default=None, description="Last login time")


class GroupInfo(BaseModel):
    """System group."""
    name: str = Field(description="Group name")
    gid: int = Field(description="Group ID")
    members: List[str] = Field(default_factory=list, description="Member usernames")
