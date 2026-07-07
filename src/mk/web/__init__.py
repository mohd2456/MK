"""MK Web API — FastAPI backend for the Web UI.

Serves the complete Web UI dashboard and provides:
- REST API at /api/v1/* for all MK operations
- WebSocket at /ws/chat for real-time AI chat
- Static file serving for the React frontend build
- PIN-based authentication with session tokens

Binds to Tailscale interface only (100.x.x.x) — not accessible
from the public internet. Access via:
  http://mk-brain:8080 (on your tailnet)
  or https://mk-brain.tail12345.ts.net (with Tailscale HTTPS)

Auto-starts with MK OS via systemd.
"""
