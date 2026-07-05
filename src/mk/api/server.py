"""Internal HTTP API server for MK.

Provides HTTP endpoints for gateway-to-core communication.
The Telegram gateway and other clients communicate with MK
through these endpoints.

Endpoints:
    POST /message - Send a message to MK and get a response
    GET /health - Health check endpoint
    POST /proactive - Trigger a proactive message to the user
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field


class MessageRequest(BaseModel):
    """Incoming message request from a gateway."""

    text: str = Field(description="Message text from user")
    sender_id: str = Field(description="Unique sender identifier")
    platform: str = Field(default="telegram", description="Source platform")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class MessageResponse(BaseModel):
    """Response to a message request."""

    text: str = Field(description="MK's response text")
    sender_id: str = Field(description="Original sender ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Response metadata")


class ProactiveRequest(BaseModel):
    """Request to send a proactive message to a user."""

    text: str = Field(description="Message text to send")
    target_id: str = Field(description="Target user/chat identifier")
    platform: str = Field(default="telegram", description="Target platform")
    priority: str = Field(default="normal", description="Message priority: low, normal, high")


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(description="Service status: healthy or degraded")
    version: str = Field(description="MK version")
    uptime_seconds: float = Field(description="Uptime in seconds")


@dataclass
class APIServer:
    """Internal HTTP API server for MK core.

    Handles requests from messaging gateways and provides
    health monitoring. Designed to be lightweight and fast.

    Attributes:
        host: Bind address for the server.
        port: Port number for the server.
        message_handler: Callback for processing incoming messages.
        proactive_queue: Queue of pending proactive messages.
    """

    host: str = "127.0.0.1"
    port: int = 8741
    message_handler: Optional[Callable] = None
    proactive_queue: List[Dict[str, Any]] = field(default_factory=list)
    _started: bool = field(default=False, init=False)

    async def handle_message(self, request: MessageRequest) -> MessageResponse:
        """Process an incoming message from a gateway.

        Routes the message through MK's agent loop and returns
        the response.

        Args:
            request: The incoming message request.

        Returns:
            MessageResponse with MK's reply.
        """
        if self.message_handler:
            response_text = await self.message_handler(
                text=request.text,
                sender_id=request.sender_id,
                platform=request.platform,
            )
        else:
            response_text = "MK is running but no message handler is configured."

        return MessageResponse(
            text=response_text,
            sender_id=request.sender_id,
        )

    async def handle_health(self) -> HealthResponse:
        """Handle a health check request.

        Returns:
            HealthResponse with current status.
        """
        import time

        from mk import __version__

        return HealthResponse(
            status="healthy" if self._started else "starting",
            version=__version__,
            uptime_seconds=0.0,  # Will be set by the actual runtime
        )

    async def handle_proactive(self, request: ProactiveRequest) -> Dict[str, Any]:
        """Queue a proactive message for delivery.

        The gateway polls or subscribes to receive these messages
        and delivers them to the user.

        Args:
            request: The proactive message request.

        Returns:
            Acknowledgment with message ID.
        """
        import time

        message_entry = {
            "text": request.text,
            "target_id": request.target_id,
            "platform": request.platform,
            "priority": request.priority,
            "queued_at": time.time(),
        }
        self.proactive_queue.append(message_entry)

        return {"status": "queued", "queue_length": len(self.proactive_queue)}

    def get_pending_proactive(self, platform: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get and clear pending proactive messages.

        Args:
            platform: Optional platform filter.

        Returns:
            List of pending proactive messages.
        """
        if platform:
            matching = [m for m in self.proactive_queue if m["platform"] == platform]
            self.proactive_queue = [
                m for m in self.proactive_queue if m["platform"] != platform
            ]
            return matching
        else:
            messages = list(self.proactive_queue)
            self.proactive_queue.clear()
            return messages

    async def start(self) -> None:
        """Start the API server.

        In production, this launches an aiohttp or uvicorn server.
        For now, sets the started flag for testing.
        """
        self._started = True

    async def stop(self) -> None:
        """Stop the API server gracefully."""
        self._started = False


def create_app(
    host: str = "127.0.0.1",
    port: int = 8741,
    message_handler: Optional[Callable] = None,
) -> APIServer:
    """Create and configure the API server.

    Args:
        host: Bind address.
        port: Port number.
        message_handler: Async callback for processing messages.

    Returns:
        Configured APIServer instance.
    """
    return APIServer(
        host=host,
        port=port,
        message_handler=message_handler,
    )
