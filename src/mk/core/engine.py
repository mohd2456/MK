"""MK Engine - The main entry point for the core system.

Ties everything together: configuration, LLM providers, memory,
tools, and the agent loop. Exposes a simple process(input) interface.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from mk.config.settings import Settings, load_config
from mk.core.agent_loop import AgentLoop, LLMProvider
from mk.core.command_router import CommandRouter
from mk.core.context import ContextBuilder
from mk.core.models import AgentResponse, AgentStep, Conversation, Role, ToolCall


class MKEngine:
    """The MK Engine - central orchestrator for all operations.

    Initializes configuration, sets up providers, registers tools,
    and processes user input through either direct routing or the
    full agent loop.
    """

    def __init__(
        self,
        config_path: Optional[str] = None,
        settings: Optional[Settings] = None,
        llm_provider: Optional[LLMProvider] = None,
    ) -> None:
        """Initialize the MK Engine.

        Args:
            config_path: Path to config YAML file.
            settings: Pre-built Settings instance (overrides config_path).
            llm_provider: LLM provider to use. If None, a placeholder is used.
        """
        self.settings = settings or load_config(config_path)
        self.conversation = Conversation()
        self.command_router = CommandRouter()
        self.context_builder = ContextBuilder(
            token_budget=self.settings.memory.context_window_budget
        )
        self._tools: Dict[str, Callable[..., Any]] = {}
        self._llm_provider = llm_provider
        self._agent_loop: Optional[AgentLoop] = None

        if llm_provider:
            self._setup_agent_loop(llm_provider)

    def _setup_agent_loop(self, provider: LLMProvider) -> None:
        """Set up the agent loop with a provider.

        Args:
            provider: The LLM provider to use.
        """
        self._agent_loop = AgentLoop(
            llm_provider=provider,
            context_builder=self.context_builder,
            tool_executor=self._execute_tool,
            max_iterations=self.settings.safety.max_iterations,
        )

    def register_tool(
        self, name: str, handler: Callable[..., Any], description: str = ""
    ) -> None:
        """Register a tool for the agent to use.

        Args:
            name: Tool name.
            handler: Async callable that implements the tool.
            description: Human-readable description of the tool.
        """
        self._tools[name] = handler

    async def process(self, user_input: str) -> AgentResponse:
        """Process user input and return a response.

        Routes simple commands directly to tools. Complex queries
        go through the full agent loop with LLM reasoning.

        Args:
            user_input: The user's input text.

        Returns:
            AgentResponse with the result.
        """
        # Record user message
        self.conversation.add_message(Role.USER, user_input)

        # Try direct command routing first
        route_result = self.command_router.route(user_input)

        if route_result.is_direct and route_result.tool_name:
            response = await self._handle_direct_command(
                route_result.tool_name, route_result.tool_args
            )
            self.conversation.add_message(Role.ASSISTANT, response.final_response)
            return response

        # Complex query - use agent loop
        if self._agent_loop:
            response = await self._agent_loop.run(
                user_input=user_input,
                conversation=self.conversation,
                available_tools=self._get_tool_descriptions(),
            )
        else:
            # No LLM provider configured
            response = AgentResponse(
                steps=[],
                final_response=(
                    "No LLM provider configured. "
                    "Please add a provider to config.yaml."
                ),
                tokens_used=0,
                cost=0.0,
            )

        self.conversation.add_message(Role.ASSISTANT, response.final_response)
        return response

    async def _handle_direct_command(
        self, tool_name: str, tool_args: Dict[str, str]
    ) -> AgentResponse:
        """Handle a directly-routed command.

        Args:
            tool_name: The tool to execute.
            tool_args: Arguments for the tool.

        Returns:
            AgentResponse with the tool result.
        """
        tool_call = ToolCall(name=tool_name, args=tool_args)

        if tool_name in self._tools:
            try:
                result = await self._execute_tool(tool_name, tool_args)
                tool_call.result = str(result)
                tool_call.executed = True
            except Exception as e:
                tool_call.error = str(e)
                tool_call.executed = True
        else:
            tool_call.error = f"Tool '{tool_name}' not found"
            tool_call.executed = True

        step = AgentStep(
            thought=None,
            action=tool_call,
            observation=tool_call.result or tool_call.error,
        )

        final = tool_call.result or f"Error: {tool_call.error}"
        return AgentResponse(
            steps=[step],
            final_response=final,
            tokens_used=0,
            cost=0.0,
            was_direct_command=True,
        )

    async def _execute_tool(
        self, name: str, args: Dict[str, Any]
    ) -> Any:
        """Execute a registered tool.

        Args:
            name: Tool name.
            args: Tool arguments.

        Returns:
            Tool result.

        Raises:
            KeyError: If tool is not registered.
        """
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' is not registered")
        handler = self._tools[name]
        return await handler(**args)

    def _get_tool_descriptions(self) -> List[Dict[str, str]]:
        """Get descriptions of all registered tools.

        Returns:
            List of tool info dicts.
        """
        return [
            {"name": name, "description": getattr(handler, "__doc__", "") or ""}
            for name, handler in self._tools.items()
        ]
