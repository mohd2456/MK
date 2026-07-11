"""FastAPI application — main entry point for the MK Web API.

Creates and configures the FastAPI app with all routes,
WebSocket handlers, CORS, static files, and middleware.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import (
    Cookie,
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from mk.observability import RequestIDMiddleware, metrics, setup_logging

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# Input Validation
# ═══════════════════════════════════════════════════════════════

# Strict pattern for identifiers used in shell commands (service names,
# device names, pool names, container names, package names).
# Only allows alphanumeric characters, dots, hyphens, underscores, and
# the at-sign (for package version specifiers like package@version).
_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9._@:+\-]+$")

# Maximum length for shell-interpolated values
_MAX_NAME_LENGTH = 128


def _validate_shell_identifier(value: str, label: str = "name") -> str:
    """Validate that a value is safe for use in shell commands.

    Args:
        value: The user-supplied value to validate.
        label: Human-readable label for error messages.

    Returns:
        The validated value (stripped of whitespace).

    Raises:
        HTTPException: If the value contains unsafe characters.
    """
    value = value.strip()
    if not value:
        raise HTTPException(400, f"Invalid {label}: must not be empty")
    if len(value) > _MAX_NAME_LENGTH:
        raise HTTPException(400, f"Invalid {label}: exceeds maximum length ({_MAX_NAME_LENGTH})")
    if not _SAFE_NAME_RE.match(value):
        raise HTTPException(
            400,
            f"Invalid {label}: contains disallowed characters. "
            f"Only alphanumeric, dots, hyphens, underscores, @, :, and + are permitted.",
        )
    return value

# ═══════════════════════════════════════════════════════════════
# Pydantic Models for API
# ═══════════════════════════════════════════════════════════════


class LoginRequest(BaseModel):
    pin: str = Field(description="4-8 digit PIN")


class LoginResponse(BaseModel):
    token: str
    expires: float


class ChatMessage(BaseModel):
    content: str
    context: Dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    content: str
    actions: List[Dict[str, Any]] = Field(default_factory=list)


class DashboardSummary(BaseModel):
    cpu_percent: float = 0.0
    ram_used_gb: float = 0.0
    ram_total_gb: float = 0.0
    ram_percent: float = 0.0
    disk_used_tb: float = 0.0
    disk_total_tb: float = 0.0
    disk_percent: float = 0.0
    network_in_mbps: float = 0.0
    network_out_mbps: float = 0.0
    uptime_seconds: float = 0.0
    containers_running: int = 0
    containers_total: int = 0
    tailscale_connected: bool = False
    tailscale_ip: str = ""


# ═══════════════════════════════════════════════════════════════
# Session Management
# ═══════════════════════════════════════════════════════════════

# In-memory session store (simple for homelab use)
_sessions: Dict[str, Dict[str, Any]] = {}
_login_attempts: Dict[str, List[float]] = {}
_pin_hash: Optional[str] = None
_mk_engine: Optional[Any] = None
_start_time: float = time.time()

SESSION_DURATION = 7 * 24 * 3600  # 7 days
MAX_ATTEMPTS = 10
LOCKOUT_SECONDS = 300


def _hash_pin(pin: str) -> str:
    """Hash a PIN with a static salt (homelab-grade, not enterprise)."""
    salt = "mk-os-pin-salt-v1"
    return hashlib.sha256(f"{salt}:{pin}".encode()).hexdigest()


def _verify_pin(pin: str) -> bool:
    """Verify a PIN against stored hash."""
    global _pin_hash
    if _pin_hash is None:
        # Default PIN is "1234" if none configured
        _pin_hash = _hash_pin(os.environ.get("MK_PIN", "1234"))
    return hmac.compare_digest(_hash_pin(pin), _pin_hash)


def _create_session() -> str:
    """Create a new session and return the token."""
    token = secrets.token_urlsafe(32)
    _sessions[token] = {
        "created": time.time(),
        "expires": time.time() + SESSION_DURATION,
    }
    return token


def _validate_session(token: Optional[str]) -> bool:
    """Check if a session token is valid."""
    if not token:
        return False
    session = _sessions.get(token)
    if not session:
        return False
    if time.time() > session["expires"]:
        del _sessions[token]
        return False
    return True


def _check_lockout(ip: str) -> bool:
    """Check if an IP is locked out from login attempts."""
    attempts = _login_attempts.get(ip, [])
    # Clean old attempts
    now = time.time()
    attempts = [t for t in attempts if now - t < LOCKOUT_SECONDS]
    _login_attempts[ip] = attempts
    return len(attempts) >= MAX_ATTEMPTS


def _record_attempt(ip: str) -> None:
    """Record a login attempt."""
    _login_attempts.setdefault(ip, []).append(time.time())


# ═══════════════════════════════════════════════════════════════
# Rate Limiting
# ═══════════════════════════════════════════════════════════════


class RateLimiter:
    """Simple in-memory rate limiter per IP address.

    Allows a configurable number of requests per window (default 100/min).
    Includes periodic cleanup to prevent unbounded memory growth from
    inactive IPs, and caps the total number of tracked IPs.
    """

    # Maximum number of IPs to track before forced eviction
    MAX_TRACKED_IPS = 10_000
    # How often to run the full cleanup pass (seconds)
    CLEANUP_INTERVAL = 300  # 5 minutes

    def __init__(self, max_requests: int = 100, window_seconds: int = 60) -> None:
        self._max_requests = max_requests
        self._window = window_seconds
        self._requests: Dict[str, List[float]] = {}
        self._last_cleanup: float = time.time()

    def _cleanup(self) -> None:
        """Remove IPs with no recent requests to prevent memory leaks."""
        now = time.time()
        stale_ips = []
        for ip, timestamps in self._requests.items():
            # Keep only timestamps within the window
            active = [t for t in timestamps if now - t < self._window]
            if not active:
                stale_ips.append(ip)
            else:
                self._requests[ip] = active
        for ip in stale_ips:
            del self._requests[ip]
        self._last_cleanup = now

    def is_allowed(self, ip: str) -> bool:
        """Check if the IP is within rate limits."""
        now = time.time()

        # Periodic cleanup of stale entries
        if now - self._last_cleanup > self.CLEANUP_INTERVAL:
            self._cleanup()

        # If we have too many tracked IPs, force a cleanup
        if len(self._requests) >= self.MAX_TRACKED_IPS:
            self._cleanup()
            # If still over limit after cleanup, evict oldest entries
            if len(self._requests) >= self.MAX_TRACKED_IPS:
                # Remove the half with oldest last-activity
                sorted_ips = sorted(
                    self._requests.keys(),
                    key=lambda k: self._requests[k][-1] if self._requests[k] else 0,
                )
                for old_ip in sorted_ips[: len(sorted_ips) // 2]:
                    del self._requests[old_ip]

        requests = self._requests.get(ip, [])
        # Prune old entries for this IP
        requests = [t for t in requests if now - t < self._window]
        self._requests[ip] = requests
        if len(requests) >= self._max_requests:
            return False
        requests.append(now)
        return True

    def remaining(self, ip: str) -> int:
        """Get remaining requests for this IP in the current window."""
        now = time.time()
        requests = self._requests.get(ip, [])
        requests = [t for t in requests if now - t < self._window]
        return max(0, self._max_requests - len(requests))


# ═══════════════════════════════════════════════════════════════
# Dependencies
# ═══════════════════════════════════════════════════════════════


async def require_auth(
    request: Request,
    mk_session: Optional[str] = Cookie(None),
) -> str:
    """Dependency: require valid session token."""
    # Check cookie
    if _validate_session(mk_session):
        return mk_session

    # Check Authorization header
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        if _validate_session(token):
            return token

    raise HTTPException(status_code=401, detail="Not authenticated")


# ═══════════════════════════════════════════════════════════════
# App Factory
# ═══════════════════════════════════════════════════════════════


def create_app(
    mk_engine: Optional[Any] = None,
    pin: Optional[str] = None,
    static_dir: Optional[str] = None,
) -> FastAPI:
    """Create the FastAPI application.

    Args:
        mk_engine: The MKEngineV2 instance (for processing commands).
        pin: Override PIN (default: env MK_PIN or "1234").
        static_dir: Path to the built React frontend (webui/dist).

    Returns:
        Configured FastAPI app.
    """
    global _mk_engine, _pin_hash

    _mk_engine = mk_engine
    if pin:
        _pin_hash = _hash_pin(pin)

    # Clear sessions for fresh app instances (important for testing)
    _sessions.clear()
    _login_attempts.clear()

    app = FastAPI(
        title="MK OS",
        description="Personal AI Operating System — Web API",
        version="2.0.0",
        docs_url="/api/docs",
        redoc_url=None,
    )

    # CORS (allow Tailscale origins)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Tailscale-only network, so * is safe
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Structured logging and request tracking
    setup_logging(level=os.environ.get("MK_LOG_LEVEL", "INFO"), json_format=True)
    app.add_middleware(RequestIDMiddleware)

    # Rate limiting middleware
    api_rate_limiter = RateLimiter(max_requests=100, window_seconds=60)

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        """Apply rate limiting to API routes (100 req/min per IP)."""
        if request.url.path.startswith("/api"):
            ip = request.client.host if request.client else "unknown"
            if not api_rate_limiter.is_allowed(ip):
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded. Try again later."},
                )
        response = await call_next(request)
        return response

    # Register routes
    _register_auth_routes(app)
    _register_dashboard_routes(app)
    _register_chat_routes(app)
    _register_storage_routes(app)
    _register_apps_routes(app)
    _register_network_routes(app)
    _register_system_routes(app)
    _register_media_routes(app)
    _register_protection_routes(app)
    _register_keys_routes(app)
    _register_metrics_routes(app)
    _register_websocket(app)

    # Serve static frontend (if build exists)
    if static_dir is None:
        # Check env var first (set during deployment), then fall back to repo-relative path
        env_dist = os.environ.get("MK_WEBUI_DIST")
        if env_dist and Path(env_dist).exists():
            static_dir = env_dist
        else:
            # Try repo-relative path (works in development)
            candidate = Path(__file__).parent.parent.parent.parent / "webui" / "dist"
            if candidate.exists():
                static_dir = str(candidate)
            else:
                # Try installed package layout (/opt/mk/webui/dist)
                installed_candidate = Path("/opt/mk/webui/dist")
                if installed_candidate.exists():
                    static_dir = str(installed_candidate)
                else:
                    # Try package-relative static dir
                    pkg_static = Path(__file__).parent / "static"
                    if pkg_static.exists():
                        static_dir = str(pkg_static)

    if static_dir and Path(static_dir).exists():
        # Serve index.html for all non-API routes (SPA fallback)
        @app.middleware("http")
        async def spa_fallback(request: Request, call_next):
            response = await call_next(request)
            if (
                response.status_code == 404
                and not request.url.path.startswith("/api")
                and not request.url.path.startswith("/ws")
            ):
                index_path = Path(static_dir) / "index.html"
                if index_path.exists():
                    return Response(
                        content=index_path.read_text(),
                        media_type="text/html",
                    )
            return response

        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app


# ═══════════════════════════════════════════════════════════════
# Route Registration
# ═══════════════════════════════════════════════════════════════


def _register_auth_routes(app: FastAPI) -> None:
    """Auth routes: login, logout, status."""

    @app.post("/api/v1/auth/login")
    async def login(req: LoginRequest, request: Request):
        ip = request.client.host if request.client else "unknown"

        if _check_lockout(ip):
            raise HTTPException(429, "Too many attempts. Try again in 5 minutes.")

        if not _verify_pin(req.pin):
            _record_attempt(ip)
            raise HTTPException(401, "Invalid PIN")

        token = _create_session()
        response = JSONResponse({"token": token, "expires": time.time() + SESSION_DURATION})
        response.set_cookie(
            "mk_session",
            token,
            max_age=SESSION_DURATION,
            httponly=True,
            samesite="lax",
        )
        return response

    @app.post("/api/v1/auth/logout")
    async def logout(token: str = Depends(require_auth)):
        _sessions.pop(token, None)
        response = JSONResponse({"status": "logged out"})
        response.delete_cookie("mk_session")
        return response

    @app.get("/api/v1/auth/status")
    async def auth_status(request: Request, mk_session: Optional[str] = Cookie(None)):
        valid = _validate_session(mk_session)
        return {"authenticated": valid}


def _register_dashboard_routes(app: FastAPI) -> None:
    """Dashboard routes: summary, alerts, activity."""

    @app.get("/api/v1/dashboard/summary", dependencies=[Depends(require_auth)])
    async def dashboard_summary():
        """Get system health overview."""
        import os

        # Read real system metrics
        cpu = 0.0
        try:
            load = os.getloadavg()[0]
            cpu_count = os.cpu_count() or 1
            cpu = min(100.0, (load / cpu_count) * 100.0)
        except Exception:
            pass

        ram_total = 0.0
        ram_used = 0.0
        try:
            with open("/proc/meminfo") as f:
                info = {}
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        info[parts[0].rstrip(":")] = int(parts[1])
                ram_total = info.get("MemTotal", 0) / (1024 * 1024)
                available = info.get("MemAvailable", info.get("MemFree", 0))
                ram_used = (info.get("MemTotal", 0) - available) / (1024 * 1024)
        except Exception:
            pass

        disk_total = 0.0
        disk_used = 0.0
        try:
            st = os.statvfs("/")
            disk_total = (st.f_frsize * st.f_blocks) / (1024**4)
            disk_used = (st.f_frsize * (st.f_blocks - st.f_bavail)) / (1024**4)
        except Exception:
            pass

        # System uptime from /proc/uptime (not process uptime)
        uptime = 0.0
        try:
            with open("/proc/uptime") as f:
                uptime = float(f.read().split()[0])
        except Exception:
            uptime = time.time() - _start_time

        # Network throughput from /proc/net/dev
        net_in_mbps = 0.0
        net_out_mbps = 0.0
        try:
            with open("/proc/net/dev") as f:
                for line in f:
                    line = line.strip()
                    if ":" not in line:
                        continue
                    iface, data = line.split(":", 1)
                    iface = iface.strip()
                    # Skip loopback
                    if iface == "lo":
                        continue
                    parts = data.split()
                    if len(parts) >= 9:
                        rx_bytes = int(parts[0])
                        tx_bytes = int(parts[8])
                        # Convert to MB/s approximation based on uptime
                        # This gives average throughput; for real-time you'd diff two readings
                        if uptime > 0:
                            net_in_mbps += rx_bytes / (1024 * 1024)
                            net_out_mbps += tx_bytes / (1024 * 1024)
            # If uptime is high, these will be cumulative totals not rates
            # For a better UX, show current rates by reading twice 1s apart
            # For now, just show 0 if we can't get a delta
            # Actually: read /proc/net/dev twice with 1s gap
            net_in_mbps = 0.0
            net_out_mbps = 0.0
            # First reading
            rx1: dict = {}
            tx1: dict = {}
            with open("/proc/net/dev") as f:
                for line in f:
                    if ":" not in line:
                        continue
                    iface, data = line.split(":", 1)
                    iface = iface.strip()
                    if iface == "lo":
                        continue
                    parts = data.split()
                    if len(parts) >= 9:
                        rx1[iface] = int(parts[0])
                        tx1[iface] = int(parts[8])
            # Wait 1 second
            await asyncio.sleep(1)
            # Second reading
            with open("/proc/net/dev") as f:
                for line in f:
                    if ":" not in line:
                        continue
                    iface, data = line.split(":", 1)
                    iface = iface.strip()
                    if iface == "lo":
                        continue
                    parts = data.split()
                    if len(parts) >= 9:
                        rx2 = int(parts[0])
                        tx2 = int(parts[8])
                        rx_diff = rx2 - rx1.get(iface, rx2)
                        tx_diff = tx2 - tx1.get(iface, tx2)
                        net_in_mbps += rx_diff / (1024 * 1024)
                        net_out_mbps += tx_diff / (1024 * 1024)
        except Exception:
            pass

        # Container counts
        containers_running = 0
        containers_total = 0
        try:
            proc = await asyncio.create_subprocess_shell(
                "docker ps -a --format '{{.State}}' 2>/dev/null",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0 and stdout:
                states = stdout.decode().strip().splitlines()
                containers_total = len(states)
                containers_running = sum(1 for s in states if s.strip() == "running")
        except Exception:
            pass

        # Tailscale status
        ts_connected = False
        ts_ip = ""
        try:
            proc = await asyncio.create_subprocess_shell(
                "tailscale ip -4 2>/dev/null",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0:
                ts_connected = True
                ts_ip = stdout.decode().strip()
        except Exception:
            pass

        return DashboardSummary(
            cpu_percent=round(cpu, 1),
            ram_used_gb=round(ram_used, 1),
            ram_total_gb=round(ram_total, 1),
            ram_percent=round((ram_used / ram_total * 100) if ram_total > 0 else 0, 1),
            disk_used_tb=round(disk_used, 2),
            disk_total_tb=round(disk_total, 2),
            disk_percent=round((disk_used / disk_total * 100) if disk_total > 0 else 0, 1),
            network_in_mbps=round(net_in_mbps, 1),
            network_out_mbps=round(net_out_mbps, 1),
            uptime_seconds=uptime,
            containers_running=containers_running,
            containers_total=containers_total,
            tailscale_connected=ts_connected,
            tailscale_ip=ts_ip,
        )

    @app.get("/api/v1/dashboard/alerts", dependencies=[Depends(require_auth)])
    async def dashboard_alerts():
        """Get active alerts."""
        if _mk_engine and hasattr(_mk_engine, "ops_manager") and _mk_engine.ops_manager:
            alerts = _mk_engine.ops_manager.alerts.active_alerts
            return [
                {
                    "id": a.id,
                    "severity": a.severity.value,
                    "message": a.message,
                    "check": a.check_name,
                    "fired_at": a.fired_at,
                }
                for a in alerts
            ]
        return []

    @app.get("/api/v1/dashboard/activity", dependencies=[Depends(require_auth)])
    async def dashboard_activity():
        """Get recent activity log."""
        # Return recent audit entries if available
        return {"events": []}


def _register_chat_routes(app: FastAPI) -> None:
    """Chat routes: send message (HTTP fallback)."""

    @app.post("/api/v1/chat/message", dependencies=[Depends(require_auth)])
    async def chat_message(msg: ChatMessage):
        """Send a chat message and get a response."""
        if _mk_engine:
            try:
                response = await _mk_engine.process(msg.content)
                return ChatResponse(
                    content=response.final_response,
                    actions=[],
                )
            except Exception as e:
                return ChatResponse(content=f"Error: {str(e)}")
        return ChatResponse(content="MK engine not initialized")

    @app.get("/api/v1/chat/history", dependencies=[Depends(require_auth)])
    async def chat_history():
        """Get chat history."""
        if _mk_engine and hasattr(_mk_engine, "conversation"):
            messages = []
            for msg in _mk_engine.conversation.messages[-50:]:
                messages.append({
                    "role": msg.role.value,
                    "content": msg.content,
                    "timestamp": msg.timestamp.isoformat(),
                })
            return {"messages": messages}
        return {"messages": []}


def _register_storage_routes(app: FastAPI) -> None:
    """Storage routes: pools, datasets, snapshots, disks."""

    @app.get("/api/v1/storage/pools", dependencies=[Depends(require_auth)])
    async def list_pools():
        return {"pools": []}

    @app.get("/api/v1/storage/datasets", dependencies=[Depends(require_auth)])
    async def list_datasets():
        return {"datasets": []}

    @app.get("/api/v1/storage/snapshots", dependencies=[Depends(require_auth)])
    async def list_snapshots():
        return {"snapshots": []}

    @app.get("/api/v1/storage/disks", dependencies=[Depends(require_auth)])
    async def list_disks():
        return {"disks": []}


def _register_apps_routes(app: FastAPI) -> None:
    """Apps routes: containers, stacks, VMs."""

    @app.get("/api/v1/apps/containers", dependencies=[Depends(require_auth)])
    async def list_containers():
        """List Docker containers."""
        try:
            proc = await asyncio.create_subprocess_shell(
                'docker ps -a --format \'{"name":"{{.Names}}","image":"{{.Image}}","status":"{{.Status}}","state":"{{.State}}","ports":"{{.Ports}}"}\'',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0:
                containers = []
                for line in stdout.decode().strip().splitlines():
                    if line:
                        try:
                            containers.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
                return {"containers": containers}
        except Exception:
            pass
        return {"containers": []}

    @app.post("/api/v1/apps/containers/{name}/restart", dependencies=[Depends(require_auth)])
    async def restart_container(name: str):
        name = _validate_shell_identifier(name, "container name")
        proc = await asyncio.create_subprocess_exec(
            "docker", "restart", name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise HTTPException(500, f"Failed: {stderr.decode()}")
        return {"status": "restarted", "container": name}

    @app.post("/api/v1/apps/containers/{name}/stop", dependencies=[Depends(require_auth)])
    async def stop_container(name: str):
        name = _validate_shell_identifier(name, "container name")
        proc = await asyncio.create_subprocess_exec(
            "docker", "stop", name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        return {"status": "stopped", "container": name}

    @app.post("/api/v1/apps/containers/{name}/start", dependencies=[Depends(require_auth)])
    async def start_container(name: str):
        name = _validate_shell_identifier(name, "container name")
        proc = await asyncio.create_subprocess_exec(
            "docker", "start", name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        return {"status": "started", "container": name}


def _register_network_routes(app: FastAPI) -> None:
    """Network routes: interfaces, tailscale, firewall, wireguard, dns, proxy."""

    # In-memory stores for network config (production would use persistent storage)
    _firewall_rules: List[Dict[str, Any]] = []
    _wireguard_interfaces: List[Dict[str, Any]] = []
    _dns_config: Dict[str, Any] = {
        "primary": "1.1.1.1",
        "secondary": "8.8.8.8",
        "search_domain": "home.lab",
        "overrides": [],
    }
    _proxy_sites: List[Dict[str, Any]] = []
    _fw_counter = {"id": 0}
    _proxy_counter = {"id": 0}
    # Lock to protect concurrent mutations of in-memory stores
    _network_lock = asyncio.Lock()

    @app.get("/api/v1/network/interfaces", dependencies=[Depends(require_auth)])
    async def list_interfaces():
        try:
            proc = await asyncio.create_subprocess_shell(
                "ip -j addr show",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0:
                return {"interfaces": json.loads(stdout.decode())}
        except Exception:
            pass
        return {"interfaces": []}

    @app.put("/api/v1/network/interfaces/{name}", dependencies=[Depends(require_auth)])
    async def update_interface(name: str, request: Request):
        name = _validate_shell_identifier(name, "interface name")
        body = await request.json()
        return {"status": "updated", "interface": name, "config": body}

    @app.get("/api/v1/network/tailscale", dependencies=[Depends(require_auth)])
    async def tailscale_status():
        try:
            proc = await asyncio.create_subprocess_shell(
                "tailscale status --json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0:
                return json.loads(stdout.decode())
        except Exception:
            pass
        return {"BackendState": "Unknown", "Peer": {}}

    # Firewall CRUD
    @app.get("/api/v1/network/firewall", dependencies=[Depends(require_auth)])
    async def list_firewall_rules():
        return {"rules": _firewall_rules}

    @app.post("/api/v1/network/firewall", dependencies=[Depends(require_auth)])
    async def add_firewall_rule(request: Request):
        body = await request.json()
        async with _network_lock:
            _fw_counter["id"] += 1
            rule = {
                "id": _fw_counter["id"],
                "chain": body.get("chain", "input"),
                "action": body.get("action", "accept"),
                "protocol": body.get("protocol"),
                "source": body.get("source"),
                "destination": body.get("destination"),
                "port": body.get("port"),
                "comment": body.get("comment", ""),
                "enabled": body.get("enabled", True),
            }
            _firewall_rules.append(rule)
        return {"status": "created", "rule": rule}

    @app.put("/api/v1/network/firewall/{rule_id}", dependencies=[Depends(require_auth)])
    async def update_firewall_rule(rule_id: int, request: Request):
        body = await request.json()
        async with _network_lock:
            for rule in _firewall_rules:
                if rule["id"] == rule_id:
                    rule.update({k: v for k, v in body.items() if k != "id"})
                    return {"status": "updated", "rule": rule}
        raise HTTPException(404, f"Rule {rule_id} not found")

    @app.delete("/api/v1/network/firewall/{rule_id}", dependencies=[Depends(require_auth)])
    async def delete_firewall_rule(rule_id: int):
        async with _network_lock:
            for i, rule in enumerate(_firewall_rules):
                if rule["id"] == rule_id:
                    _firewall_rules.pop(i)
                    return {"status": "deleted", "id": rule_id}
        raise HTTPException(404, f"Rule {rule_id} not found")

    @app.post("/api/v1/network/firewall/reorder", dependencies=[Depends(require_auth)])
    async def reorder_firewall_rules(request: Request):
        body = await request.json()
        order = body.get("order", [])
        if not order:
            raise HTTPException(400, "order list required")
        async with _network_lock:
            reordered = []
            for rid in order:
                for rule in _firewall_rules:
                    if rule["id"] == rid:
                        reordered.append(rule)
                        break
            _firewall_rules.clear()
            _firewall_rules.extend(reordered)
        return {"status": "reordered", "rules": _firewall_rules}

    # WireGuard
    @app.get("/api/v1/network/wireguard", dependencies=[Depends(require_auth)])
    async def list_wireguard_interfaces():
        return {"interfaces": _wireguard_interfaces}

    @app.post("/api/v1/network/wireguard", dependencies=[Depends(require_auth)])
    async def create_wireguard_interface(request: Request):
        body = await request.json()
        async with _network_lock:
            wg_iface = {
                "name": body.get("name", "wg0"),
                "private_key_set": True,
                "listen_port": body.get("listen_port", 51820),
                "address": body.get("address", "10.8.0.1/24"),
                "peers": [],
            }
            _wireguard_interfaces.append(wg_iface)
        return {"status": "created", "interface": wg_iface}

    @app.get("/api/v1/network/wireguard/{name}/peers", dependencies=[Depends(require_auth)])
    async def list_wireguard_peers(name: str):
        for iface in _wireguard_interfaces:
            if iface["name"] == name:
                return {"peers": iface["peers"]}
        raise HTTPException(404, f"WireGuard interface '{name}' not found")

    @app.post("/api/v1/network/wireguard/{name}/peers", dependencies=[Depends(require_auth)])
    async def add_wireguard_peer(name: str, request: Request):
        body = await request.json()
        async with _network_lock:
            for iface in _wireguard_interfaces:
                if iface["name"] == name:
                    peer = {
                        "id": len(iface["peers"]) + 1,
                        "name": body.get("name", "peer"),
                        "public_key": body.get("public_key", ""),
                        "allowed_ips": body.get("allowed_ips", []),
                        "endpoint": body.get("endpoint"),
                    }
                    iface["peers"].append(peer)
                    return {"status": "created", "peer": peer}
        raise HTTPException(404, f"WireGuard interface '{name}' not found")

    @app.delete(
        "/api/v1/network/wireguard/{name}/peers/{peer_id}",
        dependencies=[Depends(require_auth)],
    )
    async def delete_wireguard_peer(name: str, peer_id: int):
        async with _network_lock:
            for iface in _wireguard_interfaces:
                if iface["name"] == name:
                    for i, peer in enumerate(iface["peers"]):
                        if peer["id"] == peer_id:
                            iface["peers"].pop(i)
                            return {"status": "deleted", "peer_id": peer_id}
                    raise HTTPException(404, f"Peer {peer_id} not found")
        raise HTTPException(404, f"WireGuard interface '{name}' not found")

    # DNS
    @app.get("/api/v1/network/dns", dependencies=[Depends(require_auth)])
    async def get_dns_config():
        return _dns_config

    @app.put("/api/v1/network/dns", dependencies=[Depends(require_auth)])
    async def update_dns_config(request: Request):
        _allowed_dns_keys = {"primary", "secondary", "search_domain", "overrides"}
        body = await request.json()
        filtered = {k: v for k, v in body.items() if k in _allowed_dns_keys}
        _dns_config.update(filtered)
        return {"status": "updated", "config": _dns_config}

    # Reverse Proxy
    @app.get("/api/v1/network/proxy", dependencies=[Depends(require_auth)])
    async def list_proxy_sites():
        return {"sites": _proxy_sites}

    @app.post("/api/v1/network/proxy", dependencies=[Depends(require_auth)])
    async def add_proxy_site(request: Request):
        body = await request.json()
        async with _network_lock:
            _proxy_counter["id"] += 1
            site = {
                "id": _proxy_counter["id"],
                "domain": body.get("domain", ""),
                "backend": body.get("backend", ""),
                "ssl": body.get("ssl", "auto"),
                "enabled": body.get("enabled", True),
            }
            _proxy_sites.append(site)
        return {"status": "created", "site": site}

    @app.put("/api/v1/network/proxy/{site_id}", dependencies=[Depends(require_auth)])
    async def update_proxy_site(site_id: int, request: Request):
        body = await request.json()
        async with _network_lock:
            for site in _proxy_sites:
                if site["id"] == site_id:
                    site.update({k: v for k, v in body.items() if k != "id"})
                    return {"status": "updated", "site": site}
        raise HTTPException(404, f"Proxy site {site_id} not found")

    @app.delete("/api/v1/network/proxy/{site_id}", dependencies=[Depends(require_auth)])
    async def delete_proxy_site(site_id: int):
        async with _network_lock:
            for i, site in enumerate(_proxy_sites):
                if site["id"] == site_id:
                    _proxy_sites.pop(i)
                    return {"status": "deleted", "id": site_id}
        raise HTTPException(404, f"Proxy site {site_id} not found")


def _register_system_routes(app: FastAPI) -> None:
    """System routes: info, services, health, power, updates, AI settings."""

    # In-memory AI settings store
    _ai_settings: Dict[str, Any] = {
        "provider": "openai",
        "model": "gpt-4o",
        "temperature": 0.7,
        "max_tokens": 4096,
        "system_prompt": "",
        "context_options": {
            "include_system_metrics": True,
            "include_recent_alerts": True,
            "include_page_context": True,
            "include_command_history": False,
        },
    }

    @app.get("/api/v1/system/info", dependencies=[Depends(require_auth)])
    async def system_info():
        import platform

        # Real system uptime from /proc/uptime
        uptime = 0.0
        try:
            with open("/proc/uptime") as f:
                uptime = float(f.read().split()[0])
        except Exception:
            uptime = time.time() - _start_time

        # CPU model
        cpu_model = ""
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if line.startswith("model name"):
                        cpu_model = line.split(":", 1)[1].strip()
                        break
        except Exception:
            pass

        # RAM info
        ram_total_gb = 0.0
        ram_used_gb = 0.0
        try:
            with open("/proc/meminfo") as f:
                info = {}
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        info[parts[0].rstrip(":")] = int(parts[1])
                ram_total_gb = info.get("MemTotal", 0) / (1024 * 1024)
                available = info.get("MemAvailable", info.get("MemFree", 0))
                ram_used_gb = (info.get("MemTotal", 0) - available) / (1024 * 1024)
        except Exception:
            pass

        return {
            "hostname": platform.node(),
            "os": f"MK OS 2.0 ({platform.system()} {platform.release()})",
            "kernel": platform.release(),
            "arch": platform.machine(),
            "python": platform.python_version(),
            "cpu_count": os.cpu_count(),
            "cpu_model": cpu_model,
            "ram_total_gb": round(ram_total_gb, 1),
            "ram_used_gb": round(ram_used_gb, 1),
            "uptime_seconds": uptime,
        }

    @app.get("/api/v1/system/health", dependencies=[Depends(require_auth)])
    async def system_health():
        """Run all health checks and return results."""
        if _mk_engine and hasattr(_mk_engine, "ops_manager") and _mk_engine.ops_manager:
            results = await _mk_engine.ops_manager.run_all_checks_now()
            return {
                "checks": [
                    {
                        "name": r.name,
                        "severity": r.severity.value,
                        "message": r.message,
                        "recommendations": r.recommendations,
                    }
                    for r in results
                ]
            }
        return {"checks": []}

    @app.get("/api/v1/system/services", dependencies=[Depends(require_auth)])
    async def list_services():
        try:
            proc = await asyncio.create_subprocess_shell(
                "systemctl list-units --type=service --state=running --no-pager --plain -o json 2>/dev/null || systemctl list-units --type=service --state=running --no-pager --plain",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            return {"services": stdout.decode()[:5000]}
        except Exception:
            return {"services": ""}

    @app.post("/api/v1/system/services/{name}/start", dependencies=[Depends(require_auth)])
    async def start_service(name: str):
        name = _validate_shell_identifier(name, "service name")
        try:
            proc = await asyncio.create_subprocess_exec(
                "systemctl", "start", name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise HTTPException(500, f"Failed to start {name}: {stderr.decode()}")
            return {"status": "started", "service": name}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"Failed to start service: {str(e)}")

    @app.post("/api/v1/system/services/{name}/stop", dependencies=[Depends(require_auth)])
    async def stop_service(name: str):
        name = _validate_shell_identifier(name, "service name")
        try:
            proc = await asyncio.create_subprocess_exec(
                "systemctl", "stop", name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise HTTPException(500, f"Failed to stop {name}: {stderr.decode()}")
            return {"status": "stopped", "service": name}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"Failed to stop service: {str(e)}")

    @app.post("/api/v1/system/services/{name}/restart", dependencies=[Depends(require_auth)])
    async def restart_service(name: str):
        name = _validate_shell_identifier(name, "service name")
        try:
            proc = await asyncio.create_subprocess_exec(
                "systemctl", "restart", name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise HTTPException(500, f"Failed to restart {name}: {stderr.decode()}")
            return {"status": "restarted", "service": name}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"Failed to restart service: {str(e)}")

    @app.get("/api/v1/system/updates", dependencies=[Depends(require_auth)])
    async def list_updates():
        """List available system updates."""
        try:
            proc = await asyncio.create_subprocess_shell(
                "apt list --upgradable 2>/dev/null | tail -n +2",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0:
                packages = []
                for line in stdout.decode().strip().splitlines():
                    if line.strip():
                        packages.append(line.strip())
                return {"updates": packages, "count": len(packages)}
        except Exception:
            pass
        return {"updates": [], "count": 0}

    @app.post("/api/v1/system/updates/apply", dependencies=[Depends(require_auth)])
    async def apply_updates(request: Request):
        """Apply system updates."""
        body = await request.json() if request.headers.get("content-type") else {}
        packages = body.get("packages", [])
        if packages:
            # Validate each package name to prevent shell injection
            validated_packages = []
            for pkg in packages:
                validated_packages.append(_validate_shell_identifier(pkg, "package name"))
            cmd_args = ["apt-get", "install", "-y", *validated_packages]
        else:
            cmd_args = ["apt-get", "upgrade", "-y"]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                return {"status": "failed", "error": stderr.decode()[:500]}
            return {"status": "applied", "output": stdout.decode()[:1000]}
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    @app.post("/api/v1/system/power/reboot", dependencies=[Depends(require_auth)])
    async def power_reboot():
        """Reboot the system."""
        try:
            proc = await asyncio.create_subprocess_shell(
                "shutdown -r +1 'MK OS reboot requested'",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            return {"status": "rebooting", "message": "System will reboot in 1 minute"}
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    @app.post("/api/v1/system/power/shutdown", dependencies=[Depends(require_auth)])
    async def power_shutdown():
        """Shutdown the system."""
        try:
            proc = await asyncio.create_subprocess_shell(
                "shutdown -h +1 'MK OS shutdown requested'",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            return {"status": "shutting_down", "message": "System will shutdown in 1 minute"}
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    @app.get("/api/v1/system/ai/settings", dependencies=[Depends(require_auth)])
    async def get_ai_settings():
        """Get AI configuration."""
        return _ai_settings

    @app.put("/api/v1/system/ai/settings", dependencies=[Depends(require_auth)])
    async def update_ai_settings(request: Request):
        """Update AI configuration."""
        _allowed_ai_keys = {
            "provider", "model", "temperature", "max_tokens",
            "system_prompt", "context_options",
        }
        body = await request.json()
        filtered = {k: v for k, v in body.items() if k in _allowed_ai_keys}
        _ai_settings.update(filtered)
        return {"status": "updated", "settings": _ai_settings}


def _register_media_routes(app: FastAPI) -> None:
    """Media routes: organizer, library, disc ripper, drives."""

    # In-memory stores for media state
    _rip_status: Dict[str, Any] = {
        "active": False,
        "progress": 0,
        "title": "",
        "eta_seconds": 0,
        "speed_mbps": 0,
        "current_task": "",
    }
    _recent_rips: List[Dict[str, Any]] = []
    _media_settings: Dict[str, Any] = {
        "auto_rip": False,
        "output_path": "/mnt/media/rips/",
        "default_format": "mkv",
        "min_length_minutes": 30,
        "notifications": True,
    }

    @app.post("/api/v1/media/organize", dependencies=[Depends(require_auth)])
    async def organize_media(request: Request):
        """Organize a folder of media files."""
        body = await request.json()
        source = body.get("source", "")
        dest = body.get("destination", "/data/media")
        dry_run = body.get("dry_run", True)

        if not source:
            raise HTTPException(400, "source path required")

        try:
            from mk.plugins.media_organizer import MediaOrganizer
            organizer = MediaOrganizer(dest_root=dest)
            result = organizer.quick_organize(source, dry_run=dry_run)
            return {"result": result, "dry_run": dry_run}
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/v1/media/drives", dependencies=[Depends(require_auth)])
    async def list_drives():
        """List optical drives."""
        try:
            proc = await asyncio.create_subprocess_shell(
                "lsblk -Jno NAME,TYPE,SIZE,MODEL,TRAN 2>/dev/null",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0:
                data = json.loads(stdout.decode())
                drives = [
                    d for d in data.get("blockdevices", [])
                    if d.get("type") == "rom"
                ]
                return {"drives": drives}
        except Exception:
            pass
        return {"drives": []}

    @app.get("/api/v1/media/drives/{dev}/disc", dependencies=[Depends(require_auth)])
    async def get_disc_info(dev: str):
        """Get disc info for a specific drive."""
        dev = _validate_shell_identifier(dev, "device name")
        try:
            from mk.server.ripper import DiscRipper
            ripper = DiscRipper(drive_device=f"/dev/{dev}")
            result = await ripper.disc_status()
            return result.metadata if result.success else {"disc_present": False}
        except Exception:
            return {"disc_present": False, "error": "Ripper not available"}

    @app.post("/api/v1/media/rip", dependencies=[Depends(require_auth)])
    async def start_rip(request: Request):
        """Start a disc rip job."""
        body = await request.json()
        if _rip_status["active"]:
            raise HTTPException(409, "A rip is already in progress")

        _rip_status.update({
            "active": True,
            "progress": 0,
            "title": body.get("title", "Unknown"),
            "eta_seconds": 0,
            "speed_mbps": 0,
            "current_task": "Starting rip...",
        })

        # In production, this would spawn a background task using the DiscRipper
        return {
            "status": "started",
            "title": body.get("title", "Unknown"),
            "device": body.get("device", "/dev/sr0"),
        }

    @app.get("/api/v1/media/rip/status", dependencies=[Depends(require_auth)])
    async def get_rip_status():
        """Get current rip progress."""
        return _rip_status

    @app.post("/api/v1/media/rip/cancel", dependencies=[Depends(require_auth)])
    async def cancel_rip():
        """Cancel the current rip."""
        if not _rip_status["active"]:
            raise HTTPException(409, "No rip in progress")
        _rip_status.update({
            "active": False,
            "progress": 0,
            "title": "",
            "eta_seconds": 0,
            "speed_mbps": 0,
            "current_task": "Cancelled",
        })
        return {"status": "cancelled"}

    @app.post("/api/v1/media/eject/{dev}", dependencies=[Depends(require_auth)])
    async def eject_disc(dev: str):
        """Eject a disc from the specified drive."""
        dev = _validate_shell_identifier(dev, "device name")
        try:
            proc = await asyncio.create_subprocess_exec(
                "eject", f"/dev/{dev}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise HTTPException(500, f"Eject failed: {stderr.decode()}")
            return {"status": "ejected", "device": dev}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"Eject failed: {str(e)}")

    @app.get("/api/v1/media/library/stats", dependencies=[Depends(require_auth)])
    async def library_stats():
        """Get media library statistics."""
        # In production, scan the media directories
        return {
            "movies": 0,
            "tv_shows": 0,
            "total_size_bytes": 0,
            "bluray_count": 0,
            "dvd_count": 0,
            "uhd_count": 0,
        }

    @app.get("/api/v1/media/rips/recent", dependencies=[Depends(require_auth)])
    async def get_recent_rips():
        """Get recent rip history."""
        return {"rips": _recent_rips}

    @app.get("/api/v1/media/settings", dependencies=[Depends(require_auth)])
    async def get_media_settings():
        """Get media settings."""
        return _media_settings

    @app.put("/api/v1/media/settings", dependencies=[Depends(require_auth)])
    async def update_media_settings(request: Request):
        """Update media settings."""
        _allowed_media_keys = {
            "auto_rip", "output_path", "default_format",
            "min_length_minutes", "notifications",
        }
        body = await request.json()
        filtered = {k: v for k, v in body.items() if k in _allowed_media_keys}
        _media_settings.update(filtered)
        return {"status": "updated", "settings": _media_settings}


def _register_protection_routes(app: FastAPI) -> None:
    """Protection routes: backup jobs, scrubs, replication, retention."""

    # In-memory stores for protection config
    _backup_jobs: List[Dict[str, Any]] = []
    _job_history: Dict[str, List[Dict[str, Any]]] = {}
    _scrub_schedules: Dict[str, Dict[str, Any]] = {}
    _replication_tasks: List[Dict[str, Any]] = []
    _retention_policies: List[Dict[str, Any]] = []
    _job_counter = {"id": 0}
    _replication_counter = {"id": 0}
    _retention_counter = {"id": 0}
    # Lock to protect concurrent mutations of in-memory stores
    _protection_lock = asyncio.Lock()

    # Backup Jobs CRUD
    @app.get("/api/v1/protection/jobs", dependencies=[Depends(require_auth)])
    async def list_backup_jobs():
        return {"jobs": _backup_jobs}

    @app.post("/api/v1/protection/jobs", dependencies=[Depends(require_auth)])
    async def create_backup_job(request: Request):
        body = await request.json()
        async with _protection_lock:
            _job_counter["id"] += 1
            job = {
                "id": _job_counter["id"],
                "name": body.get("name", ""),
                "backup_type": body.get("backup_type", "zfs_snapshot"),
                "source": body.get("source", ""),
                "destination": body.get("destination", ""),
                "schedule": body.get("schedule", "daily"),
                "cron_expression": body.get("cron_expression"),
                "retention_count": body.get("retention_count", 7),
                "enabled": body.get("enabled", True),
                "last_run": None,
                "last_status": None,
                "last_duration_seconds": None,
            }
            _backup_jobs.append(job)
            _job_history[str(job["id"])] = []
        return {"status": "created", "job": job}

    @app.put("/api/v1/protection/jobs/{job_id}", dependencies=[Depends(require_auth)])
    async def update_backup_job(job_id: int, request: Request):
        body = await request.json()
        async with _protection_lock:
            for job in _backup_jobs:
                if job["id"] == job_id:
                    job.update({k: v for k, v in body.items() if k != "id"})
                    return {"status": "updated", "job": job}
        raise HTTPException(404, f"Job {job_id} not found")

    @app.delete("/api/v1/protection/jobs/{job_id}", dependencies=[Depends(require_auth)])
    async def delete_backup_job(job_id: int):
        async with _protection_lock:
            for i, job in enumerate(_backup_jobs):
                if job["id"] == job_id:
                    _backup_jobs.pop(i)
                    _job_history.pop(str(job_id), None)
                    return {"status": "deleted", "id": job_id}
        raise HTTPException(404, f"Job {job_id} not found")

    @app.post("/api/v1/protection/jobs/{job_id}/run", dependencies=[Depends(require_auth)])
    async def run_backup_job(job_id: int):
        async with _protection_lock:
            for job in _backup_jobs:
                if job["id"] == job_id:
                    # Record run in history
                    run_record = {
                        "started_at": time.time(),
                        "status": "running",
                        "duration_seconds": None,
                    }
                    history = _job_history.setdefault(str(job_id), [])
                    history.append(run_record)
                    # Simulate immediate completion for stub
                    run_record["status"] = "success"
                    run_record["duration_seconds"] = 0.1
                    job["last_run"] = time.time()
                    job["last_status"] = "success"
                    return {"status": "triggered", "job_id": job_id}
        raise HTTPException(404, f"Job {job_id} not found")

    @app.get("/api/v1/protection/jobs/{job_id}/history", dependencies=[Depends(require_auth)])
    async def get_job_history(job_id: int):
        # Check job exists
        found = any(j["id"] == job_id for j in _backup_jobs)
        if not found:
            raise HTTPException(404, f"Job {job_id} not found")
        history = _job_history.get(str(job_id), [])
        return {"job_id": job_id, "history": history}

    # Scrub Schedules
    @app.get("/api/v1/protection/scrubs", dependencies=[Depends(require_auth)])
    async def list_scrub_schedules():
        return {"scrubs": list(_scrub_schedules.values())}

    @app.get("/api/v1/protection/scrubs/{pool}", dependencies=[Depends(require_auth)])
    async def get_scrub_schedule(pool: str):
        pool = _validate_shell_identifier(pool, "pool name")
        if pool in _scrub_schedules:
            return _scrub_schedules[pool]
        return {
            "pool": pool,
            "schedule": "weekly",
            "last_run": None,
            "duration_seconds": None,
            "errors": 0,
        }

    @app.put("/api/v1/protection/scrubs/{pool}", dependencies=[Depends(require_auth)])
    async def update_scrub_schedule(pool: str, request: Request):
        pool = _validate_shell_identifier(pool, "pool name")
        _allowed_scrub_keys = {"schedule", "last_run", "duration_seconds", "errors"}
        body = await request.json()
        filtered = {k: v for k, v in body.items() if k in _allowed_scrub_keys}
        schedule = _scrub_schedules.get(pool, {"pool": pool})
        schedule.update(filtered)
        schedule["pool"] = pool
        _scrub_schedules[pool] = schedule
        return {"status": "updated", "scrub": schedule}

    @app.post("/api/v1/protection/scrubs/{pool}/run", dependencies=[Depends(require_auth)])
    async def run_scrub(pool: str):
        """Trigger a scrub on the specified pool."""
        pool = _validate_shell_identifier(pool, "pool name")
        try:
            proc = await asyncio.create_subprocess_exec(
                "zpool", "scrub", pool,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                return {"status": "failed", "pool": pool, "error": stderr.decode()}
        except Exception:
            pass
        return {"status": "started", "pool": pool}

    # Replication
    @app.get("/api/v1/protection/replication", dependencies=[Depends(require_auth)])
    async def list_replication_tasks():
        return {"tasks": _replication_tasks}

    @app.post("/api/v1/protection/replication", dependencies=[Depends(require_auth)])
    async def create_replication_task(request: Request):
        body = await request.json()
        async with _protection_lock:
            _replication_counter["id"] += 1
            task = {
                "id": _replication_counter["id"],
                "name": body.get("name", ""),
                "source": body.get("source", ""),
                "target": body.get("target", ""),
                "schedule": body.get("schedule", "hourly"),
                "enabled": body.get("enabled", True),
                "last_sync": None,
                "lag_seconds": None,
            }
            _replication_tasks.append(task)
        return {"status": "created", "task": task}

    @app.delete(
        "/api/v1/protection/replication/{task_id}",
        dependencies=[Depends(require_auth)],
    )
    async def delete_replication_task(task_id: int):
        async with _protection_lock:
            for i, task in enumerate(_replication_tasks):
                if task["id"] == task_id:
                    _replication_tasks.pop(i)
                    return {"status": "deleted", "id": task_id}
        raise HTTPException(404, f"Replication task {task_id} not found")

    # Retention
    @app.get("/api/v1/protection/retention", dependencies=[Depends(require_auth)])
    async def list_retention_policies():
        return {"policies": _retention_policies}

    @app.post("/api/v1/protection/retention", dependencies=[Depends(require_auth)])
    async def create_retention_policy(request: Request):
        body = await request.json()
        async with _protection_lock:
            _retention_counter["id"] += 1
            policy = {
                "id": _retention_counter["id"],
                "name": body.get("name", ""),
                "keep_daily": body.get("keep_daily", 7),
                "keep_weekly": body.get("keep_weekly", 4),
                "keep_monthly": body.get("keep_monthly", 12),
            }
            _retention_policies.append(policy)
        return {"status": "created", "policy": policy}

    @app.put("/api/v1/protection/retention/{policy_id}", dependencies=[Depends(require_auth)])
    async def update_retention_policy(policy_id: int, request: Request):
        body = await request.json()
        async with _protection_lock:
            for policy in _retention_policies:
                if policy["id"] == policy_id:
                    policy.update({k: v for k, v in body.items() if k != "id"})
                    return {"status": "updated", "policy": policy}
        raise HTTPException(404, f"Retention policy {policy_id} not found")


def _register_keys_routes(app: FastAPI) -> None:
    """Keys & Auth management routes."""

    @app.get("/api/v1/keys/llm", dependencies=[Depends(require_auth)])
    async def list_llm_keys():
        """List stored LLM API keys (masked)."""
        # In production, reads from SecretsManager
        return {"keys": []}

    @app.post("/api/v1/keys/llm", dependencies=[Depends(require_auth)])
    async def add_llm_key(request: Request):
        """Add an LLM API key."""
        body = await request.json()
        provider = body.get("provider", "")
        key = body.get("key", "")
        if not key:
            raise HTTPException(400, "key is required")

        # Store in secrets + configure provider
        if _mk_engine:
            try:
                # Try to store via the engine's tailscale key path
                from mk.safety.secrets import SecretsManager
                secrets = SecretsManager()
                secrets.store_secret(f"llm_{provider}", key)
            except Exception:
                pass

        masked = key[:6] + "...****" + key[-4:] if len(key) > 10 else "****"
        return {"status": "stored", "provider": provider, "masked": masked}

    @app.delete("/api/v1/keys/llm/{provider}", dependencies=[Depends(require_auth)])
    async def delete_llm_key(provider: str):
        """Remove an LLM API key."""
        try:
            from mk.safety.secrets import SecretsManager
            secrets = SecretsManager()
            secrets.delete_secret(f"llm_{provider}")
        except Exception:
            pass
        return {"status": "deleted", "provider": provider}

    @app.post("/api/v1/keys/telegram", dependencies=[Depends(require_auth)])
    async def save_telegram_config(request: Request):
        """Save Telegram bot token and chat IDs."""
        body = await request.json()
        token = body.get("token", "")
        chat_ids = body.get("chat_ids", [])

        if token:
            try:
                from mk.safety.secrets import SecretsManager
                secrets = SecretsManager()
                secrets.store_secret("telegram_bot_token", token)
            except Exception:
                pass

        return {"status": "saved", "chat_ids_count": len(chat_ids)}

    @app.post("/api/v1/keys/tailscale", dependencies=[Depends(require_auth)])
    async def save_tailscale_key(request: Request):
        """Save Tailscale auth key and connect."""
        body = await request.json()
        auth_key = body.get("key", "")

        if not auth_key:
            raise HTTPException(400, "key is required")

        # Store and connect
        try:
            from mk.safety.secrets import SecretsManager
            secrets = SecretsManager()
            secrets.store_secret("tailscale_auth_key", auth_key)
        except Exception:
            pass

        # Try to connect
        try:
            from mk.server.network import NetworkManager
            nm = NetworkManager(sudo=True)
            result = await nm.tailscale_up(auth_key=auth_key, ssh=True, accept_routes=True)
            if result.success:
                ip_result = await nm.tailscale_ip()
                return {
                    "status": "connected",
                    "ip": ip_result.metadata.get("ipv4", "") if ip_result.success else "",
                }
            return {"status": "failed", "error": result.error}
        except Exception as e:
            return {"status": "stored", "note": f"Key saved, connection pending: {e}"}

    @app.post("/api/v1/keys/service", dependencies=[Depends(require_auth)])
    async def save_service_key(request: Request):
        """Save a service API key (Sonarr, Radarr, Plex, etc.)."""
        body = await request.json()
        service = body.get("service", "")
        key = body.get("key", "")

        if not service or not key:
            raise HTTPException(400, "service and key are required")

        try:
            from mk.safety.secrets import SecretsManager
            secrets = SecretsManager()
            secrets.store_secret(f"service_{service}", key)
        except Exception:
            pass

        masked = key[:4] + "...****" + key[-4:] if len(key) > 8 else "****"
        return {"status": "stored", "service": service, "masked": masked}

    @app.post("/api/v1/keys/pin", dependencies=[Depends(require_auth)])
    async def change_pin(request: Request):
        """Change the dashboard login PIN."""
        global _pin_hash
        body = await request.json()
        current = body.get("current_pin", "")
        new_pin = body.get("new_pin", "")

        if not _verify_pin(current):
            raise HTTPException(401, "Current PIN is incorrect")

        if len(new_pin) < 4 or len(new_pin) > 8:
            raise HTTPException(400, "PIN must be 4-8 digits")

        if not new_pin.isdigit():
            raise HTTPException(400, "PIN must contain only digits")

        _pin_hash = _hash_pin(new_pin)
        os.environ["MK_PIN"] = new_pin

        return {"status": "changed"}


def _register_metrics_routes(app: FastAPI) -> None:
    """Prometheus-compatible metrics endpoint."""

    @app.get("/metrics", dependencies=[Depends(require_auth)])
    async def get_metrics():
        """Expose metrics in Prometheus text exposition format.

        Requires authentication to prevent leaking API surface and usage
        patterns to unauthenticated observers.
        """
        content = metrics.render_prometheus()
        return Response(
            content=content,
            media_type="text/plain; charset=utf-8",
        )


def _register_websocket(app: FastAPI) -> None:
    """WebSocket endpoint for real-time chat."""

    @app.websocket("/ws/chat")
    async def websocket_chat(ws: WebSocket, token: str = Query("")):
        # Validate token
        if not _validate_session(token):
            await ws.close(code=4001, reason="Invalid session")
            return

        await ws.accept()
        logger.info("WebSocket chat connected")

        try:
            while True:
                data = await ws.receive_text()
                msg = json.loads(data)

                if msg.get("type") == "ping":
                    await ws.send_json({"type": "pong", "server_time": time.time()})
                    continue

                if msg.get("type") == "chat_message":
                    content = msg.get("content", "")

                    # Send typing indicator
                    await ws.send_json({"type": "typing_indicator", "active": True})

                    # Process through MK engine
                    response_text = "MK engine not available"
                    if _mk_engine:
                        try:
                            result = await _mk_engine.process(content)
                            response_text = result.final_response
                        except Exception as e:
                            response_text = f"Error: {str(e)}"

                    # Send response
                    await ws.send_json({
                        "type": "chat_response",
                        "id": secrets.token_hex(8),
                        "reply_to": msg.get("id", ""),
                        "content": response_text,
                        "actions": [],
                        "done": True,
                    })

        except WebSocketDisconnect:
            logger.info("WebSocket chat disconnected")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
