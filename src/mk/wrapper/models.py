"""Typed input/output models for the MK wrapper.

These Pydantic models are the *contract* between callers (the web API, the
terminal/OS path, the gateway) and the MK engine. They give us:

- **Strict input validation** — a chat message must be a non-empty string
  within a bounded length; page context is normalized to a known shape.
- **Typed outputs** — every caller gets the same :class:`ChatResult` shape,
  including whether the call succeeded, any AI-failure information, usage
  stats, and context-aware suggested actions.

Keeping this contract in one place means the web API and the OS integration
proof-of-concept share exactly the same validation and output semantics.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from mk.wrapper.errors import AIFailureType

# Bounds for user-supplied chat content. Generous enough for real prompts,
# tight enough to reject accidental multi-megabyte payloads.
MAX_CONTENT_LENGTH = 16_000
MAX_SESSION_ID_LENGTH = 128


class ActionKind(str, Enum):
    """The kind of a suggested action, so the UI can render it appropriately."""

    SUGGESTION = "suggestion"
    """A natural-language prompt the user can send to the assistant."""

    COMMAND = "command"
    """A direct command/shortcut that maps to a concrete operation."""

    NAVIGATION = "navigation"
    """A hint to navigate to another screen/page."""


class SuggestedAction(BaseModel):
    """A single context-aware action offered to the user.

    Used both for page-based suggestion chips and for actions attached to a
    chat response.
    """

    id: str = Field(description="Stable identifier for the action")
    label: str = Field(description="Short, human-readable label")
    prompt: str = Field(description="Text sent to the assistant when chosen")
    kind: ActionKind = Field(default=ActionKind.SUGGESTION, description="Rendering hint")


class PageContext(BaseModel):
    """Where the user currently is in the UI / OS.

    This is how the assistant becomes *context aware*: the caller tells the
    wrapper which page or screen is active, and the wrapper uses it to pick
    relevant suggestions and to enrich prompts.
    """

    path: str = Field(default="/", description="Route/screen path, e.g. '/storage'")
    label: Optional[str] = Field(default=None, description="Human-readable screen name")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Free-form context (selected item, filters, ...)"
    )

    @field_validator("path", mode="before")
    @classmethod
    def _normalize_path(cls, value: Any) -> str:
        """Coerce and normalize the path to a leading-slash route string."""
        if value is None:
            return "/"
        text = str(value).strip()
        if not text:
            return "/"
        if not text.startswith("/"):
            text = "/" + text
        # Drop any query/fragment — we only key off the route.
        for sep in ("?", "#"):
            if sep in text:
                text = text.split(sep, 1)[0]
        # Collapse trailing slash (except root).
        if len(text) > 1:
            text = text.rstrip("/") or "/"
        return text

    @classmethod
    def from_raw(cls, raw: Any) -> "PageContext":
        """Build a :class:`PageContext` from loosely-typed caller input.

        Accepts ``None``, a plain path string, a dict, or an existing
        :class:`PageContext`. Never raises for shape — unknown/garbage input
        degrades to the dashboard context.
        """
        if raw is None:
            return cls()
        if isinstance(raw, PageContext):
            return raw
        if isinstance(raw, str):
            return cls(path=raw)
        if isinstance(raw, dict):
            # Common alternate keys the frontend might send.
            path = raw.get("path") or raw.get("pathname") or raw.get("route") or "/"
            label = raw.get("label") or raw.get("title")
            metadata = raw.get("metadata")
            if not isinstance(metadata, dict):
                # Stash any leftover keys as metadata for the model to see.
                metadata = {
                    k: v
                    for k, v in raw.items()
                    if k not in {"path", "pathname", "route", "label", "title", "metadata"}
                }
            return cls(path=path, label=label, metadata=metadata)
        return cls()


class ChatRequest(BaseModel):
    """A validated request to the assistant.

    Construction enforces the input contract; an invalid ``content`` raises a
    Pydantic ``ValidationError`` which the wrapper converts into an
    :class:`~mk.wrapper.errors.InputValidationError`.
    """

    content: str = Field(description="The user's message")
    context: PageContext = Field(default_factory=PageContext, description="Current UI context")
    session_id: Optional[str] = Field(default=None, description="Opaque session identifier")
    expects_json: bool = Field(
        default=False,
        description="If True, the response is validated as JSON (hallucination guard)",
    )

    @field_validator("content")
    @classmethod
    def _validate_content(cls, value: str) -> str:
        """Ensure content is a non-empty, reasonably-sized string."""
        if not isinstance(value, str):
            raise ValueError("content must be a string")
        stripped = value.strip()
        if not stripped:
            raise ValueError("content must not be empty")
        if len(value) > MAX_CONTENT_LENGTH:
            raise ValueError(f"content exceeds maximum length of {MAX_CONTENT_LENGTH} characters")
        return stripped

    @field_validator("session_id")
    @classmethod
    def _validate_session(cls, value: Optional[str]) -> Optional[str]:
        """Bound the session id length if provided."""
        if value is None:
            return None
        if len(value) > MAX_SESSION_ID_LENGTH:
            raise ValueError(
                f"session_id exceeds maximum length of {MAX_SESSION_ID_LENGTH} characters"
            )
        return value


class AIFailureInfo(BaseModel):
    """Structured description of an AI/engine failure.

    ``message`` is safe to show to end users. ``detail`` carries internal
    diagnostics (exception text, etc.) for logs and debugging.
    """

    type: AIFailureType = Field(description="Failure classification")
    message: str = Field(description="User-facing explanation")
    detail: Optional[str] = Field(default=None, description="Internal diagnostic detail")
    retryable: bool = Field(default=False, description="Whether retrying may succeed")


class ChatResult(BaseModel):
    """The uniform result of a wrapper chat call.

    Every caller — web, terminal, gateway — receives this shape. On success
    ``ok`` is True and ``failure`` is None. On any AI/engine problem ``ok`` is
    False, ``failure`` describes what happened, and ``content`` holds a safe
    fallback message suitable for display.
    """

    ok: bool = Field(description="True if the response is trusted")
    content: str = Field(description="Assistant reply or safe fallback text")
    actions: List[SuggestedAction] = Field(
        default_factory=list, description="Context-aware suggested actions"
    )
    failure: Optional[AIFailureInfo] = Field(default=None, description="Failure info, if any")
    degraded: bool = Field(
        default=False,
        description="True when running without an LLM (limited, command-only mode)",
    )
    llm_available: bool = Field(default=False, description="Whether an LLM provider is configured")
    tokens_used: int = Field(default=0, description="Tokens consumed by the engine")
    cost: float = Field(default=0.0, description="Estimated cost in USD")
    provider_used: Optional[str] = Field(default=None, description="Which LLM provider answered")
    request_id: Optional[str] = Field(default=None, description="Correlation id for tracing")
