"""Network Manager - Interfaces, firewall, DNS, and VPN management."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from mk.tools.base import ToolResult

from ._shell import safe_quote, validate_name
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
    """Manages network interfaces, firewall, DNS, and VPN."""

    def __init__(self, sudo: bool = True) -> None:
        self._sudo = sudo
        self._cmd_prefix = "sudo " if sudo else ""

    async def _run(self, cmd: str, check: bool = True) -> Tuple[int, str, str]:
        """Execute a shell command asynchronously."""
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
            logger.debug(f"Command failed ({rc}): {full_cmd}\n{err}")

        return rc, out, err

    async def _run_with_stdin(self, cmd: str, input_data: str) -> Tuple[int, str, str]:
        """Execute a shell command with data passed via stdin."""
        full_cmd = f"{self._cmd_prefix}{cmd}" if not cmd.startswith("sudo") else cmd
        logger.debug(f"Network exec (stdin): {full_cmd}")

        proc = await asyncio.create_subprocess_shell(
            full_cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate(input=input_data.encode())
        rc = proc.returncode or 0
        return rc, stdout.decode().strip(), stderr.decode().strip()

    # Interface Management

    async def list_interfaces(self) -> ToolResult:
        """List all network interfaces with their configuration."""
        rc, out, err = await self._run("ip -j addr show")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to list interfaces: {err}")

        return ToolResult(
            success=True,
            output=out,
            metadata={"format": "json"},
        )

    async def interface_status(self, name: str) -> ToolResult:
        """Get detailed status of a specific interface."""
        validate_name(name, "interface name")
        rc, out, err = await self._run(f"ip -j addr show dev {safe_quote(name)}")
        if rc != 0:
            return ToolResult(success=False, error=f"Interface '{name}' not found: {err}")

        rc2, stats, _ = await self._run(f"ip -j -s link show dev {safe_quote(name)}")

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
        """Set a static IP address on an interface."""
        validate_name(interface, "interface")
        await self._run(f"ip addr flush dev {safe_quote(interface)}")

        rc, out, err = await self._run(f"ip addr add {safe_quote(address)} dev {safe_quote(interface)}")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to set IP: {err}")

        if gateway:
            await self._run("ip route del default 2>/dev/null", check=False)
            rc, _, err = await self._run(f"ip route add default via {safe_quote(gateway)}")
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
        """Bring a network interface up."""
        validate_name(name, "interface name")
        rc, out, err = await self._run(f"ip link set {safe_quote(name)} up")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to bring up {name}: {err}")

        return ToolResult(
            success=True,
            output=f"Interface '{name}' is UP",
            side_effects=[f"Interface '{name}' brought up"],
            metadata={"interface": name, "state": "up"},
        )

    async def bring_interface_down(self, name: str) -> ToolResult:
        """Bring a network interface down."""
        validate_name(name, "interface name")
        rc, out, err = await self._run(f"ip link set {safe_quote(name)} down")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to bring down {name}: {err}")

        return ToolResult(
            success=True,
            output=f"Interface '{name}' is DOWN",
            side_effects=[f"Interface '{name}' brought down"],
            metadata={"interface": name, "state": "down"},
        )

    async def create_vlan(self, parent: str, vlan_id: int, name: Optional[str] = None) -> ToolResult:
        """Create a VLAN interface."""
        validate_name(parent, "parent interface")
        iface_name = name or f"{parent}.{vlan_id}"
        validate_name(iface_name, "interface name")

        rc, out, err = await self._run(
            f"ip link add link {safe_quote(parent)} name {safe_quote(iface_name)} type vlan id {int(vlan_id)}"
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to create VLAN: {err}")

        await self._run(f"ip link set {safe_quote(iface_name)} up")

        return ToolResult(
            success=True,
            output=f"VLAN {vlan_id} created on {parent} as {iface_name}",
            side_effects=[f"VLAN interface '{iface_name}' created and brought up"],
            metadata={"interface": iface_name, "parent": parent, "vlan_id": vlan_id},
        )

    async def create_bridge(self, name: str, members: List[str]) -> ToolResult:
        """Create a network bridge."""
        validate_name(name, "bridge name")
        for member in members:
            validate_name(member, "bridge member")

        rc, _, err = await self._run(f"ip link add name {safe_quote(name)} type bridge")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to create bridge: {err}")

        for member in members:
            await self._run(f"ip link set {safe_quote(member)} master {safe_quote(name)}")

        await self._run(f"ip link set {safe_quote(name)} up")

        return ToolResult(
            success=True,
            output=f"Bridge '{name}' created with members: {', '.join(members)}",
            side_effects=[f"Bridge '{name}' created", f"Members added: {members}"],
            metadata={"bridge": name, "members": members},
        )

    # Firewall (nftables)

    async def firewall_status(self) -> ToolResult:
        """Show current firewall ruleset."""
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
        """Add a firewall rule via nftables."""
        validate_name(chain, "chain")

        rule_parts = []
        if protocol:
            validate_name(protocol, "protocol")
            rule_parts.append(f"ip protocol {protocol}")
        if source:
            rule_parts.append(f"ip saddr {safe_quote(source)}")
        if destination:
            rule_parts.append(f"ip daddr {safe_quote(destination)}")
        if port and protocol:
            rule_parts.append(f"{protocol} dport {int(port)}")
        if comment:
            rule_parts.append(f'comment {safe_quote(comment)}')
        rule_parts.append(action)

        rule_expr = " ".join(rule_parts)

        await self._run(
            "nft add table inet mk_firewall 2>/dev/null", check=False
        )
        await self._run(
            f"nft add chain inet mk_firewall {safe_quote(chain)} "
            f"'{{ type filter hook {chain} priority 0; policy accept; }}' 2>/dev/null",
            check=False,
        )

        rc, out, err = await self._run(
            f"nft add rule inet mk_firewall {safe_quote(chain)} {rule_expr}"
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
        """Remove a firewall rule by handle number."""
        validate_name(chain, "chain")
        rc, out, err = await self._run(
            f"nft delete rule inet mk_firewall {safe_quote(chain)} handle {int(handle)}"
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
        """Add a port forwarding rule (DNAT)."""
        validate_name(protocol, "protocol")

        await self._run(
            "nft add table ip mk_nat 2>/dev/null", check=False
        )
        await self._run(
            "nft add chain ip mk_nat prerouting '{ type nat hook prerouting priority -100; }' 2>/dev/null",
            check=False,
        )

        rc, out, err = await self._run(
            f"nft add rule ip mk_nat prerouting {protocol} dport {int(external_port)} "
            f"dnat to {safe_quote(internal_ip)}:{int(internal_port)}"
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

    # DNS Management

    async def get_dns_config(self) -> ToolResult:
        """Get current DNS configuration."""
        rc, out, err = await self._run("cat /etc/resolv.conf", check=False)
        resolv = out if rc == 0 else ""

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
        """Set DNS server addresses."""
        lines = []
        if search_domains:
            lines.append(f"search {' '.join(search_domains)}")
        for server in servers:
            lines.append(f"nameserver {server}")

        content = "\n".join(lines) + "\n"

        # Use stdin to write content safely (avoids interpolation issues)
        rc, _, err = await self._run_with_stdin(
            "tee /etc/resolv.conf > /dev/null", content
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to set DNS: {err}")

        return ToolResult(
            success=True,
            output=f"DNS servers set to: {', '.join(servers)}",
            side_effects=["DNS configuration updated in /etc/resolv.conf"],
            metadata={"servers": servers, "search_domains": search_domains},
        )

    # WireGuard VPN

    async def wireguard_status(self) -> ToolResult:
        """Show WireGuard interface status and connected peers."""
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
        """Create and configure a WireGuard interface."""
        validate_name(name, "interface name")

        # Generate keypair
        rc, privkey, err = await self._run("wg genkey")
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to generate key: {err}")

        # Derive public key using stdin instead of echo interpolation
        rc, pubkey, err = await self._run_with_stdin("wg pubkey", privkey)
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to derive pubkey: {err}")

        # Create interface
        await self._run(f"ip link add dev {safe_quote(name)} type wireguard")
        await self._run(f"ip addr add {safe_quote(address)} dev {safe_quote(name)}")

        # Write private key via stdin (avoids key interpolation in shell)
        key_path = f"/etc/wireguard/{name}.key"
        rc, _, err = await self._run_with_stdin(
            f"tee {safe_quote(key_path)} > /dev/null", privkey
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to write private key: {err}")

        await self._run(f"chmod 600 {safe_quote(key_path)}")
        await self._run(
            f"wg set {safe_quote(name)} listen-port {int(listen_port)} "
            f"private-key {safe_quote(key_path)}"
        )
        await self._run(f"ip link set {safe_quote(name)} up")

        return ToolResult(
            success=True,
            output=f"WireGuard interface '{name}' created\n  Address: {address}\n  Port: {listen_port}\n  Public Key: {pubkey}",
            side_effects=[
                f"WireGuard interface '{name}' created and active",
                f"Private key stored at {key_path}",
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
        """Add a peer to a WireGuard interface."""
        validate_name(interface, "interface")

        cmd_parts = [
            f"wg set {safe_quote(interface)} peer {safe_quote(public_key)}",
            f"allowed-ips {safe_quote(allowed_ips)}",
        ]
        if endpoint:
            cmd_parts.append(f"endpoint {safe_quote(endpoint)}")
        if persistent_keepalive:
            cmd_parts.append(f"persistent-keepalive {int(persistent_keepalive)}")

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
        """Remove a peer from a WireGuard interface."""
        validate_name(interface, "interface")
        rc, out, err = await self._run(
            f"wg set {safe_quote(interface)} peer {safe_quote(public_key)} remove"
        )
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
        """Generate a WireGuard client configuration for a new peer."""
        # Generate client keypair
        rc, client_privkey, _ = await self._run("wg genkey")
        if rc != 0:
            return ToolResult(success=False, error="Failed to generate client key")

        rc, client_pubkey, _ = await self._run_with_stdin("wg pubkey", client_privkey)
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

    # Network Diagnostics

    async def ping(self, target: str, count: int = 4) -> ToolResult:
        """Ping a host to check connectivity."""
        rc, out, err = await self._run(f"ping -c {int(count)} -W 5 {safe_quote(target)}")
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
        """Run traceroute to a target."""
        rc, out, err = await self._run(f"traceroute -w 3 -m 20 {safe_quote(target)}")
        success = rc == 0 or bool(out)

        return ToolResult(
            success=success,
            output=out if out else err,
            metadata={"target": target},
        )

    async def dns_lookup(self, hostname: str, record_type: str = "A") -> ToolResult:
        """Perform a DNS lookup."""
        validate_name(record_type, "record_type")
        rc, out, err = await self._run(f"dig +short {safe_quote(record_type)} {safe_quote(hostname)}")
        if rc != 0:
            return ToolResult(success=False, error=f"DNS lookup failed: {err}")

        return ToolResult(
            success=True,
            output=out if out else f"No {record_type} records found for {hostname}",
            metadata={"hostname": hostname, "record_type": record_type},
        )

    async def port_scan(self, target: str, ports: str = "1-1024") -> ToolResult:
        """Quick port scan on a target."""
        rc, out, err = await self._run(
            f"nmap -T4 --open -p {safe_quote(ports)} {safe_quote(target)} 2>/dev/null || ss -tlnp",
            check=False,
        )

        return ToolResult(
            success=True,
            output=out if out else "No results",
            metadata={"target": target, "ports": ports},
        )


    # ═══════════════════════════════════════════════════════════════
    # Tailscale — Secure mesh VPN (replaces manual WireGuard for
    # zero-config remote access to the homelab from anywhere)
    # ═══════════════════════════════════════════════════════════════

    async def tailscale_install(self) -> ToolResult:
        """Install Tailscale if not already present.

        Uses the official Tailscale installer script.
        Idempotent — safe to call multiple times.
        """
        # Check if already installed
        rc, out, _ = await self._run("which tailscale", check=False)
        if rc == 0:
            return ToolResult(
                success=True,
                output="Tailscale is already installed",
                metadata={"already_installed": True},
            )

        # Install via official script
        rc, out, err = await self._run(
            "curl -fsSL https://tailscale.com/install.sh | sh"
        )
        if rc != 0:
            return ToolResult(
                success=False,
                error=f"Tailscale installation failed: {err}",
            )

        # Enable and start tailscaled
        await self._run("systemctl enable --now tailscaled", check=False)

        return ToolResult(
            success=True,
            output="Tailscale installed and tailscaled service started",
            side_effects=[
                "Tailscale package installed",
                "tailscaled service enabled and started",
            ],
            metadata={"installed": True},
        )

    async def tailscale_up(
        self,
        auth_key: Optional[str] = None,
        hostname: Optional[str] = None,
        advertise_routes: Optional[List[str]] = None,
        advertise_exit_node: bool = False,
        accept_routes: bool = True,
        ssh: bool = True,
        shields_up: bool = False,
        reset: bool = False,
    ) -> ToolResult:
        """Connect to Tailscale (bring the node online).

        Args:
            auth_key: Pre-auth key for unattended setup (from Tailscale admin).
            hostname: Custom hostname on the tailnet.
            advertise_routes: Subnets to advertise (e.g., ["192.168.1.0/24"]).
            advertise_exit_node: Whether to offer this node as an exit node.
            accept_routes: Accept routes advertised by other nodes.
            ssh: Enable Tailscale SSH (access via `ssh user@hostname` over tailnet).
            shields_up: Block incoming connections (outbound only).
            reset: Reset settings to defaults before connecting.
        """
        cmd_parts = ["tailscale up"]

        if auth_key:
            cmd_parts.append(f"--auth-key={safe_quote(auth_key)}")
        if hostname:
            validate_name(hostname, "hostname")
            cmd_parts.append(f"--hostname={safe_quote(hostname)}")
        if advertise_routes:
            routes = ",".join(advertise_routes)
            cmd_parts.append(f"--advertise-routes={safe_quote(routes)}")
        if advertise_exit_node:
            cmd_parts.append("--advertise-exit-node")
        if accept_routes:
            cmd_parts.append("--accept-routes")
        if ssh:
            cmd_parts.append("--ssh")
        if shields_up:
            cmd_parts.append("--shields-up")
        if reset:
            cmd_parts.append("--reset")

        cmd = " ".join(cmd_parts)
        rc, out, err = await self._run(cmd)
        if rc != 0:
            # Check if it needs interactive auth
            if "https://login.tailscale.com" in (out + err):
                auth_url = ""
                for line in (out + err).splitlines():
                    if "https://login.tailscale.com" in line:
                        auth_url = line.strip()
                        break
                return ToolResult(
                    success=False,
                    output=f"Tailscale needs authentication. Visit:\n{auth_url}",
                    error="Authentication required",
                    metadata={"auth_url": auth_url, "needs_auth": True},
                )
            return ToolResult(success=False, error=f"tailscale up failed: {err or out}")

        side_effects = ["Connected to Tailscale tailnet"]
        if advertise_routes:
            side_effects.append(f"Advertising routes: {advertise_routes}")
        if advertise_exit_node:
            side_effects.append("Advertising as exit node")
        if ssh:
            side_effects.append("Tailscale SSH enabled")

        return ToolResult(
            success=True,
            output=f"Tailscale connected. {out}".strip(),
            side_effects=side_effects,
            metadata={
                "hostname": hostname,
                "exit_node": advertise_exit_node,
                "ssh": ssh,
                "routes": advertise_routes,
            },
        )

    async def tailscale_down(self) -> ToolResult:
        """Disconnect from Tailscale (take node offline)."""
        rc, out, err = await self._run("tailscale down")
        if rc != 0:
            return ToolResult(success=False, error=f"tailscale down failed: {err}")

        return ToolResult(
            success=True,
            output="Tailscale disconnected",
            side_effects=["Node taken offline from tailnet"],
        )

    async def tailscale_status(self) -> ToolResult:
        """Get Tailscale connection status and peer list.

        Returns the current node status, IP addresses, and all
        connected peers with their online/offline state.
        """
        rc, out, err = await self._run("tailscale status --json", check=False)
        if rc != 0:
            # Try non-JSON format
            rc2, out2, err2 = await self._run("tailscale status", check=False)
            if rc2 != 0:
                return ToolResult(
                    success=False,
                    error=f"Tailscale not running or not connected: {err2 or err}",
                    metadata={"connected": False},
                )
            return ToolResult(
                success=True,
                output=out2,
                metadata={"connected": True, "format": "text"},
            )

        return ToolResult(
            success=True,
            output=out,
            metadata={"connected": True, "format": "json"},
        )

    async def tailscale_ip(self) -> ToolResult:
        """Get this node's Tailscale IP addresses."""
        rc, out, err = await self._run("tailscale ip", check=False)
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to get Tailscale IP: {err}")

        ips = [ip.strip() for ip in out.splitlines() if ip.strip()]
        return ToolResult(
            success=True,
            output=f"Tailscale IPs: {', '.join(ips)}",
            metadata={"ips": ips, "ipv4": ips[0] if ips else None},
        )

    async def tailscale_peers(self) -> ToolResult:
        """List all peers on the tailnet with their status."""
        rc, out, err = await self._run("tailscale status", check=False)
        if rc != 0:
            return ToolResult(success=False, error=f"Cannot get peers: {err}")

        # Parse the output into structured data
        peers = []
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 3 and not line.startswith("#"):
                peers.append({
                    "ip": parts[0],
                    "hostname": parts[1],
                    "user": parts[2] if len(parts) > 2 else "",
                    "os": parts[3] if len(parts) > 3 else "",
                    "online": "offline" not in line.lower(),
                })

        return ToolResult(
            success=True,
            output=out,
            metadata={"peers": peers, "peer_count": len(peers)},
        )

    async def tailscale_ping(self, target: str) -> ToolResult:
        """Ping a peer via Tailscale (tests direct connection)."""
        rc, out, err = await self._run(
            f"tailscale ping --c 3 {safe_quote(target)}", check=False
        )
        success = rc == 0 or "pong" in (out + err).lower()

        return ToolResult(
            success=success,
            output=out or err,
            metadata={"target": target, "reachable": success},
        )

    async def tailscale_serve(
        self,
        port: int,
        protocol: str = "https",
        path: str = "/",
        bg: bool = True,
    ) -> ToolResult:
        """Expose a local service via Tailscale Serve (tailnet only).

        Makes a local port accessible to other nodes on your tailnet
        without opening any firewall ports.

        Args:
            port: Local port to expose.
            protocol: "https" (default) or "http".
            path: URL path to serve at (default "/").
            bg: Run in background mode.
        """
        bg_flag = "--bg" if bg else ""
        target = f"{protocol}://localhost:{int(port)}"

        rc, out, err = await self._run(
            f"tailscale serve {bg_flag} {safe_quote(path)} {safe_quote(target)}",
            check=False,
        )
        if rc != 0:
            return ToolResult(success=False, error=f"tailscale serve failed: {err or out}")

        return ToolResult(
            success=True,
            output=f"Serving localhost:{port} on tailnet at {path}",
            side_effects=[f"Port {port} exposed to tailnet via Tailscale Serve"],
            metadata={"port": port, "protocol": protocol, "path": path},
        )

    async def tailscale_serve_status(self) -> ToolResult:
        """Show what's currently being served via Tailscale Serve."""
        rc, out, err = await self._run("tailscale serve status", check=False)
        if rc != 0:
            return ToolResult(
                success=True,
                output="No services currently served via Tailscale",
                metadata={"serving": []},
            )

        return ToolResult(
            success=True,
            output=out,
            metadata={"format": "serve_status"},
        )

    async def tailscale_serve_off(self, path: str = "/") -> ToolResult:
        """Stop serving a path via Tailscale Serve."""
        rc, out, err = await self._run(
            f"tailscale serve off {safe_quote(path)}", check=False
        )
        return ToolResult(
            success=True,
            output=f"Stopped serving at {path}",
            side_effects=[f"Tailscale Serve at {path} disabled"],
        )

    async def tailscale_funnel(
        self,
        port: int,
        protocol: str = "https",
        path: str = "/",
        bg: bool = True,
    ) -> ToolResult:
        """Expose a local service to the PUBLIC internet via Tailscale Funnel.

        ⚠️ DANGEROUS: This makes the service accessible to anyone on the internet.
        Only use for services designed for public access.

        Args:
            port: Local port to funnel.
            protocol: "https" only (Funnel always uses HTTPS).
            path: URL path.
            bg: Run in background.
        """
        bg_flag = "--bg" if bg else ""
        target = f"https://localhost:{int(port)}"

        rc, out, err = await self._run(
            f"tailscale funnel {bg_flag} {safe_quote(path)} {safe_quote(target)}",
            check=False,
        )
        if rc != 0:
            return ToolResult(success=False, error=f"tailscale funnel failed: {err or out}")

        return ToolResult(
            success=True,
            output=f"Funneling localhost:{port} to the public internet at {path}\n⚠️ This is publicly accessible!",
            side_effects=[
                f"Port {port} exposed to PUBLIC INTERNET via Tailscale Funnel",
                "Anyone with the URL can access this service",
            ],
            metadata={"port": port, "public": True, "path": path},
        )

    async def tailscale_funnel_off(self, path: str = "/") -> ToolResult:
        """Stop funneling a path to the public internet."""
        rc, out, err = await self._run(
            f"tailscale funnel off {safe_quote(path)}", check=False
        )
        return ToolResult(
            success=True,
            output=f"Funnel stopped at {path} — no longer publicly accessible",
            side_effects=[f"Public Funnel at {path} disabled"],
        )

    async def tailscale_set_exit_node(self, node: str) -> ToolResult:
        """Route all traffic through a Tailscale exit node.

        Args:
            node: Hostname or IP of the exit node (use "" to disable).
        """
        if node:
            rc, out, err = await self._run(
                f"tailscale set --exit-node={safe_quote(node)}"
            )
        else:
            rc, out, err = await self._run("tailscale set --exit-node=")

        if rc != 0:
            return ToolResult(success=False, error=f"Failed to set exit node: {err}")

        if node:
            return ToolResult(
                success=True,
                output=f"All traffic now routed through exit node: {node}",
                side_effects=[f"Exit node set to {node}"],
                metadata={"exit_node": node},
            )
        else:
            return ToolResult(
                success=True,
                output="Exit node disabled — using direct routing",
                side_effects=["Exit node routing disabled"],
            )

    async def tailscale_cert(self, domain: str) -> ToolResult:
        """Get a TLS certificate for a Tailscale domain.

        Tailscale can provision HTTPS certs for *.ts.net domains.
        These auto-renew and are trusted by browsers.

        Args:
            domain: The domain to get a cert for (e.g., "mk.tail12345.ts.net").
        """
        rc, out, err = await self._run(
            f"tailscale cert {safe_quote(domain)}", check=False
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to get cert: {err or out}")

        return ToolResult(
            success=True,
            output=f"TLS certificate provisioned for {domain}",
            side_effects=[f"Certificate files created for {domain}"],
            metadata={"domain": domain},
        )

    async def tailscale_lock_status(self) -> ToolResult:
        """Check Tailscale network lock (tailnet lock) status."""
        rc, out, err = await self._run("tailscale lock status", check=False)
        return ToolResult(
            success=True,
            output=out or "Tailnet lock not enabled",
            metadata={"format": "lock_status"},
        )
