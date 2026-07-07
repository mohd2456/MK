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
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

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

    # Register routes
    _register_auth_routes(app)
    _register_dashboard_routes(app)
    _register_chat_routes(app)
    _register_storage_routes(app)
    _register_apps_routes(app)
    _register_network_routes(app)
    _register_system_routes(app)
    _register_media_routes(app)
    _register_keys_routes(app)
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
        proc = await asyncio.create_subprocess_shell(
            f"docker restart {name}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise HTTPException(500, f"Failed: {stderr.decode()}")
        return {"status": "restarted", "container": name}

    @app.post("/api/v1/apps/containers/{name}/stop", dependencies=[Depends(require_auth)])
    async def stop_container(name: str):
        proc = await asyncio.create_subprocess_shell(
            f"docker stop {name}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        return {"status": "stopped", "container": name}

    @app.post("/api/v1/apps/containers/{name}/start", dependencies=[Depends(require_auth)])
    async def start_container(name: str):
        proc = await asyncio.create_subprocess_shell(
            f"docker start {name}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        return {"status": "started", "container": name}


def _register_network_routes(app: FastAPI) -> None:
    """Network routes: interfaces, tailscale, firewall."""

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


def _register_system_routes(app: FastAPI) -> None:
    """System routes: info, services, health."""

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


def _register_media_routes(app: FastAPI) -> None:
    """Media routes: organizer, library."""

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
