"""Homelab Extras - Power, reverse proxy, DDNS, monitoring, UPS.

Wraps common homelab open-source tools that don't fit in other managers:
    - Wake-on-LAN (etherwake/wakeonlan)
    - UPS monitoring (NUT - Network UPS Tools)
    - Reverse proxy (Caddy - auto HTTPS)
    - Dynamic DNS (ddclient)
    - Let's Encrypt certs (certbot or Caddy)
    - Monitoring (node_exporter + prometheus queries)
    - Power management for remote machines
    - Temperature monitoring (lm-sensors)
    - SMART disk health alerts
    - Speedtest (speedtest-cli)
"""

from __future__ import annotations

import logging

from mk.tools.base import ToolResult
from ._shell import safe_quote
from ._run import run_cmd

logger = logging.getLogger(__name__)


class HomelabManager:
    """Miscellaneous homelab tools — power, proxy, monitoring, DDNS."""

    # --- Wake-on-LAN ---

    async def wake_machine(self, mac_address: str, interface: str = "eth0") -> ToolResult:
        """Send a Wake-on-LAN magic packet to power on a remote machine.

        Uses etherwake or wakeonlan (whichever is available).

        Args:
            mac_address: Target MAC address (e.g., "AA:BB:CC:DD:EE:FF").
            interface: Network interface to send from.
        """
        # Try etherwake first, then wakeonlan
        rc, out, err = await run_cmd(
            f"etherwake -i {safe_quote(interface)} {safe_quote(mac_address)}",
            sudo=True,
        )
        if rc != 0:
            rc, out, err = await run_cmd(
                f"wakeonlan -i {safe_quote(interface)} {safe_quote(mac_address)}",
                sudo=False,
            )
        if rc != 0:
            return ToolResult(
                success=False, error=f"WoL failed (install etherwake or wakeonlan): {err}"
            )

        return ToolResult(
            success=True,
            output=f"Wake-on-LAN sent to {mac_address}",
            side_effects=[f"Magic packet sent via {interface}"],
            metadata={"mac": mac_address},
        )

    # --- UPS (Network UPS Tools) ---

    async def ups_status(self) -> ToolResult:
        """Get UPS status from NUT (Network UPS Tools).

        Returns battery %, load, status, runtime.
        """
        rc, out, err = await run_cmd("upsc ups@localhost 2>/dev/null", sudo=False)
        if rc != 0:
            return ToolResult(success=False, error=f"NUT not available or no UPS configured: {err}")
        return ToolResult(success=True, output=out, metadata={"source": "nut"})

    async def ups_battery_percent(self) -> ToolResult:
        """Get UPS battery percentage only."""
        rc, out, err = await run_cmd("upsc ups@localhost battery.charge 2>/dev/null", sudo=False)
        if rc != 0:
            return ToolResult(success=False, error="Cannot read UPS battery")
        return ToolResult(success=True, output=f"Battery: {out}%", metadata={"percent": out})

    # --- Reverse Proxy (Caddy) ---

    async def proxy_status(self) -> ToolResult:
        """Check if Caddy reverse proxy is running and show config."""
        rc, out, err = await run_cmd("systemctl is-active caddy", sudo=True)
        active = out.strip() == "active"

        rc2, config, _ = await run_cmd("cat /etc/caddy/Caddyfile 2>/dev/null", sudo=True)

        return ToolResult(
            success=True,
            output=f"Caddy: {'running' if active else 'stopped'}\n\n{config if config else '(no config)'}",
            metadata={"active": active},
        )

    async def add_proxy_site(
        self,
        domain: str,
        upstream: str,
        https: bool = True,
    ) -> ToolResult:
        """Add a reverse proxy entry to Caddy.

        Caddy auto-provisions HTTPS via Let's Encrypt.

        Args:
            domain: External domain (e.g., "plex.example.com").
            upstream: Backend address (e.g., "localhost:32400").
            https: Use HTTPS with auto cert (default True).
        """
        # Build Caddy site block
        if https:
            block = f"{domain} {{\n    reverse_proxy {upstream}\n}}\n"
        else:
            block = f"http://{domain} {{\n    reverse_proxy {upstream}\n}}\n"

        # Append to Caddyfile
        rc, _, err = await run_cmd(
            "tee -a /etc/caddy/Caddyfile",
            sudo=True,
            stdin_data=f"\n{block}",
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to update Caddyfile: {err}")

        # Reload Caddy
        await run_cmd("systemctl reload caddy", sudo=True)

        return ToolResult(
            success=True,
            output=f"Proxy added: {domain} -> {upstream}" + (" (auto HTTPS)" if https else ""),
            side_effects=["Caddyfile updated", "Caddy reloaded"],
            metadata={"domain": domain, "upstream": upstream},
        )

    async def remove_proxy_site(self, domain: str) -> ToolResult:
        """Remove a proxy entry from Caddy."""
        # Remove the domain block (simple approach: sed between domain and closing brace)
        escaped = domain.replace(".", "\\.")
        rc, _, err = await run_cmd(
            f"sed -i '/{escaped}/,/}}/d' /etc/caddy/Caddyfile",
            sudo=True,
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to remove site: {err}")

        await run_cmd("systemctl reload caddy", sudo=True)
        return ToolResult(success=True, output=f"Proxy for '{domain}' removed")

    # --- Dynamic DNS ---

    async def ddns_status(self) -> ToolResult:
        """Check DDNS client status (ddclient)."""
        rc, out, err = await run_cmd("systemctl status ddclient --no-pager 2>/dev/null", sudo=True)
        if rc != 0 and not out:
            return ToolResult(success=False, error="ddclient not installed or not running")
        return ToolResult(success=True, output=out)

    async def ddns_update_now(self) -> ToolResult:
        """Force an immediate DDNS update."""
        rc, out, err = await run_cmd("ddclient -force", sudo=True)
        if rc != 0:
            return ToolResult(success=False, error=f"DDNS update failed: {err}")
        return ToolResult(success=True, output=f"DDNS updated: {out}")

    async def get_public_ip(self) -> ToolResult:
        """Get the current public IP address."""
        rc, out, err = await run_cmd("curl -s https://ifconfig.me", sudo=False, timeout=10)
        if rc != 0:
            # Fallback
            rc, out, err = await run_cmd("curl -s https://api.ipify.org", sudo=False, timeout=10)
        if rc != 0:
            return ToolResult(success=False, error="Cannot determine public IP")
        return ToolResult(success=True, output=f"Public IP: {out}", metadata={"ip": out})

    # --- Monitoring ---

    async def system_temperatures(self) -> ToolResult:
        """Get CPU/system temperatures from lm-sensors."""
        rc, out, err = await run_cmd("sensors 2>/dev/null", sudo=False)
        if rc != 0:
            return ToolResult(success=False, error="lm-sensors not available (install lm-sensors)")
        return ToolResult(success=True, output=out)

    async def speedtest(self) -> ToolResult:
        """Run an internet speed test."""
        rc, out, err = await run_cmd("speedtest-cli --simple 2>/dev/null", sudo=False, timeout=60)
        if rc != 0:
            # Try ookla speedtest
            rc, out, err = await run_cmd(
                "speedtest --format=human-readable 2>/dev/null", sudo=False, timeout=60
            )
        if rc != 0:
            return ToolResult(success=False, error="speedtest-cli not available")
        return ToolResult(success=True, output=out)

    async def top_processes(self, count: int = 10) -> ToolResult:
        """Show top processes by CPU/memory usage."""
        rc, out, err = await run_cmd(
            f"ps aux --sort=-%mem | head -{count + 1}",
            sudo=False,
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed: {err}")
        return ToolResult(success=True, output=out)

    async def check_port_open(self, host: str, port: int) -> ToolResult:
        """Check if a port is reachable (quick connectivity test)."""
        rc, out, err = await run_cmd(
            f"timeout 5 bash -c 'echo > /dev/tcp/{safe_quote(host)}/{port}' 2>&1",
            sudo=False,
            timeout=10,
        )
        reachable = rc == 0
        status = "open" if reachable else "closed/unreachable"
        return ToolResult(
            success=True,
            output=f"{host}:{port} is {status}",
            metadata={"host": host, "port": port, "open": reachable},
        )

    # --- SSL Certificates ---

    async def list_certs(self) -> ToolResult:
        """List SSL certificates (certbot managed)."""
        rc, out, err = await run_cmd("certbot certificates 2>/dev/null", sudo=True)
        if rc != 0:
            return ToolResult(success=False, error="certbot not available")
        return ToolResult(success=True, output=out)

    async def renew_certs(self) -> ToolResult:
        """Renew all SSL certificates."""
        rc, out, err = await run_cmd("certbot renew", sudo=True, timeout=120)
        if rc != 0:
            return ToolResult(success=False, error=f"Renewal failed: {err}")
        return ToolResult(success=True, output=out, side_effects=["Certificates renewed"])

    # --- Cron / Scheduled Tasks ---

    async def list_cron_jobs(self, user: str = "root") -> ToolResult:
        """List cron jobs for a user."""
        rc, out, err = await run_cmd(f"crontab -l -u {safe_quote(user)} 2>/dev/null", sudo=True)
        if rc != 0:
            return ToolResult(success=True, output=f"No cron jobs for {user}")
        return ToolResult(success=True, output=out)

    # --- Disk Health Summary ---

    async def disk_health_summary(self) -> ToolResult:
        """Quick SMART health check across all disks."""
        rc, out, err = await run_cmd(
            "for disk in $(lsblk -dpn -o NAME | grep -E 'sd|nvme'); do "
            "echo \"$disk: $(smartctl -H $disk 2>/dev/null | grep -i 'overall\\|result' | head -1)\"; "
            "done",
            sudo=True,
        )
        if rc != 0 or not out:
            return ToolResult(success=False, error="smartctl not available or no disks found")
        return ToolResult(success=True, output=out)

    # --- Power Management ---

    async def suspend_system(self) -> ToolResult:
        """Suspend the system to RAM."""
        rc, _, err = await run_cmd("systemctl suspend", sudo=True)
        if rc != 0:
            return ToolResult(success=False, error=f"Suspend failed: {err}")
        return ToolResult(success=True, output="System suspended")

    async def schedule_wake(self, seconds_from_now: int) -> ToolResult:
        """Schedule a system wake from suspend/sleep using RTC alarm.

        Args:
            seconds_from_now: Seconds until wake.
        """
        rc, _, err = await run_cmd(
            f"rtcwake -m no -s {seconds_from_now}",
            sudo=True,
        )
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to set wake alarm: {err}")
        return ToolResult(
            success=True,
            output=f"System will wake in {seconds_from_now}s",
            metadata={"wake_seconds": seconds_from_now},
        )
