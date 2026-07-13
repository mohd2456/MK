"""Detection of AI failures in engine output.

The wrapper cannot fully "know" when a model hallucinates, but it can catch
the common, mechanically-detectable failure modes and refuse to pass them off
as trustworthy answers:

- **Empty output** — the model returned nothing usable.
- **Malformed / degenerate output** — runaway token repetition, which is a
  classic sign of a stuck decode loop or a low-quality hallucination.
- **Schema-invalid output** — when the caller asked for structured JSON but
  the text does not parse, that is treated as a likely hallucination.

Each detector returns an :class:`~mk.wrapper.models.AIFailureInfo` describing
the problem, or ``None`` when the output looks trustworthy. Detection is pure
and side-effect free so it is easy to unit test.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from mk.wrapper.errors import AIFailureType
from mk.wrapper.models import AIFailureInfo

# A response longer than this many characters is checked for runaway
# repetition. Short strings can legitimately repeat (e.g. "ok ok").
_REPETITION_MIN_LENGTH = 200

# If a single line makes up more than this fraction of a multi-line response,
# treat it as a degenerate loop.
_REPETITION_LINE_RATIO = 0.6

# If the most common token accounts for more than this fraction of all tokens
# in a long response, treat it as degenerate.
_REPETITION_TOKEN_RATIO = 0.5

_USER_MSG_EMPTY = "I wasn't able to produce a response. Please try rephrasing your request."
_USER_MSG_MALFORMED = (
    "I produced an unreliable response and stopped it to avoid giving you bad "
    "information. Please try again."
)
_USER_MSG_SCHEMA = (
    "I couldn't produce a valid structured answer for that request. Please try again."
)


def _looks_degenerate(text: str) -> bool:
    """Heuristic check for runaway repetition in a long response."""
    if len(text) < _REPETITION_MIN_LENGTH:
        return False

    # Line-level repetition (e.g. the same sentence over and over).
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) >= 4:
        most_common = max(set(lines), key=lines.count)
        if lines.count(most_common) / len(lines) > _REPETITION_LINE_RATIO:
            return True

    # Token-level repetition (e.g. "na na na na ...").
    tokens = re.findall(r"\S+", text)
    if len(tokens) >= 20:
        most_common = max(set(tokens), key=tokens.count)
        if tokens.count(most_common) / len(tokens) > _REPETITION_TOKEN_RATIO:
            return True

    return False


def detect_output_failure(text: str, *, expects_json: bool = False) -> Optional[AIFailureInfo]:
    """Inspect engine output text for detectable failure modes.

    Args:
        text: The final response text from the engine.
        expects_json: If True, the text must parse as JSON or it is flagged
            as ``SCHEMA_INVALID``.

    Returns:
        An :class:`AIFailureInfo` if a failure is detected, else ``None``.
    """
    if text is None or not str(text).strip():
        return AIFailureInfo(
            type=AIFailureType.EMPTY_OUTPUT,
            message=_USER_MSG_EMPTY,
            detail="Engine returned empty or whitespace-only output.",
            retryable=True,
        )

    text = str(text)

    if _looks_degenerate(text):
        return AIFailureInfo(
            type=AIFailureType.MALFORMED_OUTPUT,
            message=_USER_MSG_MALFORMED,
            detail="Output flagged as degenerate (excessive repetition).",
            retryable=True,
        )

    if expects_json:
        candidate = _extract_json_candidate(text)
        try:
            json.loads(candidate)
        except (ValueError, TypeError):
            return AIFailureInfo(
                type=AIFailureType.SCHEMA_INVALID,
                message=_USER_MSG_SCHEMA,
                detail="Structured JSON output requested but response did not parse.",
                retryable=True,
            )

    return None


def _extract_json_candidate(text: str) -> str:
    """Best-effort extraction of a JSON payload from a text response.

    Models often wrap JSON in prose or code fences. This pulls out the first
    balanced-looking object/array so the parse check is fair.
    """
    stripped = text.strip()

    # Strip markdown code fences if present.
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z]*\n?", "", stripped)
        stripped = re.sub(r"\n?```$", "", stripped).strip()

    # If it already looks like JSON, return as-is.
    if stripped[:1] in "{[":
        return stripped

    # Otherwise, grab the span between the first opening and last closing brace.
    start = min(
        (i for i in (stripped.find("{"), stripped.find("[")) if i != -1),
        default=-1,
    )
    end = max(stripped.rfind("}"), stripped.rfind("]"))
    if start != -1 and end != -1 and end > start:
        return stripped[start : end + 1]

    return stripped
