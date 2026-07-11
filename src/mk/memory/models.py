"""Data models for the memory system.

Defines structures for memory entries, conversation turns,
user knowledge, and system state tracking.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class MemoryCategory(str, Enum):
    """Category for memory entries."""

    CONVERSATION = "conversation"
    USER_PREFERENCE = "user_preference"
    USER_KNOWLEDGE = "user_knowledge"
    SYSTEM_STATE = "system_state"
    LEARNED_PATTERN = "learned_pattern"


class MemoryEntry(BaseModel):
    """A single entry in the memory system.

    Represents any piece of information stored in memory,
    with metadata for retrieval and relevance scoring.
    """

    id: str = Field(description="Unique memory entry identifier")
    content: str = Field(description="The memory content")
    category: MemoryCategory = Field(description="Memory category for filtering")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="When this memory was created"
    )
    relevance_score: float = Field(default=1.0, description="Relevance score (0.0 to 1.0)")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class ConversationTurn(BaseModel):
    """A single turn in a conversation.

    Stores both the original content and an optional summary
    for compressed representation in the context window.
    """

    role: str = Field(description="Message role (user, assistant, system)")
    content: str = Field(description="Original message content")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="When this turn occurred"
    )
    summary: Optional[str] = Field(default=None, description="Compressed summary of this turn")
    token_count: int = Field(default=0, description="Estimated token count for this turn")


class UserKnowledge(BaseModel):
    """A piece of knowledge learned about the user.

    Stored in long-term memory with confidence scoring
    and source tracking for provenance.
    """

    key: str = Field(description="Knowledge identifier/topic")
    value: str = Field(description="The knowledge content")
    confidence: float = Field(default=1.0, description="Confidence score (0.0 to 1.0)")
    learned_at: datetime = Field(
        default_factory=datetime.utcnow, description="When this was learned"
    )
    last_accessed: datetime = Field(
        default_factory=datetime.utcnow, description="When this was last retrieved"
    )
    access_count: int = Field(default=0, description="Number of times this was retrieved")
    source: str = Field(default="conversation", description="Where this knowledge came from")
    tags: List[str] = Field(default_factory=list, description="Tags for categorization")


class ServiceStatus(str, Enum):
    """Status of a monitored service."""

    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"
    UNKNOWN = "unknown"


class ServiceInfo(BaseModel):
    """Information about a monitored service."""

    name: str = Field(description="Service name")
    status: ServiceStatus = Field(default=ServiceStatus.UNKNOWN, description="Current status")
    last_check: datetime = Field(default_factory=datetime.utcnow, description="Last status check")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional service metadata"
    )


class SystemState(BaseModel):
    """State of a homelab machine.

    Tracks the current status of a machine and its services,
    along with recent actions performed on it.
    """

    machine_name: str = Field(description="Machine identifier")
    host: str = Field(default="", description="Machine hostname or IP")
    status: str = Field(default="unknown", description="Machine status")
    services: List[ServiceInfo] = Field(
        default_factory=list, description="Services running on this machine"
    )
    last_check: datetime = Field(
        default_factory=datetime.utcnow, description="Last time status was checked"
    )
    recent_actions: List[str] = Field(
        default_factory=list, description="Recent actions taken on this machine"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional machine metadata"
    )
