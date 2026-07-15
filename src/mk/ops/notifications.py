"""Notification broadcaster — delivers alerts to all active channels.

Routes alert messages from the :class:`~mk.ops.alerts.AlertManager` to:
- All connected WebSocket clients (real-time in-browser notifications)
- Telegram (via the MK gateway bridge, if configured)
- The metrics counter (for observability)

This module provides the ``notify_callback`` that the OpsManager passes to
the AlertManager. It's intentionally decoupled from transport specifics so
new channels (email, Slack, etc.) can be added without touching the ops layer.
"""

from __future__ import annotations

import logging
from typing import Callable, Coroutine, List, Optional, Set

from starlette.websockets import WebSocket

logger = logging.getLogger(__name__)


class NotificationBroadcaster:
    """Broadcasts alert notifications to all active channels.

    Maintains a set of connected WebSocket clients and an optional
    Telegram send callback. The :meth:`notify` method is the single
    async callable passed to OpsManager as ``notify_callback``.

    Usage in the web app:
        broadcaster = NotificationBroadcaster()
        ops = OpsManager(notify_callback=broadcaster.notify)
        # When a WS connects:
        broadcaster.register_ws(ws)
        # When it disconnects:
        broadcaster.unregister_ws(ws)
    """

    def __init__(
        self,
        telegram_send: Optional[Callable[[str], Coroutine]] = None,
    ) -> None:
        self._ws_clients: Set[WebSocket] = set()
        self._telegram_send = telegram_send
        self._notification_count = 0

    @property
    def connected_clients(self) -> int:
        return len(self._ws_clients)

    @property
    def notification_count(self) -> int:
        return self._notification_count

    def register_ws(self, ws: WebSocket) -> None:
        """Register a connected WebSocket client for notifications."""
        self._ws_clients.add(ws)

    def unregister_ws(self, ws: WebSocket) -> None:
        """Unregister a disconnected WebSocket client."""
        self._ws_clients.discard(ws)

    async def notify(self, message: str) -> None:
        """Broadcast a notification to all channels. Never raises.

        This is the function passed to OpsManager as notify_callback.
        """
        self._notification_count += 1

        # Metrics
        try:
            from mk.metrics import metrics

            metrics.increment("mk_notifications_total")
        except Exception:
            pass

        # Push to all connected WS clients
        frame = {
            "type": "notification",
            "message": message,
            "timestamp": __import__("time").time(),
        }
        dead: List[WebSocket] = []
        for ws in self._ws_clients:
            try:
                await ws.send_json(frame)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._ws_clients.discard(ws)

        # Push to Telegram (if configured)
        if self._telegram_send:
            try:
                await self._telegram_send(message)
            except Exception as exc:
                logger.debug("Telegram notification failed: %s", exc)

        logger.info("[notification] %s", message[:120])
