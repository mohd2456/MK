"""Tests for AI-failure detection heuristics."""

from __future__ import annotations

from mk.wrapper.errors import AIFailureType
from mk.wrapper.failures import detect_output_failure


class TestEmptyOutput:
    def test_empty_string(self):
        failure = detect_output_failure("")
        assert failure is not None
        assert failure.type == AIFailureType.EMPTY_OUTPUT

    def test_whitespace_only(self):
        failure = detect_output_failure("   \n\t  ")
        assert failure is not None
        assert failure.type == AIFailureType.EMPTY_OUTPUT

    def test_none(self):
        failure = detect_output_failure(None)  # type: ignore[arg-type]
        assert failure is not None
        assert failure.type == AIFailureType.EMPTY_OUTPUT


class TestHealthyOutput:
    def test_normal_text_passes(self):
        assert detect_output_failure("Your pool 'tank' is healthy and online.") is None

    def test_short_repetition_is_fine(self):
        # Short strings can legitimately repeat.
        assert detect_output_failure("ok ok ok") is None


class TestDegenerateOutput:
    def test_line_repetition_flagged(self):
        text = "\n".join(["The system is fine."] * 40)
        failure = detect_output_failure(text)
        assert failure is not None
        assert failure.type == AIFailureType.MALFORMED_OUTPUT

    def test_token_repetition_flagged(self):
        text = "spam " * 200
        failure = detect_output_failure(text)
        assert failure is not None
        assert failure.type == AIFailureType.MALFORMED_OUTPUT

    def test_long_varied_text_passes(self):
        text = " ".join(f"word{i}" for i in range(300))
        assert detect_output_failure(text) is None


class TestSchemaValidation:
    def test_valid_json_object_passes(self):
        assert detect_output_failure('{"status": "ok"}', expects_json=True) is None

    def test_valid_json_in_code_fence_passes(self):
        text = '```json\n{"status": "ok"}\n```'
        assert detect_output_failure(text, expects_json=True) is None

    def test_json_embedded_in_prose_passes(self):
        text = 'Here is the result: {"status": "ok"} — hope that helps!'
        assert detect_output_failure(text, expects_json=True) is None

    def test_invalid_json_flagged(self):
        failure = detect_output_failure("this is not json at all", expects_json=True)
        assert failure is not None
        assert failure.type == AIFailureType.SCHEMA_INVALID

    def test_prose_not_checked_when_json_not_expected(self):
        assert detect_output_failure("this is not json at all") is None
