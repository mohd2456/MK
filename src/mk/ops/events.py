"""Event bus — reactive event-driven automation.

The event bus allows MK to react to system events in real-time,
not just on scheduled intervals. Events come from:
- Docker (container state changes, health checks)
- Systemd (service failures, restarts)
- ZFS (scrub completions, errors)
- Plugin triggers (from plugin.yaml trigger declarations)
- Internal (check failures, plan completions)

Handlers subscribe to event patterns and get called when
matching events fire. This enables reactions like:
- "Container restarted 3x in 5 minutes → alert + investigate"
- "ZFS scrub found errors → immediately verify backups"
- "Disk > 90% → trigger cleanup job"
"""

from __future__ import annotations

import asyncio
import fnmatch
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """A system event that can trigger reactions.

    Events have a type (hierarchical, dot-separated) and arbitrary data.
    Examples:
        - "container:restart" with data {"name": "plex", "count": 3}
        - "disk:threshold" with data {"pool": "/data", "percent": 92}
        - "schedule:daily" with data {}
        - "check:failed" with data {"check": "backup_freshness"}
    """

    type: str  # Hierarchical: "category:action" (e.g., "container:restart")
    data: Dict[str, Any] = field(default_factory=dict)
    source: str = "system"  # Where the event came from
    timestamp: float = field(default_factory=time.time)

    @property
    def category(self) -> str:
        """The event category (part before the colon)."""
        return self.type.split(":")[0] if ":" in self.type else self.type

    @property
    def action(self) -> str:
        """The event action (part after the colon)."""
        return self.type.split(":", 1)[1] if ":" in self.type else ""


@dataclass
class EventHandler:
    """A registered event handler.

    Handlers subscribe to event patterns (with glob matching)
    and get called when matching events fire.
    """

    name: str
    pattern: str  # Glob pattern to match event types (e.g., "container:*")
    handler: Callable[[Event], Coroutine]
    description: str = ""
    enabled: bool = True
    call_count: int = 0
    last_called: Optional[float] = None
    cooldown_seconds: float = 0.0  # Minimum time between calls
    _last_triggered: float = 0.0

    def matches(self, event_type: str) -> bool:
        """Check if this handler matches an event type.

        Uses glob-style matching:
        - "container:*" matches "container:restart", "container:stop"
        - "schedule:*" matches all schedule events
        - "*:failed" matches any failed event

        Args:
            event_type: The event type to check.

        Returns:
            True if this handler should fire for this event.
        """
        return fnmatch.fnmatch(event_type, self.pattern)

    @property
    def is_cooled_down(self) -> bool:
        """Whether the cooldown period has elapsed."""
        if self.cooldown_seconds <= 0:
            return True
        return (time.time() - self._last_triggered) >= self.cooldown_seconds


class EventBus:
    """Event bus for reactive system automation.

    Provides pub/sub for system events with:
    - Glob-based pattern matching for subscriptions
    - Async handler execution
    - Cooldown support per handler
    - Event history for debugging
    """

    def __init__(self, max_history: int = 500) -> None:
        """Initialize the event bus.

        Args:
            max_history: Maximum events to keep in history.
        """
        self._handlers: Dict[str, EventHandler] = {}
        self._history: List[Event] = []
        self._max_history = max_history
        self._total_events: int = 0
        self._total_handled: int = 0

    @property
    def handler_count(self) -> int:
        """Number of registered handlers."""
        return len(self._handlers)

    @property
    def total_events(self) -> int:
        """Total events emitted."""
        return self._total_events

    def subscribe(
        self,
        name: str,
        pattern: str,
        handler: Callable[[Event], Coroutine],
        description: str = "",
        cooldown_seconds: float = 0.0,
    ) -> EventHandler:
        """Register an event handler.

        Args:
            name: Unique handler name.
            pattern: Glob pattern for event types to match.
            handler: Async function called with the Event.
            description: Human-readable description.
            cooldown_seconds: Minimum time between handler calls.

        Returns:
            The registered EventHandler.
        """
        eh = EventHandler(
            name=name,
            pattern=pattern,
            handler=handler,
            description=description,
            cooldown_seconds=cooldown_seconds,
        )
        self._handlers[name] = eh
        logger.debug(f"Event handler registered: '{name}' → '{pattern}'")
        return eh

    def unsubscribe(self, name: str) -> bool:
        """Remove a handler.

        Args:
            name: Handler name to remove.

        Returns:
            True if found and removed.
        """
        return self._handlers.pop(name, None) is not None

    async def emit(self, event: Event) -> int:
        """Emit an event, triggering all matching handlers.

        Handlers run concurrently. Exceptions in handlers are
        logged but don't prevent other handlers from running.

        Args:
            event: The event to emit.

        Returns:
            Number of handlers that were triggered.
        """
        self._total_events += 1
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        # Find matching handlers
        matching = [
            h for h in self._handlers.values()
            if h.enabled and h.matches(event.type) and h.is_cooled_down
        ]

        if not matching:
            return 0

        # Execute handlers concurrently
        triggered = 0
        tasks = []
        for handler in matching:
            tasks.append(self._call_handler(handler, event))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    f"Event handler '{matching[i].name}' failed: {result}"
                )
            else:
                triggered += 1

        self._total_handled += triggered
        return triggered

    async def emit_simple(
        self, event_type: str, source: str = "system", **data: Any
    ) -> int:
        """Convenience: emit an event from type and data.

        Args:
            event_type: Event type string.
            source: Event source.
            **data: Event data as keyword arguments.

        Returns:
            Number of handlers triggered.
        """
        event = Event(type=event_type, data=data, source=source)
        return await self.emit(event)

    async def _call_handler(self, handler: EventHandler, event: Event) -> None:
        """Call a single handler safely.

        Args:
            handler: The handler to invoke.
            event: The event to pass.
        """
        handler.call_count += 1
        handler.last_called = time.time()
        handler._last_triggered = time.time()
        await handler.handler(event)

    def get_recent_events(self, limit: int = 50, event_type: Optional[str] = None) -> List[Event]:
        """Get recent events from history.

        Args:
            limit: Maximum events to return.
            event_type: Optional filter by type pattern.

        Returns:
            List of recent events, newest first.
        """
        events = self._history
        if event_type:
            events = [e for e in events if fnmatch.fnmatch(e.type, event_type)]
        return list(reversed(events[-limit:]))

    def get_status(self) -> Dict[str, Any]:
        """Get event bus status."""
        return {
            "total_events": self._total_events,
            "total_handled": self._total_handled,
            "handlers": self.handler_count,
            "history_size": len(self._history),
            "registered_handlers": [
                {
                    "name": h.name,
                    "pattern": h.pattern,
                    "enabled": h.enabled,
                    "call_count": h.call_count,
                    "description": h.description,
                }
                for h in self._handlers.values()
            ],
        }
