"""Error types and AI-failure taxonomy for the MK wrapper.

The wrapper draws a hard line between two kinds of problems:

1. **Client errors** — the caller sent something invalid (empty message,
   oversized payload, wrong type). These are raised as exceptions so the
   caller (web API, terminal) can translate them into the right response
   (e.g. HTTP 422). See :class:`InputValidationError`.

2. **AI / runtime failures** — the engine timed out, crashed, produced an
   empty or malformed answer, or no model is configured. These are *never*
   raised out of :meth:`mk.wrapper.wrapper.MKWrapper.chat`; instead they are
   captured, classified via :class:`AIFailureType`, logged, and returned to
   the caller inside a :class:`~mk.wrapper.models.ChatResult` with a safe,
   user-facing fallback message. This is what lets the assistant degrade
   gracefully instead of crashing.
"""

from __future__ import annotations

from enum import Enum


class AIFailureType(str, Enum):
    """Classification of AI / engine failures surfaced by the wrapper.

    The value strings are stable and safe to expose to clients and to use
    as metric label values.
    """

    NONE = "none"
    """No failure — the response is trusted."""

    TIMEOUT = "timeout"
    """The engine did not respond within the configured deadline."""

    ENGINE_ERROR = "engine_error"
    """The engine raised an unexpected exception while processing."""

    EMPTY_OUTPUT = "empty_output"
    """The engine returned an empty or whitespace-only response."""

    MALFORMED_OUTPUT = "malformed_output"
    """The response looked degenerate (e.g. runaway repetition) and is a
    likely hallucination or model loop."""

    SCHEMA_INVALID = "schema_invalid"
    """A structured (JSON) response was requested but the output could not
    be parsed or failed validation — treated as a likely hallucination."""

    NO_ENGINE = "no_engine"
    """No engine could be constructed or supplied to the wrapper."""

    PROVIDER_UNAVAILABLE = "provider_unavailable"
    """All configured LLM providers failed or none are configured."""


# Failure types that represent a real problem (as opposed to a graceful,
# expected degradation). Used to decide whether ``ChatResult.ok`` is False.
HARD_FAILURES = frozenset(
    {
        AIFailureType.TIMEOUT,
        AIFailureType.ENGINE_ERROR,
        AIFailureType.EMPTY_OUTPUT,
        AIFailureType.MALFORMED_OUTPUT,
        AIFailureType.SCHEMA_INVALID,
        AIFailureType.NO_ENGINE,
        AIFailureType.PROVIDER_UNAVAILABLE,
    }
)


class MKWrapperError(Exception):
    """Base class for all wrapper-level exceptions."""


class InputValidationError(MKWrapperError):
    """Raised when caller-supplied input fails validation.

    This is a *client* error. Callers should map it to a 4xx response
    rather than a 5xx — the wrapper did nothing wrong, the input was bad.
    """

    def __init__(self, message: str, *, field: str = "content") -> None:
        """Initialize the validation error.

        Args:
            message: Human-readable description of what was wrong.
            field: The name of the offending field.
        """
        super().__init__(message)
        self.field = field
        self.message = message
