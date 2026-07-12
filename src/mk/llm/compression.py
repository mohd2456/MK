"""Context compression via Headroom.

Wraps the optional `headroom-ai` library (https://github.com/chopratejas/headroom)
to shrink prompts before they reach an LLM provider. Headroom is content-aware:
it crushes large JSON tool outputs, logs, and code while preserving meaning,
typically cutting 40-90% of tokens on data-heavy turns.

Design principles (mirrors the rest of the MK LLM layer):

* **Optional & lazy** — `headroom` is imported on first use. If it isn't
  installed, this becomes a transparent no-op; nothing breaks.
* **Opt-in** — disabled unless explicitly enabled (``MK_COMPRESSION=1`` or the
  ``enabled`` constructor flag), so default behavior is unchanged.
* **Never fails a request** — any error during compression is caught, logged,
  and the original messages are returned untouched.
* **Observable** — token savings and outcomes are logged and metered.

Install with:  ``uv sync --extra compression``  (or ``pip install headroom-ai``).
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional, Tuple

from pydantic import BaseModel, Field

from mk.llm.models import LLMMessage
from mk.observability import metrics

logger = logging.getLogger("mk.llm.compression")

# Env var used to enable compression without code changes.
_ENABLE_ENV = "MK_COMPRESSION"
_MODEL_ENV = "MK_COMPRESSION_MODEL"
_TRUTHY = {"1", "true", "yes", "on"}


class CompressionStats(BaseModel):
    """Outcome of a compression attempt.

    ``applied`` is True only when Headroom actually ran and produced a usable
    result. On any skip or failure the original messages are returned and
    ``applied`` is False (with ``error`` set when relevant).
    """

    applied: bool = Field(default=False, description="Whether compression was applied")
    available: bool = Field(default=False, description="Whether headroom is importable")
    tokens_before: int = Field(default=0)
    tokens_after: int = Field(default=0)
    tokens_saved: int = Field(default=0)
    compression_ratio: float = Field(
        default=1.0, description="tokens_after / tokens_before (1.0 = no change)"
    )
    transforms_applied: List[str] = Field(default_factory=list)
    error: Optional[str] = Field(default=None, description="Error detail if compression failed")


class ContextCompressor:
    """Optional Headroom-backed compressor for LLM message lists.

    Args:
        enabled: Master switch. When False, ``compress_messages`` is a no-op.
        model: Model name passed to Headroom (affects tokenizer/limits only).
            When None, Headroom's own default is used.
    """

    def __init__(self, enabled: bool = False, model: Optional[str] = None) -> None:
        self._enabled = enabled
        self._model = model
        self._compress = None  # resolved lazily
        self._available: Optional[bool] = None

    @classmethod
    def from_env(cls) -> "ContextCompressor":
        """Build a compressor from environment variables (disabled by default)."""
        enabled = os.environ.get(_ENABLE_ENV, "").strip().lower() in _TRUTHY
        model = os.environ.get(_MODEL_ENV) or None
        return cls(enabled=enabled, model=model)

    @property
    def enabled(self) -> bool:
        """Whether compression is switched on (independent of availability)."""
        return self._enabled

    @property
    def available(self) -> bool:
        """Whether the ``headroom`` package can be imported (cached)."""
        if self._available is None:
            try:
                from headroom import compress  # type: ignore

                self._compress = compress
                self._available = True
            except Exception as exc:  # noqa: BLE001 - optional dependency
                logger.info("headroom not available; compression disabled: %s", exc)
                self._available = False
        return self._available

    @property
    def active(self) -> bool:
        """True when compression is both enabled and available."""
        return self._enabled and self.available

    def compress_messages(
        self, messages: List[LLMMessage], model: Optional[str] = None
    ) -> Tuple[List[LLMMessage], CompressionStats]:
        """Compress a message list, returning ``(messages, stats)``.

        Always safe: returns the original messages unchanged if compression is
        disabled, unavailable, or errors out. The returned list preserves
        message roles and order; only textual content is compressed.
        """
        if not messages or not self._enabled:
            return messages, CompressionStats(applied=False, available=self._available or False)

        if not self.available:
            return messages, CompressionStats(applied=False, available=False)

        try:
            payload = [{"role": m.role.value, "content": m.content} for m in messages]
            chosen_model = model or self._model
            result = (
                self._compress(payload, model=chosen_model)
                if chosen_model
                else self._compress(payload)
            )

            rebuilt = self._rebuild(messages, getattr(result, "messages", None))
            if rebuilt is None:
                # Structural mismatch — don't risk corrupting the conversation.
                logger.warning("compression output shape mismatch; skipping")
                metrics.increment("mk_compression_total", labels={"outcome": "skipped"})
                return messages, CompressionStats(applied=False, available=True)

            before = int(getattr(result, "tokens_before", 0) or 0)
            after = int(getattr(result, "tokens_after", 0) or 0)
            saved = int(getattr(result, "tokens_saved", max(0, before - after)) or 0)
            ratio = float(getattr(result, "compression_ratio", 1.0) or 1.0)
            transforms = list(getattr(result, "transforms_applied", []) or [])

            metrics.increment("mk_compression_total", labels={"outcome": "applied"})
            metrics.observe("mk_compression_tokens_saved", float(saved))
            logger.info(
                "compression applied: %d -> %d tokens (saved %d, ratio %.2f) transforms=%s",
                before,
                after,
                saved,
                ratio,
                transforms,
            )

            return rebuilt, CompressionStats(
                applied=True,
                available=True,
                tokens_before=before,
                tokens_after=after,
                tokens_saved=saved,
                compression_ratio=ratio,
                transforms_applied=transforms,
            )
        except Exception as exc:  # noqa: BLE001 - never break a request
            logger.warning("compression failed, using original messages: %s", exc)
            metrics.increment("mk_compression_total", labels={"outcome": "error"})
            return messages, CompressionStats(applied=False, available=True, error=str(exc))

    @staticmethod
    def _rebuild(
        original: List[LLMMessage], compressed: Optional[List[dict]]
    ) -> Optional[List[LLMMessage]]:
        """Rebuild typed messages from Headroom output, preserving roles.

        Returns None if the shapes don't line up 1:1, signalling the caller to
        keep the original messages rather than risk a malformed conversation.
        """
        if not isinstance(compressed, list) or len(compressed) != len(original):
            return None
        rebuilt: List[LLMMessage] = []
        for orig, comp in zip(original, compressed):
            content = comp.get("content") if isinstance(comp, dict) else None
            rebuilt.append(
                LLMMessage(
                    role=orig.role,
                    content=str(content) if content is not None else orig.content,
                    name=orig.name,
                    tool_call_id=orig.tool_call_id,
                )
            )
        return rebuilt
