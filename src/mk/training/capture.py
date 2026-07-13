"""Capture real conversations for local-brain retraining.

MK's local brain improves by learning from real use. When capture is enabled,
successful user/assistant exchanges are appended to a JSONL file in the exact
format the fine-tuning pipeline consumes
(``{"messages": [{"role": ..., "content": ...}, ...]}``), so they can be folded
back into the training set with ``training/scripts/ingest_captured.py``.

Capture is **opt-in** (privacy-first): it is off unless enabled explicitly or
via the ``MK_CAPTURE_CONVERSATIONS`` environment variable. It never raises —
capturing training data must never disrupt a live reply.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

_TRUTHY = {"1", "true", "yes", "on"}

# A concise MK identity used as the system message for captured examples when
# the caller does not supply one. The retraining ingest step can normalize this
# to the canonical training system prompt.
DEFAULT_SYSTEM_PROMPT = (
    "You are MK, a personal AI operating system that manages a homelab. "
    "Parse intent quickly, pick the right tool, and keep replies short and useful."
)


class ConversationCapture:
    """Append accepted conversations to a training-format JSONL file.

    Args:
        path: Output JSONL path. Falls back to ``MK_CAPTURE_PATH`` then
            ``~/.mk/training/captured.jsonl``.
        enabled: Whether capture is active. Defaults to the truthiness of
            ``MK_CAPTURE_CONVERSATIONS``.
        system_prompt: System message stored with each example when the caller
            doesn't provide one.
    """

    def __init__(
        self,
        path: Optional[str] = None,
        enabled: Optional[bool] = None,
        system_prompt: Optional[str] = None,
    ) -> None:
        if path:
            self._path = Path(path)
        else:
            env_path = os.environ.get("MK_CAPTURE_PATH")
            self._path = (
                Path(env_path) if env_path else Path.home() / ".mk" / "training" / "captured.jsonl"
            )
        if enabled is None:
            enabled = os.environ.get("MK_CAPTURE_CONVERSATIONS", "").strip().lower() in _TRUTHY
        self._enabled = bool(enabled)
        self._system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT

    @property
    def enabled(self) -> bool:
        """Whether capture is active."""
        return self._enabled

    @property
    def path(self) -> Path:
        """The JSONL output path."""
        return self._path

    def capture(
        self,
        user_content: str,
        assistant_content: str,
        *,
        system_prompt: Optional[str] = None,
        ok: bool = True,
    ) -> bool:
        """Record one exchange as a training example. Returns True if written.

        No-ops (returning False) when disabled, when ``ok`` is False, or when
        either side is empty — we only want clean, successful exchanges as
        training signal. Never raises.
        """
        if not self._enabled or not ok:
            return False
        user = (user_content or "").strip()
        assistant = (assistant_content or "").strip()
        if not user or not assistant:
            return False

        record = {
            "messages": [
                {"role": "system", "content": system_prompt or self._system_prompt},
                {"role": "user", "content": user},
                {"role": "assistant", "content": assistant},
            ]
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            return False

        # Observability: count captured training examples.
        try:
            from mk.metrics import metrics

            metrics.increment("mk_training_captured_total")
        except Exception:  # noqa: BLE001 - metrics must never break capture
            pass
        return True

    def count(self) -> int:
        """Return the number of captured examples on disk (0 if none/error)."""
        if not self._path.exists():
            return 0
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                return sum(1 for line in f if line.strip())
        except OSError:
            return 0
