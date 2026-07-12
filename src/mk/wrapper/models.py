"""Typed input/output contracts for the MK wrapper.

Everything crossing the wrapper boundary is a Pydantic model, so validation
happens once, in one place, with clear error messages. The web API, the
terminal/OS path, and tests all share these exact shapes.

Inputs
    - :class:`PageContext` — where the user is (page/screen) plus optional hints.
    - :class:`ChatRequest` — a validated conversational request.

Outputs
    - :class:`SuggestedAction` — a context-relevant action the UI can surface.
    - :class:`AIFailureInfo` — structured detail about an AI failure.
    - :class:`ChatResult` — the single, uniform result type the wrapper returns.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from mk.wrapper.errors import AIFailureType

# Bounds chosen to protect the engine and keep memory/CPU predictable.
MAX_CONTENT_LENGTH = 16_000
MAX_SESSION_ID_LENGTH = 128
MAX_PAGE_LENGTH = 256


class PageContext(BaseModel):
    """The user's current location and lightweight UI context.

    ``page`` is normalized to a leading-slash route path (e.g. ``/dashboard``)
    so downstream suggestion matching is stable regardless of how the client
    formats it. All fields are optional except that an empty context is valid
    (it simply yields generic suggestions).
    """

    page: str = Field(default="/", description="Current route/screen, e.g. /dashboard")
    title: Optional[str] = Field(default=None, description="Human-readable page title")
    selection: Optional[str] = Field(
        default=None, description="Currently selected entity, if any (e.g. a container name)"
    )
    extra: Dict[str, Any] = Field(
        default_factory=dict, description="Arbitrary client-supplied context hints"
    )

    @field_validator("page", mode="before")
    @classmethod
    def _normalize_page(cls, v: Any) -> str:
        """Normalize the page into a bounded, leading-slash route string."""
        if v is None:
            return "/"
        text = str(v).strip()
        if not text:
            return "/"
        # Drop query string / fragment — routing only cares about the path.
        for sep in ("?", "#"):
            if sep in text:
                text = text.split(sep, 1)[0]
        if not text.startswith("/"):
            text = "/" + text
        # Collapse trailing slash (except root) for stable prefix matching.
        if len(text) > 1 and text.endswith("/"):
            text = text.rstrip("/")
        return text[:MAX_PAGE_LENGTH]


class ChatRequest(BaseModel):
    """A validated conversational request.

    Enforces a non-empty, bounded message and a bounded session id. Invalid
    input is rejected here (via :class:`~mk.wrapper.errors.InputValidationError`
    in the wrapper), never passed to the engine.
    """

    content: str = Field(description="The user's message")
    session_id: Optional[str] = Field(default=None, description="Opaque session/conversation id")
    context: PageContext = Field(default_factory=PageContext, description="Current page context")
    expect_json: bool = Field(
        default=False,
        description="If True, the response is expected to be valid JSON and is schema-checked.",
    )

    @field_validator("content")
    @classmethod
    def _validate_content(cls, v: str) -> str:
        if v is None:
            raise ValueError("content must not be null")
        stripped = v.strip()
        if not stripped:
            raise ValueError("content must not be empty")
        if len(v) > MAX_CONTENT_LENGTH:
            raise ValueError(f"content exceeds maximum length of {MAX_CONTENT_LENGTH} characters")
        return stripped

    @field_validator("session_id")
    @classmethod
    def _validate_session_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if len(v) > MAX_SESSION_ID_LENGTH:
            raise ValueError(f"session_id exceeds maximum length of {MAX_SESSION_ID_LENGTH}")
        return v


class SuggestedAction(BaseModel):
    """A context-relevant action or shortcut the UI can surface.

    ``command`` is the text that would be sent to the assistant if the user
    activates the suggestion, making suggestions self-executing.
    """

    id: str = Field(description="Stable identifier for the action")
    label: str = Field(description="Short, human-friendly label")
    description: str = Field(default="", description="One-line explanation of what it does")
    command: str = Field(description="Assistant command/prompt to run when activated")
    category: str = Field(default="general", description="Grouping hint for the UI")
    icon: Optional[str] = Field(default=None, description="Optional icon name hint for the UI")


class AIFailureInfo(BaseModel):
    """Structured detail about an AI/engine failure.

    ``detail`` is safe-for-logs technical context; the user-facing text lives
    in :attr:`ChatResult.message`.
    """

    failure_type: AIFailureType = Field(description="Classification of the failure")
    detail: str = Field(default="", description="Technical detail for logs/diagnostics")
    retryable: bool = Field(default=False, description="Whether retrying may succeed")


class ChatResult(BaseModel):
    """The single, uniform result type returned by the wrapper.

    On success, ``ok`` is True and ``content``/``message`` carry the reply.
    On failure, ``ok`` is False, ``failure`` describes what went wrong, and
    ``message`` is a calm, user-facing fallback. Either way the caller gets a
    well-formed object — the wrapper never propagates engine exceptions.
    """

    ok: bool = Field(description="True if the assistant produced a usable answer")
    content: str = Field(default="", description="The assistant's reply text (may be a fallback)")
    message: str = Field(
        default="",
        description="User-facing message; equals content on success, fallback text on failure",
    )
    failure: Optional[AIFailureInfo] = Field(
        default=None, description="Populated only when ok is False"
    )
    actions: List[Dict[str, Any]] = Field(
        default_factory=list, description="Inline actions returned with the reply"
    )
    suggestions: List[SuggestedAction] = Field(
        default_factory=list, description="Context-aware follow-up suggestions"
    )
    degraded: bool = Field(
        default=False,
        description="True when answered in a reduced-capability mode (e.g. no LLM configured)",
    )
    provider: Optional[str] = Field(default=None, description="LLM provider that served the reply")
    tokens_used: int = Field(default=0, description="Tokens consumed, if known")
    cost: float = Field(default=0.0, description="Estimated cost in USD, if known")
    was_direct_command: bool = Field(
        default=False, description="Whether the engine handled this as a direct command"
    )
    elapsed_ms: float = Field(default=0.0, description="Wall-clock processing time in milliseconds")

    @property
    def failure_type(self) -> Optional[str]:
        """Convenience accessor for the failure type value, if any."""
        return self.failure.failure_type.value if self.failure else None
