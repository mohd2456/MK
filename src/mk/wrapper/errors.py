"""Error taxonomy for the MK wrapper.

Defines the two distinct failure surfaces the wrapper exposes:

1. :class:`InputValidationError` — the *caller* sent something invalid
   (empty message, oversized payload, malformed context). This is a client
   error and is the ONLY exception the wrapper is allowed to raise. The web
   layer maps it to an HTTP 422.

2. :class:`AIFailureType` — the AI/engine side went wrong (timeout, crash,
   empty/garbled output, hallucinated structure, no provider configured).
   These are never raised; they are caught, classified, logged, and returned
   inside a :class:`~mk.wrapper.models.ChatResult` so the API never 500s.

Keeping these two concerns separate is what lets the wrapper guarantee
"no unhandled exception escapes to the API" while still giving callers precise,
actionable information about what went wrong.
"""

from __future__ import annotations

from enum import Enum


class AIFailureType(str, Enum):
    """Classification of an AI/engine failure.

    The value is a stable, lowercase string safe to expose in API responses
    and to key metrics/dashboards on.
    """

    TIMEOUT = "timeout"
    """The engine did not respond within the configured time budget."""

    ENGINE_ERROR = "engine_error"
    """The engine raised an unexpected exception while processing."""

    EMPTY_OUTPUT = "empty_output"
    """The engine returned no usable text (empty or whitespace only)."""

    MALFORMED_OUTPUT = "malformed_output"
    """The output was structurally degenerate (e.g. runaway repetition),
    a common signal of a looping or hallucinating model."""

    SCHEMA_INVALID = "schema_invalid"
    """Structured output was expected but did not parse or failed validation
    against the requested schema — a strong hallucination signal."""

    NO_ENGINE = "no_engine"
    """No engine is wired in and no default could be constructed, so the
    assistant cannot process conversational requests."""

    PROVIDER_UNAVAILABLE = "provider_unavailable"
    """Every configured LLM provider failed or none is reachable."""


# User-facing fallback messages. Deliberately calm, non-technical, and
# actionable. Never leak stack traces or provider internals to end users.
_USER_MESSAGES: dict[AIFailureType, str] = {
    AIFailureType.TIMEOUT: (
        "That took longer than expected and I stopped to keep things responsive. "
        "Please try again, or rephrase your request more simply."
    ),
    AIFailureType.ENGINE_ERROR: (
        "Something went wrong while I was working on that. The issue has been "
        "logged. Please try again in a moment."
    ),
    AIFailureType.EMPTY_OUTPUT: (
        "I wasn't able to produce a response for that. Could you rephrase or add "
        "a little more detail?"
    ),
    AIFailureType.MALFORMED_OUTPUT: (
        "My response came back garbled, so I've held it back rather than show "
        "something unreliable. Please try again."
    ),
    AIFailureType.SCHEMA_INVALID: (
        "I couldn't produce a valid result for that action, so I've stopped "
        "rather than act on bad data. Please try again."
    ),
    AIFailureType.NO_ENGINE: (
        "The AI assistant isn't configured yet. You can still use direct "
        "commands, or add an LLM provider key to enable full conversation."
    ),
    AIFailureType.PROVIDER_UNAVAILABLE: (
        "No AI provider is available right now. Please check your provider keys "
        "or try again shortly."
    ),
}

# Which failure types are worth retrying automatically / suggesting a retry.
_RETRYABLE: frozenset[AIFailureType] = frozenset(
    {
        AIFailureType.TIMEOUT,
        AIFailureType.ENGINE_ERROR,
        AIFailureType.EMPTY_OUTPUT,
        AIFailureType.MALFORMED_OUTPUT,
        AIFailureType.PROVIDER_UNAVAILABLE,
    }
)


def user_message_for(failure: AIFailureType) -> str:
    """Return the calm, user-facing fallback message for a failure type."""
    return _USER_MESSAGES.get(
        failure,
        "I ran into a problem handling that request. Please try again.",
    )


def is_retryable(failure: AIFailureType) -> bool:
    """Whether the given failure is generally worth retrying."""
    return failure in _RETRYABLE


class WrapperError(Exception):
    """Base class for all wrapper-originated exceptions."""


class InputValidationError(WrapperError):
    """Raised when caller input fails validation.

    This is a *client* error, distinct from an AI failure: the request was
    never valid, so there is nothing for the engine to attempt. The web layer
    maps this to HTTP 422 with the provided detail.
    """

    def __init__(self, detail: str, field: str | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.field = field
