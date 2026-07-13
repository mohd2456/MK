"""The MK wrapper — a robust, typed façade over the MK engine.

:class:`MKWrapper` is the single integration point every surface (web API,
WebSocket, terminal/OS path, tests) should use to talk to the assistant. It
adds, around whatever engine it wraps:

* **Strict input validation** — every request becomes a validated
  :class:`~mk.wrapper.models.ChatRequest`; bad input raises
  :class:`~mk.wrapper.errors.InputValidationError` (mapped to HTTP 422) and is
  never handed to the engine.
* **A hard time budget** — engine calls run under :func:`asyncio.wait_for`, so
  a hung provider can't hang the request.
* **Total exception isolation** — any engine/provider error is caught,
  classified into an :class:`~mk.wrapper.errors.AIFailureType`, logged, and
  returned inside a :class:`~mk.wrapper.models.ChatResult`. No engine exception
  ever escapes to the caller.
* **AI-failure detection** — successful replies are screened for empty,
  degenerate/looping, and schema-invalid output (hallucination signals).
* **Context awareness** — every result carries page-relevant suggestions.
* **Observability** — structured logs and metrics for every outcome.

The wrapper is intentionally duck-typed: it works with :class:`MKEngine`,
:class:`MKEngineV2`, or any object exposing an awaitable ``process(str)`` that
returns an object with a ``final_response`` attribute (or a plain string).
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from typing import Any, AsyncIterator, Awaitable, Callable, List, Optional, Union

from mk.observability import metrics
from mk.wrapper.context import get_suggestions
from mk.wrapper.errors import (
    AIFailureType,
    InputValidationError,
    is_retryable,
    user_message_for,
)
from mk.wrapper.failures import analyze_output
from mk.wrapper.models import (
    AIFailureInfo,
    ChatRequest,
    ChatResult,
    PageContext,
    SuggestedAction,
)

logger = logging.getLogger("mk.wrapper")

# Default per-request time budget (seconds). Generous enough for multi-step
# agent loops, tight enough to keep the API responsive.
DEFAULT_TIMEOUT_SECONDS = 60.0

EngineFactory = Callable[[], Union[Any, Awaitable[Any]]]


class MKWrapper:
    """Typed, defensive façade over an MK engine instance.

    Args:
        engine: A ready engine (``MKEngine``/``MKEngineV2`` or a compatible
            duck-typed object). May be ``None`` if ``engine_factory`` is given.
        engine_factory: Optional zero-arg callable (sync or async) that builds
            an engine lazily on first use. Lets the web app defer construction.
        timeout: Per-request time budget in seconds.
    """

    def __init__(
        self,
        engine: Optional[Any] = None,
        engine_factory: Optional[EngineFactory] = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._engine = engine
        self._engine_factory = engine_factory
        self._timeout = max(1.0, float(timeout))
        self._factory_lock = asyncio.Lock()

    @property
    def has_engine(self) -> bool:
        """Whether an engine is available (already built or buildable)."""
        return self._engine is not None or self._engine_factory is not None

    async def _get_engine(self) -> Optional[Any]:
        """Return the engine, lazily building it via the factory if needed.

        Never raises: a factory failure is logged and results in ``None`` so
        the caller degrades to a NO_ENGINE result rather than crashing.
        """
        if self._engine is not None:
            return self._engine
        if self._engine_factory is None:
            return None
        async with self._factory_lock:
            if self._engine is not None:
                return self._engine
            try:
                built = self._engine_factory()
                if inspect.isawaitable(built):
                    built = await built
                self._engine = built
            except Exception as exc:  # noqa: BLE001 - defensive boundary
                logger.error("Engine factory failed: %s", exc, exc_info=True)
                self._engine = None
        return self._engine

    # ── Public API ──────────────────────────────────────────────

    def get_suggestions(self, context: Union[PageContext, dict, None]) -> List[SuggestedAction]:
        """Return context-aware suggestions for a page.

        Accepts a :class:`PageContext`, a plain dict, or ``None`` and always
        returns a non-empty list (falling back to generic suggestions).
        """
        ctx = self._coerce_context(context)
        return get_suggestions(ctx)

    def validate_request(self, request: Union[ChatRequest, dict]) -> ChatRequest:
        """Validate/normalize a request, raising for invalid caller input.

        Exposed so streaming callers can reject bad input up front (HTTP 422)
        before opening a stream.

        Raises:
            InputValidationError: If the request is invalid.
        """
        return self._coerce_request(request)

    async def stream_chat(self, request: Union[ChatRequest, dict]) -> "AsyncIterator[str]":
        """Stream a conversational reply chunk-by-chunk.

        Same guarantees as :meth:`chat` for the boundary it can enforce while
        streaming: caller input is validated (raising
        :class:`InputValidationError`), a missing engine degrades to a single
        calm message chunk, and any engine error mid-stream is isolated and
        turned into a trailing fallback notice rather than propagating.

        If the engine does not expose an async ``stream_reply`` generator, this
        falls back to a single-chunk yield of the non-streaming result, so every
        engine works through one code path.

        Yields:
            Reply text chunks in order.
        """
        req = self._coerce_request(request)
        engine = await self._get_engine()

        if engine is None:
            yield user_message_for(AIFailureType.NO_ENGINE)
            return

        stream_fn = getattr(engine, "stream_reply", None)
        if not callable(stream_fn):
            # Engine has no streaming support — degrade to non-streaming chat.
            result = await self.chat(req)
            if result.content:
                yield result.content
            return

        try:
            async for chunk in stream_fn(req.content):
                if chunk:
                    yield chunk
        except Exception as exc:  # noqa: BLE001 - defensive streaming boundary
            logger.error("wrapper.stream_chat failure: %s", exc, exc_info=True)
            yield "\n\n" + user_message_for(AIFailureType.ENGINE_ERROR)

    async def chat(self, request: Union[ChatRequest, dict]) -> ChatResult:
        """Process a conversational request and always return a ``ChatResult``.

        Raises:
            InputValidationError: only for invalid *caller* input. Every AI or
                engine problem is returned as a non-ok result instead.
        """
        req = self._coerce_request(request)
        suggestions = get_suggestions(req.context)
        started = time.perf_counter()

        engine = await self._get_engine()
        if engine is None:
            return self._failure_result(
                AIFailureType.NO_ENGINE,
                detail="No engine wired in and no factory available",
                suggestions=suggestions,
                started=started,
                degraded=True,
            )

        try:
            response = await asyncio.wait_for(
                self._invoke_engine(engine, req.content),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            return self._failure_result(
                AIFailureType.TIMEOUT,
                detail=f"engine did not respond within {self._timeout:.0f}s",
                suggestions=suggestions,
                started=started,
            )
        except Exception as exc:  # noqa: BLE001 - defensive boundary
            return self._handle_engine_exception(exc, suggestions, started)

        return self._build_result_from_response(response, req, suggestions, started)

    # ── Internals ───────────────────────────────────────────────

    async def _invoke_engine(self, engine: Any, content: str) -> Any:
        """Call ``engine.process`` supporting both async and sync engines."""
        if not hasattr(engine, "process"):
            raise AttributeError("engine has no 'process' method")
        result = engine.process(content)
        if inspect.isawaitable(result):
            return await result
        return result

    def _handle_engine_exception(
        self, exc: Exception, suggestions: List[SuggestedAction], started: float
    ) -> ChatResult:
        """Classify an engine exception into a failure result."""
        # Import lazily so the wrapper has no hard dependency on the llm layer.
        failure = AIFailureType.ENGINE_ERROR
        try:
            from mk.llm.base import ProviderError
            from mk.llm.base import TimeoutError as ProviderTimeout

            if isinstance(exc, ProviderTimeout):
                failure = AIFailureType.TIMEOUT
            elif isinstance(exc, ProviderError):
                failure = AIFailureType.PROVIDER_UNAVAILABLE
        except Exception:  # noqa: BLE001 - llm layer optional
            pass

        return self._failure_result(
            failure,
            detail=f"{type(exc).__name__}: {exc}",
            suggestions=suggestions,
            started=started,
            log_exc=exc,
        )

    def _build_result_from_response(
        self,
        response: Any,
        req: ChatRequest,
        suggestions: List[SuggestedAction],
        started: float,
    ) -> ChatResult:
        """Turn a raw engine response into a screened, typed ``ChatResult``."""
        text = self._extract_text(response)

        failure = analyze_output(text, expect_json=req.expect_json)
        if failure is not None:
            return self._failure_result(
                failure,
                detail=f"post-response check flagged {failure.value}",
                suggestions=suggestions,
                started=started,
                raw_preview=(text or "")[:200],
            )

        elapsed_ms = (time.perf_counter() - started) * 1000.0
        provider = getattr(response, "provider_used", None)
        was_direct = bool(getattr(response, "was_direct_command", False))
        # A reply produced without any LLM provider is a degraded (but valid) mode.
        degraded = provider is None and not was_direct

        metrics.increment("mk_wrapper_chat_total", labels={"outcome": "ok"})
        metrics.observe("mk_wrapper_chat_seconds", elapsed_ms / 1000.0)
        logger.info(
            "wrapper.chat ok provider=%s direct=%s tokens=%s elapsed_ms=%.1f",
            provider,
            was_direct,
            getattr(response, "tokens_used", 0),
            elapsed_ms,
        )

        assert text is not None  # analyze_output guarantees non-empty here
        return ChatResult(
            ok=True,
            content=text,
            message=text,
            actions=[],
            suggestions=suggestions,
            degraded=degraded,
            provider=provider,
            tokens_used=int(getattr(response, "tokens_used", 0) or 0),
            cost=float(getattr(response, "cost", 0.0) or 0.0),
            was_direct_command=was_direct,
            elapsed_ms=elapsed_ms,
        )

    def _failure_result(
        self,
        failure: AIFailureType,
        detail: str,
        suggestions: List[SuggestedAction],
        started: float,
        degraded: bool = False,
        raw_preview: str = "",
        log_exc: Optional[Exception] = None,
    ) -> ChatResult:
        """Build, log, and meter a non-ok ``ChatResult`` for a failure."""
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        message = user_message_for(failure)

        metrics.increment("mk_wrapper_chat_total", labels={"outcome": failure.value})
        metrics.increment("mk_wrapper_ai_failures_total", labels={"type": failure.value})

        # NO_ENGINE / degraded modes are expected states, not errors.
        if failure in (AIFailureType.NO_ENGINE,):
            logger.info("wrapper.chat degraded failure=%s detail=%s", failure.value, detail)
        else:
            logger.error(
                "wrapper.chat failure=%s detail=%s preview=%s",
                failure.value,
                detail,
                raw_preview or "",
                exc_info=log_exc if log_exc is not None else False,
            )

        return ChatResult(
            ok=False,
            content=message,
            message=message,
            failure=AIFailureInfo(
                failure_type=failure,
                detail=detail,
                retryable=is_retryable(failure),
            ),
            suggestions=suggestions,
            degraded=degraded or failure == AIFailureType.NO_ENGINE,
            elapsed_ms=elapsed_ms,
        )

    @staticmethod
    def _extract_text(response: Any) -> Optional[str]:
        """Pull the reply text out of whatever the engine returned."""
        if response is None:
            return None
        if isinstance(response, str):
            return response
        final = getattr(response, "final_response", None)
        if isinstance(final, str):
            return final
        if final is not None:
            return str(final)
        return None

    @staticmethod
    def _coerce_request(request: Union[ChatRequest, dict]) -> ChatRequest:
        """Validate/normalize an incoming request into a ``ChatRequest``."""
        if isinstance(request, ChatRequest):
            return request
        try:
            return ChatRequest.model_validate(request)
        except Exception as exc:  # pydantic ValidationError et al.
            raise InputValidationError(_first_validation_message(exc)) from exc

    @staticmethod
    def _coerce_context(context: Union[PageContext, dict, None]) -> PageContext:
        """Normalize a context input into a ``PageContext`` (never raises)."""
        if isinstance(context, PageContext):
            return context
        if not context:
            return PageContext()
        try:
            return PageContext.model_validate(context)
        except Exception:  # noqa: BLE001 - suggestions must never fail
            return PageContext()


def _first_validation_message(exc: Exception) -> str:
    """Produce a concise, user-facing validation message from an error."""
    errors = getattr(exc, "errors", None)
    if callable(errors):
        try:
            items = errors()
            if items:
                first = items[0]
                loc = ".".join(str(p) for p in first.get("loc", ())) or "input"
                msg = first.get("msg", "invalid value")
                return f"{loc}: {msg}"
        except Exception:  # noqa: BLE001
            pass
    return str(exc) or "invalid request"
