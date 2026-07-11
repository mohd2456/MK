"""Agent loop for MK.

Implements the core reasoning loop:
input -> context enrichment -> LLM call -> parse response -> execute tools -> loop.

The loop continues until the LLM provides a final answer or max iterations
is reached. This is the heart of MK's intelligence.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Protocol

from mk.core.context import ContextBuilder
from mk.core.models import AgentResponse, AgentStep, Conversation, ToolCall


class LLMProvider(Protocol):
    """Protocol for LLM provider implementations."""

    async def complete(self, messages: List[Dict[str, str]], **kwargs: Any) -> Dict[str, Any]:
        """Send messages to the LLM and get a completion.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            **kwargs: Additional provider-specific parameters.

        Returns:
            Dict with 'content' (response text), 'tokens_used' (int),
            and optionally 'tool_calls' (list of tool call dicts).
        """
        ...  # pragma: no cover

    @property
    def name(self) -> str:
        """Provider name."""
        ...  # pragma: no cover


class AgentLoop:
    """The MK agent loop - processes input through reasoning cycles.

    Implements the plan-execute-check pattern:
    1. Build context from input + memory + state
    2. Call LLM for reasoning/planning
    3. Parse response for tool calls or final answer
    4. If tool calls: execute them and loop back to step 2
    5. If final answer: return the response

    Respects max iterations to prevent infinite loops.
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        context_builder: ContextBuilder,
        tool_executor: Optional[Callable[[str, Dict[str, Any]], Any]] = None,
        max_iterations: int = 10,
        system_prompt: Optional[str] = None,
    ) -> None:
        """Initialize the agent loop.

        Args:
            llm_provider: The LLM provider to use for completions.
            context_builder: Context builder for assembling prompts.
            tool_executor: Async callable that executes tools by name.
            max_iterations: Maximum loop iterations before stopping.
            system_prompt: Custom system prompt for MK.
        """
        self.llm_provider = llm_provider
        self.context_builder = context_builder
        self.tool_executor = tool_executor
        self.max_iterations = max_iterations
        self.system_prompt = system_prompt

    async def run(
        self,
        user_input: str,
        conversation: Optional[Conversation] = None,
        memory_context: Optional[str] = None,
        system_state: Optional[Dict[str, Any]] = None,
        available_tools: Optional[List[Dict[str, str]]] = None,
    ) -> AgentResponse:
        """Run the agent loop on user input.

        Args:
            user_input: The user's input text.
            conversation: Current conversation for context.
            memory_context: Relevant memories about the user.
            system_state: Current system state info.
            available_tools: List of available tool descriptions.

        Returns:
            AgentResponse with steps taken, final response, and usage stats.
        """
        steps: List[AgentStep] = []
        total_tokens = 0
        total_cost = 0.0
        iteration = 0

        # Working messages - starts with context-enriched prompt
        working_input = user_input

        while iteration < self.max_iterations:
            iteration += 1

            # Build context
            messages = self.context_builder.build_context(
                user_input=working_input,
                conversation=conversation,
                memory_context=memory_context,
                system_state=system_state,
                available_tools=available_tools,
                system_prompt=self.system_prompt,
            )

            # Call LLM
            llm_response = await self.llm_provider.complete(messages)

            content = llm_response.get("content", "")
            tokens = llm_response.get("tokens_used", 0)
            cost = llm_response.get("cost", 0.0)
            tool_calls_raw = llm_response.get("tool_calls", [])

            total_tokens += tokens
            total_cost += cost

            # Parse for tool calls
            if tool_calls_raw:
                for tc in tool_calls_raw:
                    tool_call = ToolCall(
                        name=tc.get("name", ""),
                        args=tc.get("args", {}),
                    )

                    # Execute tool if executor available
                    if self.tool_executor:
                        try:
                            result = await self._execute_tool(tool_call.name, tool_call.args)
                            tool_call.result = str(result)
                            tool_call.executed = True
                        except Exception as e:
                            tool_call.error = str(e)
                            tool_call.executed = True

                    step = AgentStep(
                        thought=content if content else None,
                        action=tool_call,
                        observation=tool_call.result or tool_call.error,
                    )
                    steps.append(step)

                # Continue loop with tool results as context
                tool_results = self._format_tool_results(steps[-len(tool_calls_raw) :])
                working_input = (
                    f"{user_input}\n\n"
                    f"[Tool execution results]\n{tool_results}\n\n"
                    "Continue with the task or provide a final response."
                )
            else:
                # No tool calls - this is the final response
                step = AgentStep(thought=content, action=None, observation=None)
                steps.append(step)

                return AgentResponse(
                    steps=steps,
                    final_response=content,
                    tokens_used=total_tokens,
                    cost=total_cost,
                    provider_used=self.llm_provider.name,
                )

        # Max iterations reached
        final_msg = "I've reached my iteration limit. Here's what I have so far: " + (
            steps[-1].thought or "Unable to complete the task."
        )
        return AgentResponse(
            steps=steps,
            final_response=final_msg,
            tokens_used=total_tokens,
            cost=total_cost,
            provider_used=self.llm_provider.name,
        )

    async def _execute_tool(self, name: str, args: Dict[str, Any]) -> Any:
        """Execute a tool by name.

        Args:
            name: Tool name.
            args: Tool arguments.

        Returns:
            Tool execution result.

        Raises:
            RuntimeError: If no tool executor is configured.
        """
        if not self.tool_executor:
            raise RuntimeError("No tool executor configured")
        return await self.tool_executor(name, args)

    def _format_tool_results(self, steps: List[AgentStep]) -> str:
        """Format tool results for inclusion in the next prompt.

        Args:
            steps: Recent steps with tool results.

        Returns:
            Formatted string of tool results.
        """
        results = []
        for step in steps:
            if step.action:
                tc = step.action
                if tc.result:
                    results.append(f"Tool '{tc.name}': {tc.result}")
                elif tc.error:
                    results.append(f"Tool '{tc.name}' failed: {tc.error}")
        return "\n".join(results)
