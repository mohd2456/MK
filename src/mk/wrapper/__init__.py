"""MK wrapper package.

A robust, typed façade over the MK engine that adds strict input validation,
a hard time budget, total exception isolation, AI-failure detection, context
awareness, and observability. This is the single integration point that both
the web API and any terminal/OS surface should use to talk to the assistant.

Typical use::

    from mk.wrapper import MKWrapper, ChatRequest

    wrapper = MKWrapper(engine=my_engine)          # or engine_factory=...
    result = await wrapper.chat(ChatRequest(content="status", context={"page": "/dashboard"}))
    if result.ok:
        print(result.content)
    else:
        print(result.failure_type, "->", result.message)
"""

from __future__ import annotations

from mk.wrapper.context import get_suggestions, known_pages
from mk.wrapper.errors import (
    AIFailureType,
    InputValidationError,
    WrapperError,
    is_retryable,
    user_message_for,
)
from mk.wrapper.failures import (
    analyze_output,
    detect_degenerate_output,
    detect_empty_output,
    validate_structured_output,
)
from mk.wrapper.models import (
    AIFailureInfo,
    ChatRequest,
    ChatResult,
    PageContext,
    SuggestedAction,
)
from mk.wrapper.wrapper import DEFAULT_TIMEOUT_SECONDS, MKWrapper

__all__ = [
    "MKWrapper",
    "DEFAULT_TIMEOUT_SECONDS",
    "ChatRequest",
    "ChatResult",
    "PageContext",
    "SuggestedAction",
    "AIFailureInfo",
    "AIFailureType",
    "WrapperError",
    "InputValidationError",
    "is_retryable",
    "user_message_for",
    "get_suggestions",
    "known_pages",
    "analyze_output",
    "detect_empty_output",
    "detect_degenerate_output",
    "validate_structured_output",
]
