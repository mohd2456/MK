"""Network Manager - Interfaces, firewall, DNS, and VPN management.

The AI-managed network layer. Replaces pfSense/OPNsense dashboard:
- Network interface configuration (IP, DHCP, static, bonding, VLANs)
- Firewall management via nftables (rules, chains, port forwarding)
- DNS configuration (resolv.conf, local DNS, split DNS)
- WireGuard VPN management (interfaces, peers, key generation)
- Network diagnostics (ping, traceroute, DNS lookup, bandwidth test)

MK monitors connectivity, adjusts firewall rules, and manages VPN
peers — all through conversation.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from mk.tools.base import ToolResult

from .models import (
    FirewallRule,
    InterfaceState,
    InterfaceType,
    NetworkInterface,
    WireGuardInterface,
    WireGuardPeer,
)

logger = logging.getLogger(__name__)


class NetworkManager:
    """Manages network interfaces, firewall, DNS, and VPN.

    Provides unified control over the host's networking stack.
    Replaces the need for pfSense/OPNsense web UIs for basic
    home server networking tasks.
    """

    def __init__(self, sudo: bool = True) -> None:
        """Initialize the Network Manager.

        Args:
            sudo: Whether to prefix commands with sudo.
        """
        self._sudo = sudo
        self._cmd_prefix = "sudo " if sudo else ""

    async def _run(self, cmd: str, check: bool = True) -> Tuple[int, str, str]:
        """Execute a shell command asynchronously.

        Args:
            cmd: Command to execute.
            check: Log errors on non-zero exit.

        Returns:
            Tuple of (return_code, stdout, stderr).
        """
        full_cmd = f"{self._cmd_prefix}{cmd}" if not cmd.startswith("sudo") else cmd
        logger.debug(f"Network exec: {full_cmd}")

        proc = await asyncio.create_subprocess_shell(
            full_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        rc = proc.returncode or 0
        out = stdout.decode().strip()
        err = stderr.decode().strip()

        if rc != 0 and check:
            logger.error(f"Command failed ({rc}): {full_cmd}\n{err}")

        return rc, out, err

    # ─── Interface Management ─────────────────────────────────────────────

    async def list_interfaces(self) -> ToolResult:
        """List all network interfaces with their configuration.

        Returns:
            ToolResult with interface listing in JSON format.
        """
        rc, out, err = await self._run("ip -j addr show")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to list interfaces: {err}")

        return ToolResult(
            success=True,
            output=out,
            metadata={"format": "json"},
        )

    async def interface_status(self, name: str) -> ToolResult:
        """Get detailed status of a specific interface.

        Args:
            name: Interface name (e.g., eth0, eno1).

        Returns:
            ToolResult with interface details.
        """
        rc, out, err = await self._run(f"ip -j addr show dev {name}")
        if rc != 0:
            return ToolResult(success=False, error=f"Interface '{name}' not found: {err}")

        # Also get link stats
        rc2, stats, _ = await self._run(f"ip -j -s link show dev {name}")

        result = {"address_info": out}
        if rc2 == 0:
            result["stats"] = stats

        return ToolResult(
            success=True,
            output=json.dumps(result),
            metadata={"interface": name},
        )

    async def set_ip_address(
        self, interface: str, address: str, gateway: Optional[str] = None
    ) -> ToolResult:
        """Set a static IP address on an interface.

        Args:
            interface: Interface name.
            address: IP address with CIDR (e.g., "192.168.1.10/24").
            gateway: Default gateway (optional).

        Returns:
            ToolResult with configuration status.
        """
        # Flush existing addresses
        await self._run(f"ip addr flush dev {interface}")

        # Set new address
        rc, out, err = await self._run(f"ip addr add {address} dev {interface}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to set IP: {err}")

        # Set gateway if provided
        if gateway:
            await self._run("ip route del default 2>/dev/null", check=False)
            rc, _, err = await self._run(f"ip route add default via {gateway}")
            if rc != 0:
                return ToolResult(
                    success=False,
                    error=f"IP set but gateway failed: {err}",
                )

        side_effects = [f"IP {address} assigned to {interface}"]
        if gateway:
            side_effects.append(f"Default gateway set to {gateway}")

        return ToolResult(
            success=True,
            output=f"Interface '{interface}' configured: {address}" + (f" gw {gateway}" if gateway else ""),
            side_effects=side_effects,
            metadata={"interface": interface, "address": address, "gateway": gateway},
        )

    async def bring_interface_up(self, name: str) -> ToolResult:
        """Bring a network interface up.

        Args:
            name: Interface name.

        Returns:
            ToolResult with status.
        """
        rc, out, err = await self._run(f"ip link set {name} up")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to bring up {name}: {err}")

        return ToolResult(
            success=True,
            output=f"Interface '{name}' is UP",
            side_effects=[f"Interface '{name}' brought up"],
            metadata={"interface": name, "state": "up"},
        )

    async def bring_interface_down(self, name: str) -> ToolResult:
        """Bring a network interface down.

        Args:
            name: Interface name.

        Returns:
            ToolResult with status.
        """
        rc, out, err = await self._run(f"ip link set {name} down")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to bring down {name}: {err}")

        return ToolResult(
            success=True,
            output=f"Interface '{name}' is DOWN",
            side_effects=[f"Interface '{name}' brought down"],
            metadata={"interface": name, "state": "down"},
        )

    async def create_vlan(self, parent: str, vlan_id: int, name: Optional[str] = None) -> ToolResult:
        """Create a VLAN interface.

        Args:
            parent: Parent interface (e.g., eth0).
            vlan_id: VLAN ID (1-4094).
            name: Custom interface name (default: parent.vlan_id).

        Returns:
            ToolResult with creation status.
        """
        iface_name = name or f"{parent}.{vlan_id}"
        rc, out, err = await self._run(
            f"ip link add link {parent} name {iface_name} type vlan id {vlan_id}"
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to create VLAN: {err}")

        await self._run(f"ip link set {iface_name} up")

        return ToolResult(
            success=True,
            output=f"VLAN {vlan_id} created on {parent} as {iface_name}",
            side_effects=[f"VLAN interface '{iface_name}' created and brought up"],
            metadata={"interface": iface_name, "parent": parent, "vlan_id": vlan_id},
        )

    async def create_bridge(self, name: str, members: List[str]) -> ToolResult:
        """Create a network bridge.

        Args:
            name: Bridge interface name.
            members: Interfaces to add to the bridge.

        Returns:
            ToolResult with creation status.
        """
        # Create bridge
        rc, _, err = await self._run(f"ip link add name {name} type bridge")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to create bridge: {err}")

        # Add members
        for member in members:
            await self._run(f"ip link set {member} master {name}")

        # Bring up
        await self._run(f"ip link set {name} up")

        return ToolResult(
            success=True,
            output=f"Bridge '{name}' created with members: {', '.join(members)}",
            side_effects=[f"Bridge '{name}' created", f"Members added: {members}"],
            metadata={"bridge": name, "members": members},
        )

    # ─── Firewall (nftables) ──────────────────────────────────────────────

    async def firewall_status(self) -> ToolResult:
        """Show current firewall ruleset.

        Returns:
            ToolResult with nftables ruleset.
        """
        rc, out, err = await self._run("nft list ruleset")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to get firewall status: {err}")

        return ToolResult(
            success=True,
            output=out if out else "No firewall rules configured",
            metadata={"format": "nftables"},
        )

    async def add_firewall_rule(
        self,
        chain: str = "input",
        action: str = "accept",
        protocol: Optional[str] = None,
        port: Optional[int] = None,
        source: Optional[str] = None,
        destination: Optional[str] = None,
        comment: str = "",
    ) -> ToolResult:
        """Add a firewall rule via nftables.

        Args:
            chain: Chain name (input, output, forward).
            action: Rule action (accept, drop, reject).
            protocol: Protocol (tcp, udp, icmp).
            port: Destination port number.
            source: Source IP/network.
            destination: Destination IP/network.
            comment: Rule description.

        Returns:
            ToolResult with rule creation status.
        """
        # Build nft rule expression
        rule_parts = []
        if protocol:
            rule_parts.append(f"ip protocol {protocol}")
        if source:
            rule_parts.append(f"ip saddr {source}")
        if destination:
            rule_parts.append(f"ip daddr {destination}")
        if port and protocol:
            rule_parts.append(f"{protocol} dport {port}")
        if comment:
            rule_parts.append(f'comment "{comment}"')
        rule_parts.append(action)

        rule_expr = " ".join(rule_parts)

        # Ensure table and chain exist
        await self._run(
            "nft add table inet mk_firewall 2>/dev/null", check=False
        )
        await self._run(
            f"nft add chain inet mk_firewall {chain} '{{ type filter hook {chain} priority 0; policy accept; }}' 2>/dev/null",
            check=False,
        )

        # Add rule
        rc, out, err = await self._run(
            f"nft add rule inet mk_firewall {chain} {rule_expr}"
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to add rule: {err}")

        return ToolResult(
            success=True,
            output=f"Firewall rule added: {chain} -> {rule_expr}",
            side_effects=[f"nftables rule added to {chain} chain"],
            metadata={"chain": chain, "rule": rule_expr, "action": action},
        )

    async def remove_firewall_rule(self, chain: str, handle: int) -> ToolResult:
        """Remove a firewall rule by handle number.

        Args:
            chain: Chain containing the rule.
            handle: Rule handle number.

        Returns:
            ToolResult with removal status.
        """
        rc, out, err = await self._run(
            f"nft delete rule inet mk_firewall {chain} handle {handle}"
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to remove rule: {err}")

        return ToolResult(
            success=True,
            output=f"Rule handle {handle} removed from {chain}",
            side_effects=[f"Firewall rule {handle} removed from {chain}"],
            metadata={"chain": chain, "handle": handle},
        )

    async def add_port_forward(
        self,
        external_port: int,
        internal_ip: str,
        internal_port: int,
        protocol: str = "tcp",
    ) -> ToolResult:
        """Add a port forwarding rule (DNAT).

        Args:
            external_port: External (WAN) port.
            internal_ip: Internal destination IP.
            internal_port: Internal destination port.
            protocol: Protocol (tcp/udp).

        Returns:
            ToolResult with port forward status.
        """
        # Ensure NAT table exists
        await self._run(
            "nft add table ip mk_nat 2>/dev/null", check=False
        )
        await self._run(
            "nft add chain ip mk_nat prerouting '{ type nat hook prerouting priority -100; }' 2>/dev/null",
            check=False,
        )

        rc, out, err = await self._run(
            f"nft add rule ip mk_nat prerouting {protocol} dport {external_port} "
            f"dnat to {internal_ip}:{internal_port}"
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to add port forward: {err}")

        return ToolResult(
            success=True,
            output=f"Port forward: :{external_port}/{protocol} -> {internal_ip}:{internal_port}",
            side_effects=[f"Port {external_port} forwarded to {internal_ip}:{internal_port}"],
            metadata={
                "external_port": external_port,
                "internal_ip": internal_ip,
                "internal_port": internal_port,
                "protocol": protocol,
            },
        )

    # ─── DNS Management ───────────────────────────────────────────────────

    async def get_dns_config(self) -> ToolResult:
        """Get current DNS configuration.

        Returns:
            ToolResult with DNS settings.
        """
        rc, out, err = await self._run("cat /etc/resolv.conf", check=False)
        resolv = out if rc == 0 else ""

        # Try systemd-resolved
        rc2, resolved, _ = await self._run(
            "resolvectl status 2>/dev/null", check=False
        )

        result = {"resolv_conf": resolv}
        if rc2 == 0:
            result["systemd_resolved"] = resolved

        return ToolResult(
            success=True,
            output=json.dumps(result, indent=2),
            metadata={"format": "dns_config"},
        )

    async def set_dns_servers(self, servers: List[str], search_domains: Optional[List[str]] = None) -> ToolResult:
        """Set DNS server addresses.

        Args:
            servers: List of DNS server IPs.
            search_domains: DNS search domains.

        Returns:
            ToolResult with configuration status.
        """
        lines = []
        if search_domains:
            lines.append(f"search {' '.join(search_domains)}")
        for server in servers:
            lines.append(f"nameserver {server}")

        content = "\n".join(lines) + "\n"

        rc, _, err = await self._run(
            f"bash -c 'echo \"{content}\" > /etc/resolv.conf'"
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to set DNS: {err}")

        return ToolResult(
            success=True,
            output=f"DNS servers set to: {', '.join(servers)}",
            side_effects=["DNS configuration updated in /etc/resolv.conf"],
            metadata={"servers": servers, "search_domains": search_domains},
        )

    # ─── WireGuard VPN ────────────────────────────────────────────────────

    async def wireguard_status(self) -> ToolResult:
        """Show WireGuard interface status and connected peers.

        Returns:
            ToolResult with WireGuard status.
        """
        rc, out, err = await self._run("wg show all")
        if rc != 0:
            return ToolResult(
                success=False,
                error=f"WireGuard not available or no interfaces: {err}",
            )

        return ToolResult(
            success=True,
            output=out if out else "No WireGuard interfaces configured",
            metadata={"format": "wireguard"},
        )

    async def create_wireguard_interface(
        self,
        name: str = "wg0",
        address: str = "10.0.0.1/24",
        listen_port: int = 51820,
    ) -> ToolResult:
        """Create and configure a WireGuard interface.

        Args:
            name: Interface name (default: wg0).
            address: Interface address with CIDR.
            listen_port: UDP listen port.

        Returns:
            ToolResult with interface setup status.
        """
        # Generate keypair
        rc, privkey, err = await self._run("wg genkey")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to generate key: {err}")

        # Derive public key
        rc, pubkey, err = await self._run(f"echo '{privkey}' | wg pubkey")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to derive pubkey: {err}")

        # Create interface
        await self._run(f"ip link add dev {name} type wireguard")
        await self._run(f"ip addr add {address} dev {name}")

        # Write private key to temp file and configure
        await self._run(f"bash -c 'echo \"{privkey}\" > /etc/wireguard/{name}.key'")
        await self._run(f"chmod 600 /etc/wireguard/{name}.key")
        await self._run(f"wg set {name} listen-port {listen_port} private-key /etc/wireguard/{name}.key")
        await self._run(f"ip link set {name} up")

        return ToolResult(
            success=True,
            output=f"WireGuard interface '{name}' created\n  Address: {address}\n  Port: {listen_port}\n  Public Key: {pubkey}",
            side_effects=[
                f"WireGuard interface '{name}' created and active",
                f"Private key stored at /etc/wireguard/{name}.key",
            ],
            metadata={
                "interface": name,
                "address": address,
                "port": listen_port,
                "public_key": pubkey,
            },
        )

    async def add_wireguard_peer(
        self,
        interface: str,
        public_key: str,
        allowed_ips: str,
        endpoint: Optional[str] = None,
        persistent_keepalive: int = 25,
        name: Optional[str] = None,
    ) -> ToolResult:
        """Add a peer to a WireGuard interface.

        Args:
            interface: WireGuard interface name.
            public_key: Peer's public key.
            allowed_ips: Comma-separated allowed IPs (e.g., "10.0.0.2/32").
            endpoint: Peer endpoint (host:port).
            persistent_keepalive: Keepalive interval in seconds.
            name: Friendly name for the peer (stored as comment).

        Returns:
            ToolResult with peer addition status.
        """
        cmd_parts = [
            f"wg set {interface} peer {public_key}",
            f"allowed-ips {allowed_ips}",
        ]
        if endpoint:
            cmd_parts.append(f"endpoint {endpoint}")
        if persistent_keepalive:
            cmd_parts.append(f"persistent-keepalive {persistent_keepalive}")

        cmd = " ".join(cmd_parts)
        rc, out, err = await self._run(cmd)
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to add peer: {err}")

        peer_name = name or public_key[:8]
        return ToolResult(
            success=True,
            output=f"Peer '{peer_name}' added to {interface} (allowed: {allowed_ips})",
            side_effects=[f"WireGuard peer added to {interface}"],
            metadata={
                "interface": interface,
                "peer_name": peer_name,
                "public_key": public_key,
                "allowed_ips": allowed_ips,
            },
        )

    async def remove_wireguard_peer(self, interface: str, public_key: str) -> ToolResult:
        """Remove a peer from a WireGuard interface.

        Args:
            interface: WireGuard interface name.
            public_key: Peer's public key to remove.

        Returns:
            ToolResult with removal status.
        """
        rc, out, err = await self._run(f"wg set {interface} peer {public_key} remove")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to remove peer: {err}")

        return ToolResult(
            success=True,
            output=f"Peer removed from {interface}",
            side_effects=[f"WireGuard peer removed from {interface}"],
            metadata={"interface": interface, "public_key": public_key},
        )

    async def generate_peer_config(
        self,
        server_interface: str,
        peer_address: str,
        server_public_key: str,
        server_endpoint: str,
        dns: str = "1.1.1.1",
        allowed_ips: str = "0.0.0.0/0",
    ) -> ToolResult:
        """Generate a WireGuard client configuration for a new peer.

        Args:
            server_interface: Server WG interface name.
            peer_address: IP address for the peer (e.g., "10.0.0.2/32").
            server_public_key: Server's public key.
            server_endpoint: Server endpoint (host:port).
            dns: DNS server for the peer.
            allowed_ips: What traffic to route through VPN.

        Returns:
            ToolResult with peer config (for QR code or file).
        """
        # Generate client keypair
        rc, client_privkey, _ = await self._run("wg genkey")
        if rc != 0:
            return ToolResult(success=False, error="Failed to generate client key")

        rc, client_pubkey, _ = await self._run(f"echo '{client_privkey}' | wg pubkey")
        if rc != 0:
            return ToolResult(success=False, error="Failed to derive client pubkey")

        config = f"""[Interface]
PrivateKey = {client_privkey}
Address = {peer_address}
DNS = {dns}

[Peer]
PublicKey = {server_public_key}
AllowedIPs = {allowed_ips}
Endpoint = {server_endpoint}
PersistentKeepalive = 25
"""

        return ToolResult(
            success=True,
            output=config,
            metadata={
                "client_public_key": client_pubkey,
                "peer_address": peer_address,
                "note": "Add client_public_key as peer on server",
            },
        )

    # ─── Network Diagnostics ──────────────────────────────────────────────

    async def ping(self, target: str, count: int = 4) -> ToolResult:
        """Ping a host to check connectivity.

        Args:
            target: Hostname or IP to ping.
            count: Number of pings.

        Returns:
            ToolResult with ping results.
        """
        rc, out, err = await self._run(f"ping -c {count} -W 5 {target}")
        if rc != 0:
            return ToolResult(
                success=False,
                error=f"Ping to {target} failed: {err or out}",
                metadata={"target": target, "reachable": False},
            )

        return ToolResult(
            success=True,
            output=out,
            metadata={"target": target, "reachable": True},
        )

    async def traceroute(self, target: str) -> ToolResult:
        """Run traceroute to a target.

        Args:
            target: Hostname or IP.

        Returns:
            ToolResult with traceroute output.
        """
        rc, out, err = await self._run(f"traceroute -w 3 -m 20 {target}")
        success = rc == 0 or bool(out)

        return ToolResult(
            success=success,
            output=out if out else err,
            metadata={"target": target},
        )

    async def dns_lookup(self, hostname: str, record_type: str = "A") -> ToolResult:
        """Perform a DNS lookup.

        Args:
            hostname: Domain to look up.
            record_type: Record type (A, AAAA, MX, NS, TXT, CNAME).

        Returns:
            ToolResult with DNS query results.
        """
        rc, out, err = await self._run(f"dig +short {record_type} {hostname}")
        if rc != 0:
            return ToolResult(success=False, error=f"DNS lookup failed: {err}")

        return ToolResult(
            success=True,
            output=out if out else f"No {record_type} records found for {hostname}",
            metadata={"hostname": hostname, "record_type": record_type},
        )

    async def port_scan(self, target: str, ports: str = "1-1024") -> ToolResult:
        """Quick port scan on a target (uses /dev/tcp or nmap if available).

        Args:
            target: Target host.
            ports: Port range (e.g., "80,443" or "1-1024").

        Returns:
            ToolResult with open ports.
        """
        # Try nmap first, fall back to ss for local
        rc, out, err = await self._run(
            f"nmap -T4 --open -p {ports} {target} 2>/dev/null || ss -tlnp",
            check=False,
        )

        return ToolResult(
            success=True,
            output=out if out else "No results",
            metadata={"target": target, "ports": ports},
        )
