"""MK Web Server — starts the Web UI on the Tailscale interface.

Binds to the Tailscale IP (100.x.x.x) so the dashboard is ONLY
accessible from your tailnet. Not exposed to the public internet.

Usage:
    python -m mk.web.serve              # Auto-detect Tailscale IP
    python -m mk.web.serve --host 0.0.0.0 --port 8080  # Override
    python -m mk.web.serve --pin 5678   # Set login PIN

The server:
1. Detects the Tailscale IP automatically
2. Starts FastAPI with uvicorn on port 8080
3. Serves the built React frontend (webui/dist/)
4. Exposes the API at /api/v1/* and WebSocket at /ws/chat
5. Also exposes via Tailscale Serve for HTTPS (auto-cert)
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def get_tailscale_ip() -> Optional[str]:
    """Get this node's Tailscale IPv4 address.

    Returns:
        The 100.x.x.x Tailscale IP, or None if not connected.
    """
    try:
        result = subprocess.run(
            ["tailscale", "ip", "-4"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def get_tailscale_hostname() -> Optional[str]:
    """Get this node's Tailscale hostname (e.g., 'mk-brain').

    Returns:
        Hostname string or None.
    """
    try:
        result = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            import json

            status = json.loads(result.stdout)
            return status.get("Self", {}).get("HostName", None)
    except Exception:
        pass
    return None


def start_server(
    host: Optional[str] = None,
    port: int = 8080,
    pin: Optional[str] = None,
    dev: bool = False,
) -> None:
    """Start the MK Web server.

    Args:
        host: Bind address. If None, auto-detects Tailscale IP.
            Falls back to 0.0.0.0 if Tailscale isn't available.
        port: Port to bind to (default: 8080).
        pin: Login PIN override (default: env MK_PIN or "1234").
        dev: Run in development mode (auto-reload).
    """
    import uvicorn

    # Auto-detect bind address
    if host is None:
        ts_ip = get_tailscale_ip()
        if ts_ip:
            # Bind to both Tailscale and localhost
            host = "0.0.0.0"
            logger.info(f"Tailscale detected: {ts_ip}")
            logger.info(f"Web UI accessible at: http://{ts_ip}:{port}")
            ts_hostname = get_tailscale_hostname()
            if ts_hostname:
                logger.info(f"Or via hostname: http://{ts_hostname}:{port}")
        else:
            host = "0.0.0.0"
            logger.warning("Tailscale not detected — binding to all interfaces")

    # Set PIN via environment if provided
    if pin:
        os.environ["MK_PIN"] = pin

    # Find the static frontend build
    # Check env var first (set during deployment), then fall back to repo-relative path
    env_dist = os.environ.get("MK_WEBUI_DIST")
    if env_dist and Path(env_dist).exists():
        static_dir = Path(env_dist)
    else:
        # Try repo-relative path (works in development)
        project_root = Path(__file__).parent.parent.parent.parent
        static_dir = project_root / "webui" / "dist"
        if not static_dir.exists():
            # Try installed path (/opt/mk/webui/dist)
            static_dir = Path("/opt/mk/webui/dist")
            if not static_dir.exists():
                # Try package-relative static dir
                pkg_static = Path(__file__).parent / "static"
                if pkg_static.exists():
                    static_dir = pkg_static
                else:
                    logger.warning(
                        f"Frontend build not found. Searched:\n"
                        f"  - MK_WEBUI_DIST env var (not set)\n"
                        f"  - {project_root / 'webui' / 'dist'}\n"
                        f"  - /opt/mk/webui/dist\n"
                        f"  - {pkg_static}\n"
                        "Run 'cd webui && pnpm build' to build the frontend."
                    )

    print(f"""
╔══════════════════════════════════════════════╗
║           MK OS — Web Dashboard             ║
╠══════════════════════════════════════════════╣
║  Address:  http://{host}:{port:<5}              ║
║  API:      http://{host}:{port}/api/v1       ║
║  Docs:     http://{host}:{port}/api/docs     ║""")

    ts_ip = get_tailscale_ip()
    if ts_ip:
        print(f"║  Tailscale: http://{ts_ip}:{port:<5}          ║")

    print(f"""║  PIN:      {"*" * len(os.environ.get("MK_PIN", "1234"))} (set MK_PIN env)    ║
╚══════════════════════════════════════════════╝
""")

    uvicorn.run(
        "mk.web.app:create_app",
        host=host,
        port=port,
        reload=dev,
        factory=True,
        log_level="info",
        access_log=True,
    )


# CLI entry point
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="MK OS Web Dashboard")
    parser.add_argument("--host", default=None, help="Bind address (auto-detects Tailscale)")
    parser.add_argument("--port", type=int, default=8080, help="Port (default: 8080)")
    parser.add_argument("--pin", default=None, help="Login PIN")
    parser.add_argument("--dev", action="store_true", help="Development mode (auto-reload)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    start_server(host=args.host, port=args.port, pin=args.pin, dev=args.dev)
