"""Unit tests for the MK agent loop."""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from mk.core.agent_loop import AgentLoop
from mk.core.context import ContextBuilder
from mk.core.models import Conversation, Role
from tests.conftest import MockLLMProvider


@pytest.mark.asyncio
async def test_simple_response() -> None:
    """Agent loop returns final response when LLM gives no tool calls."""
    provider = MockLLMProvider([
        {"content": "Hello! I'm MK.", "tokens_used": 20, "cost": 0.001, "tool_calls": []}
    ])
    context_builder = ContextBuilder(token_budget=4000)
    loop = AgentLoop(
        llm_provider=provider,
        context_builder=context_builder,
        max_iterations=5,
    )

    response = await loop.run("Hello")

    assert response.final_response == "Hello! I'm MK."
    assert response.tokens_used == 20
    assert response.cost == 0.001
    assert response.provider_used == "mock-provider"
    assert len(response.steps) == 1
    assert response.steps[0].thought == "Hello! I'm MK."
    assert response.steps[0].action is None


@pytest.mark.asyncio
async def test_tool_call_and_response() -> None:
    """Agent loop executes tool calls and then gets final response."""
    provider = MockLLMProvider([
        # First call: LLM wants to use a tool
        {
            "content": "Let me check that.",
            "tokens_used": 30,
            "cost": 0.001,
            "tool_calls": [{"name": "check_status", "args": {"target": "plex"}}],
        },
        # Second call: LLM gives final answer after seeing tool result
        {
            "content": "Plex is running fine.",
            "tokens_used": 20,
            "cost": 0.001,
            "tool_calls": [],
        },
    ])

    async def mock_executor(name: str, args: Dict[str, Any]) -> str:
        return "Service 'plex' is running (uptime: 3 days)"

    context_builder = ContextBuilder(token_budget=4000)
    loop = AgentLoop(
        llm_provider=provider,
        context_builder=context_builder,
        tool_executor=mock_executor,
        max_iterations=5,
    )

    response = await loop.run("Is plex running?")

    assert response.final_response == "Plex is running fine."
    assert response.tokens_used == 50
    assert len(response.steps) == 2
    # First step should have the tool call
    assert response.steps[0].action is not None
    assert response.steps[0].action.name == "check_status"
    assert response.steps[0].action.result == "Service 'plex' is running (uptime: 3 days)"
    assert response.steps[0].action.executed is True


@pytest.mark.asyncio
async def test_tool_error_handling() -> None:
    """Agent loop handles tool execution errors gracefully."""
    provider = MockLLMProvider([
        {
            "content": "Let me restart that.",
            "tokens_used": 25,
            "cost": 0.001,
            "tool_calls": [{"name": "restart_service", "args": {"target": "sonarr"}}],
        },
        {
            "content": "The restart failed due to a connection error.",
            "tokens_used": 30,
            "cost": 0.001,
            "tool_calls": [],
        },
    ])

    async def failing_executor(name: str, args: Dict[str, Any]) -> str:
        raise ConnectionError("Cannot connect to host")

    context_builder = ContextBuilder(token_budget=4000)
    loop = AgentLoop(
        llm_provider=provider,
        context_builder=context_builder,
        tool_executor=failing_executor,
        max_iterations=5,
    )

    response = await loop.run("Restart sonarr")

    assert response.final_response == "The restart failed due to a connection error."
    assert response.steps[0].action is not None
    assert response.steps[0].action.error == "Cannot connect to host"


@pytest.mark.asyncio
async def test_max_iterations_reached() -> None:
    """Agent loop stops after max iterations."""
    # Provider always returns tool calls, never a final answer
    responses = [
        {
            "content": "Still working...",
            "tokens_used": 10,
            "cost": 0.0,
            "tool_calls": [{"name": "check", "args": {}}],
        }
    ] * 5

    async def mock_executor(name: str, args: Dict[str, Any]) -> str:
        return "done"

    provider = MockLLMProvider(responses)
    context_builder = ContextBuilder(token_budget=4000)
    loop = AgentLoop(
        llm_provider=provider,
        context_builder=context_builder,
        tool_executor=mock_executor,
        max_iterations=3,
    )

    response = await loop.run("Do something complex")

    # Should have stopped at 3 iterations
    assert "iteration limit" in response.final_response.lower()
    assert response.tokens_used == 30  # 10 per iteration * 3


@pytest.mark.asyncio
async def test_conversation_context_passed() -> None:
    """Agent loop passes conversation context to the LLM."""
    provider = MockLLMProvider([
        {"content": "Got it.", "tokens_used": 10, "cost": 0.0, "tool_calls": []}
    ])

    context_builder = ContextBuilder(token_budget=4000)
    loop = AgentLoop(
        llm_provider=provider,
        context_builder=context_builder,
        max_iterations=5,
    )

    conversation = Conversation()
    conversation.add_message(Role.USER, "My name is Alex")
    conversation.add_message(Role.ASSISTANT, "Nice to meet you, Alex!")

    response = await loop.run("What's my name?", conversation=conversation)

    assert response.final_response == "Got it."
    # Verify the provider received messages including conversation history
    assert len(provider.calls) == 1
    messages = provider.calls[0]
    # Should have system + conversation history + user input
    assert len(messages) >= 3
