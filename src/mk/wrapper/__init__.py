"""MK wrapper package.

A robust, typed integration layer around the MK engine, shared by the web API
and the OS/terminal path. See :mod:`mk.wrapper.wrapper` for the main entry
point, :class:`~mk.wrapper.wrapper.MKWrapper`.

Public API::

    from mk.wrapper import MKWrapper, ChatRequest, ChatResult, PageContext

Everything callers need is re-exported here so downstream code never has to
reach into submodules.
"""

from __future__ import annotations

from mk.wrapper.errors import (
    AIFailureType,
    InputValidationError,
    MKWrapperError,
)
from mk.wrapper.models import (
    ActionKind,
    AIFailureInfo,
    ChatRequest,
    ChatResult,
    PageContext,
    SuggestedAction,
)
from mk.wrapper.wrapper import (
    DEFAULT_TIMEOUT_SECONDS,
    MKWrapper,
    build_default_engine,
)

__all__ = [
    "MKWrapper",
    "build_default_engine",
    "DEFAULT_TIMEOUT_SECONDS",
    "ChatRequest",
    "ChatResult",
    "PageContext",
    "SuggestedAction",
    "ActionKind",
    "AIFailureInfo",
    "AIFailureType",
    "MKWrapperError",
    "InputValidationError",
]
