"""Unit tests for AI-failure detectors (pure functions)."""

from __future__ import annotations

import pytest

from mk.wrapper.errors import AIFailureType
from mk.wrapper.failures import (
    analyze_output,
    detect_degenerate_output,
    detect_empty_output,
    validate_structured_output,
)


@pytest.mark.parametrize("text", [None, "", "   ", "\n\t  \n"])
def test_detect_empty_output_true(text):
    assert detect_empty_output(text) is True


@pytest.mark.parametrize("text", ["hello", "  ok  ", "a"])
def test_detect_empty_output_false(text):
    assert detect_empty_output(text) is False


def test_detect_degenerate_repeated_token():
    text = "spam " * 50
    assert detect_degenerate_output(text) is True


def test_detect_degenerate_repeated_line():
    text = "\n".join(["the same line"] * 20)
    assert detect_degenerate_output(text) is True


def test_detect_degenerate_single_char_run():
    assert detect_degenerate_output("a" * 100) is True


def test_detect_degenerate_normal_prose_is_fine():
    text = (
        "The storage pool is healthy and there are no active alerts. "
        "Two containers are running and the network looks nominal."
    )
    assert detect_degenerate_output(text) is False


def test_detect_degenerate_short_text_ignored():
    # Below the minimum length threshold, never flagged.
    assert detect_degenerate_output("hi hi hi") is False


def test_validate_structured_output_valid_object():
    ok, parsed, detail = validate_structured_output('{"action": "restart", "target": "plex"}')
    assert ok is True
    assert parsed == {"action": "restart", "target": "plex"}
    assert detail == ""


def test_validate_structured_output_fenced_json():
    ok, parsed, _ = validate_structured_output('```json\n{"a": 1}\n```')
    assert ok is True
    assert parsed == {"a": 1}


def test_validate_structured_output_embedded_json():
    ok, parsed, _ = validate_structured_output('Sure! Here it is: {"a": 1} hope that helps')
    assert ok is True
    assert parsed == {"a": 1}


def test_validate_structured_output_not_json():
    ok, parsed, detail = validate_structured_output("I think you should restart it.")
    assert ok is False
    assert parsed is None
    assert detail


def test_validate_structured_output_broken_json():
    ok, parsed, detail = validate_structured_output('{"a": 1, "b": }')
    assert ok is False
    assert "valid JSON" in detail


def test_analyze_output_healthy_returns_none():
    assert analyze_output("Everything is fine, no issues found.") is None


def test_analyze_output_empty():
    assert analyze_output("   ") is AIFailureType.EMPTY_OUTPUT


def test_analyze_output_degenerate():
    assert analyze_output("loop " * 60) is AIFailureType.MALFORMED_OUTPUT


def test_analyze_output_schema_invalid_when_json_expected():
    assert analyze_output("not json", expect_json=True) is AIFailureType.SCHEMA_INVALID


def test_analyze_output_valid_json_when_expected():
    assert analyze_output('{"ok": true}', expect_json=True) is None
