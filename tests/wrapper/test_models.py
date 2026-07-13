"""Tests for wrapper input/output models and validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mk.wrapper.models import (
    MAX_CONTENT_LENGTH,
    ActionKind,
    ChatRequest,
    PageContext,
    SuggestedAction,
)


class TestChatRequestValidation:
    def test_valid_content_is_stripped(self):
        req = ChatRequest(content="  hello world  ")
        assert req.content == "hello world"

    def test_empty_content_rejected(self):
        with pytest.raises(ValidationError):
            ChatRequest(content="   ")

    def test_oversized_content_rejected(self):
        with pytest.raises(ValidationError):
            ChatRequest(content="x" * (MAX_CONTENT_LENGTH + 1))

    def test_max_length_content_accepted(self):
        req = ChatRequest(content="x" * MAX_CONTENT_LENGTH)
        assert len(req.content) == MAX_CONTENT_LENGTH

    def test_oversized_session_id_rejected(self):
        with pytest.raises(ValidationError):
            ChatRequest(content="hi", session_id="s" * 200)

    def test_defaults(self):
        req = ChatRequest(content="hi")
        assert req.context.path == "/"
        assert req.expects_json is False
        assert req.session_id is None


class TestPageContextNormalization:
    def test_from_none(self):
        ctx = PageContext.from_raw(None)
        assert ctx.path == "/"

    def test_from_string(self):
        ctx = PageContext.from_raw("storage")
        assert ctx.path == "/storage"

    def test_leading_slash_preserved(self):
        assert PageContext.from_raw("/network").path == "/network"

    def test_trailing_slash_collapsed(self):
        assert PageContext.from_raw("/network/").path == "/network"

    def test_query_and_fragment_stripped(self):
        assert PageContext.from_raw("/storage?tab=pools#top").path == "/storage"

    def test_from_dict_with_pathname_alias(self):
        ctx = PageContext.from_raw({"pathname": "/apps", "title": "Apps"})
        assert ctx.path == "/apps"
        assert ctx.label == "Apps"

    def test_from_dict_extra_keys_become_metadata(self):
        ctx = PageContext.from_raw({"path": "/storage", "selectedPool": "tank"})
        assert ctx.metadata.get("selectedPool") == "tank"

    def test_garbage_degrades_to_root(self):
        assert PageContext.from_raw(12345).path == "/"

    def test_existing_context_passthrough(self):
        original = PageContext(path="/media")
        assert PageContext.from_raw(original) is original


class TestSuggestedAction:
    def test_default_kind(self):
        action = SuggestedAction(id="x", label="X", prompt="do x")
        assert action.kind == ActionKind.SUGGESTION
