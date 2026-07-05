"""Core data models for MK.

Defines the fundamental data structures used throughout the system:
messages, conversations, tool calls, agent steps, and responses.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Role(str, Enum):
    """Message role in a conversation."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class Message(BaseModel):
    """A single message in a conversation."""

    role: Role = Field(description="Who sent the message")
    content: str = Field(description="Message content")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Conversation(BaseModel):
    """A conversation consisting of ordered messages."""

    messages: List[Message] = Field(default_factory=list)
    id: Optional[str] = Field(default=None, description="Conversation identifier")

    def add_message(self, role: Role, content: str) -> Message:
        """Add a new message to the conversation.

        Args:
            role: The role of the message sender.
            content: The message content.

        Returns:
            The created Message instance.
        """
        msg = Message(role=role, content=content)
        self.messages.append(msg)
        return msg

    @property
    def last_message(self) -> Optional[Message]:
        """Return the most recent message, or None if empty."""
        return self.messages[-1] if self.messages else None

    @property
    def message_count(self) -> int:
        """Return the number of messages in the conversation."""
        return len(self.messages)


class ToolCall(BaseModel):
    """A tool invocation requested by the LLM."""

    name: str = Field(description="Tool name to invoke")
    args: Dict[str, Any] = Field(default_factory=dict, description="Tool arguments")
    result: Optional[str] = Field(default=None, description="Tool execution result")
    error: Optional[str] = Field(default=None, description="Error if tool failed")
    executed: bool = Field(default=False, description="Whether the tool was executed")


class AgentStep(BaseModel):
    """A single step in the agent's reasoning process."""

    thought: Optional[str] = Field(default=None, description="Agent's reasoning")
    action: Optional[ToolCall] = Field(default=None, description="Tool call if any")
    observation: Optional[str] = Field(default=None, description="Result observation")


class AgentResponse(BaseModel):
    """Complete response from the agent loop."""

    steps: List[AgentStep] = Field(default_factory=list, description="Reasoning steps taken")
    final_response: str = Field(description="Final response to the user")
    tokens_used: int = Field(default=0, description="Total tokens consumed")
    cost: float = Field(default=0.0, description="Estimated cost in USD")
    provider_used: Optional[str] = Field(default=None, description="Which LLM provider was used")
    was_direct_command: bool = Field(
        default=False, description="Whether this was routed as a direct command"
    )
