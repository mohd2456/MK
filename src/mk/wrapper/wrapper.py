"""The MK wrapper — a single, robust entry point to the MK engine.

``MKWrapper`` is the central integration point for talking to MK. Both the
web API and the OS/terminal path go through it so they share identical
validation, timeout handling, AI-failure detection, logging, and metrics.

Design goals:

- **Strict input validation** — every call is validated against the typed
  :class:`~mk.wrapper.models.ChatRequest` contract.
- **Never crash the caller** — the only exception ``chat`` raises is
  :class:`~mk.wrapper.errors.InputValidationError` for bad input. Every
  engine/AI failure is caught, classified, logged, and returned as a
  :class:`~mk.wrapper.models.ChatResult` with a safe fallback message.
- **AI-failure awareness** — timeouts, empty/degenerate output, invalid
  structured output, missing engine, and provider outages are detected and
  reported through a stable taxonomy (:class:`~mk.wrapper.errors.AIFailureType`).
- **Context awareness** — the current page/screen drives suggested actions.
- **Lazy, safe engine construction** — if no engine is supplied, a default
  one is built on first use; if that build fails, the wrapper still responds
  gracefully instead of raising.

The wrapper only depends on the engine having an async
``process(str) -> AgentResponse`` method, so it works with both ``MKEngine``
and ``MKEngineV2`` (and with test doubles).
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any, Awaitable, Callable, Optional, Union

from mk.observability import metrics
from mk.wrapper import context as context_module
from mk.wrapper.errors import HARD_FAILURES, AIFailureType, InputValidationError
from mk.wrapper.failures import detect_output_failure
from mk.wrapper.models import (
    AIFailureInfo,
    ChatRequest,
    ChatResult,
    PageContext,
    SuggestedAction,
)

logger = logging.getLogger("mk.wrapper")

# Default deadline for a single engine call. Long enough for multi-step agent
# loops, short enough that a wedged provider does not hang the UI forever.
DEFAULT_TIMEOUT_SECONDS = 60.0

# Type alias for the pluggable engine factory.
EngineFactory = Callable[[], Union[Any, Awaitable[Any]]]

_NO_ENGINE_MESSAGE = (
    "MK is running, but its engine could not be started. Basic features are "
    "unavailable right now. Check the server logs for details."
)
_TIMEOUT_MESSAGE = (
    "That took longer than expected and I stopped waiting. Please try again — "
    "if it keeps happening, the AI provider may be slow or unreachable."
)
_ENGINE_ERROR_MESSAGE = (
    "Something went wrong while processing that request. I've logged the error. Please try again."
)


def build_default_engine() -> Any:
    """Construct a lightweight default engine for standalone use.

    Builds a V1 :class:`~mk.core.engine.MKEngine` with server management and
    any configured LLM providers. Every step is defensive: configuration,
    server setup, and provider setup failures are logged and swallowed so the
    engine is always returned in *some* usable state (command-only mode if no
    LLM is available).

    Returns:
        An initialized ``MKEngine`` instance.
    """
    from mk.config.settings import Settings, load_config
    from mk.core.engine import MKEngine

    try:
        settings = load_config()
    except Exception as exc:  # pragma: no cover - config edge cases
        logger.warning("Falling back to default settings: %s", exc)
        settings = Settings()

    engine = MKEngine(settings=settings)

    try:
        engine.setup_server_management()
    except Exception as exc:
        logger.warning("Server management unavailable: %s", exc)

    try:
        engine.setup_llm_providers()
    except Exception as exc:
        logger.info("LLM providers not configured: %s", exc)

    return engine


class MKWrapper:
    """Robust, typed wrapper around the MK engine.

    Args:
        engine: A pre-built engine (``MKEngine``/``MKEngineV2`` or any object
            with an async ``process(str)`` method). If ``None``, a default
            engine is lazily built via ``engine_factory`` on first use.
        timeout: Per-call deadline in seconds for engine processing.
        engine_factory: Callable used to build the engine when ``engine`` is
            ``None``. Defaults to :func:`build_default_engine`. May be sync or
            async.
    """

    def __init__(
        self,
        engine: Optional[Any] = None,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        engine_factory: Optional[EngineFactory] = None,
    ) -> None:
        self._engine = engine
        self._timeout = max(1.0, float(timeout))
        self._engine_factory = engine_factory or build_default_engine
        self._build_lock = asyncio.Lock()
        self._build_attempted = False

    # ── Engine lifecycle ────────────────────────────────────────────

    @property
    def has_engine(self) -> bool:
        """Whether an engine instance is currently available (without building)."""
        return self._engine is not None

    async def _get_engine(self) -> Optional[Any]:
        """Return the engine, building it lazily and safely if needed.

        Returns ``None`` if no engine could be constructed. The build is
        attempted at most once to avoid repeated expensive failures.
        """
        if self._engine is not None:
            return self._engine

        async with self._build_lock:
            if self._engine is not None:
                return self._engine
            if self._build_attempted:
                return None
            self._build_attempted = True
            try:
                built = self._engine_factory()
                if inspect.isawaitable(built):
                    built = await built
                self._engine = built
            except Exception as exc:
                logger.error("Failed to build MK engine: %s", exc, exc_info=True)
                self._engine = None
        return self._engine

    @staticmethod
    def _llm_available(engine: Any) -> bool:
        """Best-effort check for whether the engine has an LLM configured."""
        if engine is None:
            return False
        loop = getattr(engine, "_agent_loop", None)
        router = getattr(engine, "_llm_router", None)
        provider = getattr(engine, "_llm_provider", None)
        return bool(loop or router or provider)

    # ── Public API ──────────────────────────────────────────────────

    def suggestions(self, context: Any = None, limit: int = 4) -> list[SuggestedAction]:
        """Return context-aware suggested actions for a page/screen.

        Args:
            context: A :class:`PageContext`, a path string, a dict, or None.
            limit: Maximum number of suggestions.

        Returns:
            A list of :class:`SuggestedAction` (never None).
        """
        ctx = PageContext.from_raw(context)
        return context_module.suggestions_for(ctx, limit=limit)

    def context_label(self, context: Any = None) -> str:
        """Return the human-readable label for a page/screen context."""
        return context_module.label_for(PageContext.from_raw(context))

    async def chat(
        self,
        request: Union[ChatRequest, str, dict],
        *,
        request_id: Optional[str] = None,
    ) -> ChatResult:
        """Process a chat message and return a uniform, safe result.

        Args:
            request: A :class:`ChatRequest`, a raw message string, or a dict
                with at least a ``content`` key (and optional ``context``,
                ``session_id``, ``expects_json``).
            request_id: Optional correlation id for tracing/logging.

        Returns:
            A :class:`ChatResult`. ``ok`` is False when an AI/engine failure
            was detected, in which case ``content`` is a safe fallback.

        Raises:
            InputValidationError: If the input fails validation. This is the
                only exception ``chat`` raises; it signals a *client* error.
        """
        req = self._coerce_request(request)
        actions = self.suggestions(req.context)
        metrics.increment("mk_wrapper_chat_total")

        engine = await self._get_engine()
        if engine is None:
            return self._failure_result(
                req,
                actions,
                AIFailureInfo(
                    type=AIFailureType.NO_ENGINE,
                    message=_NO_ENGINE_MESSAGE,
                    detail="Engine factory returned None.",
                    retryable=False,
                ),
                request_id=request_id,
                llm_available=False,
            )

        llm_available = self._llm_available(engine)

        # Run the engine with a hard deadline and full exception isolation.
        try:
            response = await asyncio.wait_for(engine.process(req.content), timeout=self._timeout)
        except asyncio.TimeoutError:
            logger.warning(
                "Engine timed out after %.1fs (request_id=%s)", self._timeout, request_id
            )
            return self._failure_result(
                req,
                actions,
                AIFailureInfo(
                    type=AIFailureType.TIMEOUT,
                    message=_TIMEOUT_MESSAGE,
                    detail=f"Engine.process exceeded {self._timeout:.1f}s.",
                    retryable=True,
                ),
                request_id=request_id,
                llm_available=llm_available,
            )
        except Exception as exc:
            failure_type = self._classify_exception(exc)
            logger.error(
                "Engine error (%s) processing request_id=%s: %s",
                failure_type.value,
                request_id,
                exc,
                exc_info=True,
            )
            return self._failure_result(
                req,
                actions,
                AIFailureInfo(
                    type=failure_type,
                    message=_ENGINE_ERROR_MESSAGE,
                    detail=f"{type(exc).__name__}: {exc}",
                    retryable=failure_type == AIFailureType.PROVIDER_UNAVAILABLE,
                ),
                request_id=request_id,
                llm_available=llm_available,
            )

        # Extract fields defensively — engine contract is duck-typed.
        content = str(getattr(response, "final_response", "") or "")
        tokens_used = int(getattr(response, "tokens_used", 0) or 0)
        cost = float(getattr(response, "cost", 0.0) or 0.0)
        provider_used = getattr(response, "provider_used", None)

        # Inspect the output for detectable AI failures.
        failure = detect_output_failure(content, expects_json=req.expects_json)
        if failure is not None:
            logger.warning(
                "AI output failure (%s) for request_id=%s", failure.type.value, request_id
            )
            metrics.increment("mk_wrapper_failures_total", labels={"type": failure.type.value})
            return ChatResult(
                ok=False,
                content=failure.message,
                actions=actions,
                failure=failure,
                degraded=not llm_available,
                llm_available=llm_available,
                tokens_used=tokens_used,
                cost=cost,
                provider_used=provider_used,
                request_id=request_id,
            )

        metrics.increment("mk_wrapper_success_total")
        return ChatResult(
            ok=True,
            content=content,
            actions=actions,
            failure=None,
            degraded=not llm_available,
            llm_available=llm_available,
            tokens_used=tokens_used,
            cost=cost,
            provider_used=provider_used,
            request_id=request_id,
        )

    # ── Internals ───────────────────────────────────────────────────

    @staticmethod
    def _coerce_request(request: Union[ChatRequest, str, dict]) -> ChatRequest:
        """Validate and normalize loosely-typed input into a ChatRequest.

        Raises:
            InputValidationError: If validation fails.
        """
        try:
            if isinstance(request, ChatRequest):
                return request
            if isinstance(request, str):
                return ChatRequest(content=request)
            if isinstance(request, dict):
                data = dict(request)
                data["context"] = PageContext.from_raw(data.get("context"))
                return ChatRequest(**data)
        except InputValidationError:
            raise
        except Exception as exc:
            # Pydantic ValidationError and friends become a client error.
            raise InputValidationError(_first_error_message(exc)) from exc

        raise InputValidationError(f"Unsupported request type: {type(request).__name__}")

    @staticmethod
    def _classify_exception(exc: Exception) -> AIFailureType:
        """Map an engine exception to a failure type."""
        # Provider layer failures (import locally to avoid hard dependency).
        try:
            from mk.llm.base import ProviderError

            if isinstance(exc, ProviderError):
                return AIFailureType.PROVIDER_UNAVAILABLE
        except Exception:  # pragma: no cover - defensive
            pass
        return AIFailureType.ENGINE_ERROR

    def _failure_result(
        self,
        req: ChatRequest,
        actions: list[SuggestedAction],
        failure: AIFailureInfo,
        *,
        request_id: Optional[str],
        llm_available: bool,
    ) -> ChatResult:
        """Build a ChatResult for a failure, recording metrics."""
        if failure.type in HARD_FAILURES:
            metrics.increment("mk_wrapper_failures_total", labels={"type": failure.type.value})
        return ChatResult(
            ok=False,
            content=failure.message,
            actions=actions,
            failure=failure,
            degraded=not llm_available,
            llm_available=llm_available,
            request_id=request_id,
        )


def _first_error_message(exc: Exception) -> str:
    """Extract a concise, user-safe message from a validation exception."""
    # Pydantic ValidationError exposes .errors(); fall back to str().
    errors = getattr(exc, "errors", None)
    if callable(errors):
        try:
            items = errors()
            if items:
                first = items[0]
                loc = ".".join(str(p) for p in first.get("loc", ())) or "input"
                msg = first.get("msg", "invalid value")
                # Pydantic prefixes messages with "Value error, "
                msg = msg.replace("Value error, ", "")
                return f"Invalid {loc}: {msg}"
        except Exception:  # pragma: no cover - defensive
            pass
    return str(exc) or "Invalid input"
