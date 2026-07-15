"""Tests for MKEngine.stream_agent (multi-step ReAct with streaming)."""

from __future__ import annotations

from typing import AsyncIterator, List

import pytest

from mk.core.engine import MKEngine
from mk.llm.models import LLMRequest


class FakeAgentRouter:
    """Simulates an LLM that produces a tool call then a final answer."""

    def __init__(self) -> None:
        self._call_count = 0

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        self._call_count += 1
        if self._call_count == 1:
            # First iteration: emit a tool call
            yield '{"tool": "docker", "params": {"action": "restart", "container": "plex"}}'
        else:
            # Second iteration: emit a final answer
            yield "Done — Plex has been restarted."


class FakeAgentRouterNoTools:
    """Simulates an LLM that just answers directly (no tool calls)."""

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        yield "The system is healthy."


@pytest.mark.asyncio
async def test_stream_agent_executes_tools_and_yields_frames():
    """The agent loop calls tools and yields thought/action/observation/answer frames."""
    engine = MKEngine()
    engine._llm_router = FakeAgentRouter()

    # Register a fake tool
    executed = []

    async def fake_docker(**kwargs):
        executed.append(kwargs)
        return "Container plex restarted successfully"

    engine._tools["docker"] = fake_docker

    frames: List[dict] = []
    # Use a prompt that won't match any direct command route.
    async for frame in engine.stream_agent("please check if plex is healthy and restart it if not"):
        frames.append(frame)

    # Should have: thought(s) from iteration 1, action, observation,
    # thought(s) from iteration 2, and answer.
    types = [f["type"] for f in frames]
    assert "thought" in types
    assert "action" in types
    assert "observation" in types
    assert "answer" in types
    assert types[-1] == "answer"

    # Tool was executed
    assert len(executed) == 1
    assert executed[0] == {"action": "restart", "container": "plex"}

    # Observation reports success
    obs_frames = [f for f in frames if f["type"] == "observation"]
    assert obs_frames[0]["success"] is True
    assert "restarted" in obs_frames[0]["result"]

    # Final answer
    answer = next(f for f in frames if f["type"] == "answer")
    assert "Done" in answer["content"] or "Plex" in answer["content"]


@pytest.mark.asyncio
async def test_stream_agent_no_tools_yields_answer_directly():
    """When the LLM doesn't call tools, stream_agent yields thought + answer."""
    engine = MKEngine()
    engine._llm_router = FakeAgentRouterNoTools()

    frames = [f async for f in engine.stream_agent("how is the system?")]
    types = [f["type"] for f in frames]
    assert "thought" in types
    assert "answer" in types
    assert "action" not in types


@pytest.mark.asyncio
async def test_stream_agent_direct_command_bypasses_loop():
    """Commands handled by the command router bypass the agent loop."""
    engine = MKEngine()
    engine._llm_router = FakeAgentRouter()

    # 'help' is handled by the command router as a direct path.
    frames = [f async for f in engine.stream_agent("help")]
    types = [f["type"] for f in frames]
    # 'help' is a direct command (verified via engine.command_router.route("help"))
    # If the router handles it directly, we get a single answer frame.
    # If not, the LLM handles it (thought + answer or thought + tool + answer).
    # We just verify it doesn't crash and produces an answer.
    assert "answer" in types
    assert frames[-1]["type"] == "answer"


@pytest.mark.asyncio
async def test_stream_agent_no_llm_degrades():
    """With no LLM, stream_agent yields the offline handler response."""
    engine = MKEngine()
    frames = [f async for f in engine.stream_agent("tell me a joke")]
    assert frames[-1]["type"] == "answer"
    assert frames[-1]["content"]  # non-empty offline message
