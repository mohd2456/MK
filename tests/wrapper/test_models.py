"""Unit tests for wrapper Pydantic models and validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mk.wrapper.errors import AIFailureType
from mk.wrapper.models import (
    MAX_CONTENT_LENGTH,
    AIFailureInfo,
    ChatRequest,
    ChatResult,
    PageContext,
)


def test_page_context_normalizes_leading_slash():
    assert PageContext(page="dashboard").page == "/dashboard"


def test_page_context_strips_query_and_fragment():
    assert PageContext(page="/apps?tab=1#top").page == "/apps"


def test_page_context_strips_trailing_slash():
    assert PageContext(page="/storage/").page == "/storage"


def test_page_context_empty_defaults_to_root():
    assert PageContext(page="").page == "/"
    assert PageContext(page=None).page == "/"


def test_chat_request_strips_content():
    req = ChatRequest(content="  hello  ")
    assert req.content == "hello"


def test_chat_request_rejects_empty_content():
    with pytest.raises(ValidationError):
        ChatRequest(content="   ")


def test_chat_request_rejects_oversized_content():
    with pytest.raises(ValidationError):
        ChatRequest(content="x" * (MAX_CONTENT_LENGTH + 1))


def test_chat_request_blank_session_id_becomes_none():
    assert ChatRequest(content="hi", session_id="  ").session_id is None


def test_chat_request_context_from_dict():
    req = ChatRequest(content="hi", context={"page": "network"})
    assert isinstance(req.context, PageContext)
    assert req.context.page == "/network"


def test_chat_result_failure_type_property():
    result = ChatResult(
        ok=False,
        content="oops",
        failure=AIFailureInfo(failure_type=AIFailureType.TIMEOUT, detail="x", retryable=True),
    )
    assert result.failure_type == "timeout"


def test_chat_result_failure_type_none_when_ok():
    assert ChatResult(ok=True, content="hi").failure_type is None
