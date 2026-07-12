"""Detectors for AI failure signals in engine output.

These are pure, side-effect-free functions so they are trivial to unit test
and reason about. The wrapper runs the output through :func:`analyze_output`
after a successful engine call to catch the failures that *don't* raise —
empty replies, degenerate/looping text, and (when structured output is
expected) unparseable or schema-invalid JSON.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from mk.wrapper.errors import AIFailureType

# Minimum length below which we don't bother with repetition analysis.
_MIN_LEN_FOR_REPETITION = 40

# If a single token makes up more than this fraction of a long response,
# treat it as degenerate/looping output.
_MAX_TOKEN_FRACTION = 0.6

# If the most common short line repeats more than this many times, likewise.
_MAX_LINE_REPEATS = 8


def detect_empty_output(text: Optional[str]) -> bool:
    """Return True if the text is missing or effectively empty."""
    return not text or not text.strip()


def detect_degenerate_output(text: str) -> bool:
    """Heuristically detect runaway repetition / looping output.

    Models that get stuck often emit the same token or line hundreds of times.
    We flag output where a single whitespace-delimited token dominates, or a
    single short line repeats many times. Kept conservative to avoid false
    positives on legitimately repetitive content (tables, lists).
    """
    stripped = text.strip()
    if len(stripped) < _MIN_LEN_FOR_REPETITION:
        return False

    tokens = stripped.split()
    if len(tokens) >= 12:
        counts: dict[str, int] = {}
        for tok in tokens:
            counts[tok] = counts.get(tok, 0) + 1
        most_common = max(counts.values())
        if most_common / len(tokens) > _MAX_TOKEN_FRACTION:
            return True

    # Repeated identical non-trivial lines.
    lines = [ln.strip() for ln in stripped.splitlines() if ln.strip()]
    if len(lines) >= _MAX_LINE_REPEATS:
        line_counts: dict[str, int] = {}
        for ln in lines:
            line_counts[ln] = line_counts.get(ln, 0) + 1
        if max(line_counts.values()) > _MAX_LINE_REPEATS:
            return True

    # A single character repeated for a long stretch (e.g. "aaaaaa...").
    if re.search(r"(.)\1{40,}", stripped):
        return True

    return False


def _extract_json(text: str) -> Optional[str]:
    """Best-effort extraction of a JSON object/array from a text blob.

    Handles the common case of a model wrapping JSON in prose or ```json
    fences. Returns the candidate JSON substring, or None if none is found.
    """
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        return fence.group(1).strip()
    # Fall back to the first {...} or [...] span.
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = text.find(open_ch)
        end = text.rfind(close_ch)
        if start != -1 and end != -1 and end > start:
            return text[start : end + 1].strip()
    return None


def validate_structured_output(text: str) -> tuple[bool, Optional[Any], str]:
    """Parse and validate output that is expected to be JSON.

    Returns a ``(ok, parsed, detail)`` tuple. ``ok`` is False when the output
    cannot be parsed as JSON — a strong signal the model hallucinated the
    requested structure rather than following it.
    """
    if detect_empty_output(text):
        return False, None, "structured output was empty"

    candidate = _extract_json(text)
    if candidate is None:
        return False, None, "no JSON object or array found in output"

    try:
        parsed = json.loads(candidate)
    except (json.JSONDecodeError, ValueError) as exc:
        return False, None, f"output is not valid JSON: {exc}"

    if not isinstance(parsed, (dict, list)):
        return False, None, "parsed JSON is not an object or array"

    return True, parsed, ""


def analyze_output(text: Optional[str], expect_json: bool = False) -> Optional[AIFailureType]:
    """Classify a successful engine reply for latent AI failures.

    Returns the :class:`AIFailureType` if a problem is detected, or ``None``
    when the output looks healthy. This runs *after* the engine returns
    without raising, catching the failure modes that don't surface as
    exceptions.
    """
    if detect_empty_output(text):
        return AIFailureType.EMPTY_OUTPUT

    assert text is not None  # narrowed by detect_empty_output

    if expect_json:
        ok, _parsed, _detail = validate_structured_output(text)
        if not ok:
            return AIFailureType.SCHEMA_INVALID

    if detect_degenerate_output(text):
        return AIFailureType.MALFORMED_OUTPUT

    return None
