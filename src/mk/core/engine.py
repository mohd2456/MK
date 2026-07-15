"""MK Engine - The main entry point for the core system.

Ties everything together: configuration, LLM providers, memory,
tools, and the agent loop. Exposes a simple process(input) interface.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from mk.config.settings import Settings, load_config
from mk.core.agent_loop import AgentLoop, LLMProvider
from mk.core.command_router import CommandRouter
from mk.core.context import ContextBuilder
from mk.core.models import AgentResponse, AgentStep, Conversation, Role, ToolCall

logger = logging.getLogger(__name__)

# System prompt used for the streaming conversational path. The streaming path
# is a direct, token-by-token completion (no ReAct tool loop), so it gets a
# concise identity prompt; tool-driven requests still go through process().
_STREAM_SYSTEM_PROMPT = (
    "You are MK, a personal AI operating system that manages a homelab. "
    "Answer clearly and concisely. If an action would change the system, "
    "explain what you would do rather than pretending it is done."
)


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
        self._llm_router: Optional[Any] = None
        self._agent_loop: Optional[AgentLoop] = None

        self._server_manager: Optional[Any] = None

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

    def register_tool(self, name: str, handler: Callable[..., Any], description: str = "") -> None:
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
            # No LLM — try to handle common commands directly
            response = await self._handle_no_llm(user_input)

        self.conversation.add_message(Role.ASSISTANT, response.final_response)
        return response

    @property
    def llm_router(self) -> Optional[Any]:
        """Return the configured LLM router, or None if no providers are set up."""
        return self._llm_router

    def _build_stream_messages(self, max_turns: int = 12) -> List[Any]:
        """Build the LLM message list for a streaming completion.

        Uses a concise system prompt plus the most recent conversation turns
        (which already include the current user message). Tool/other roles are
        mapped to user/assistant so the payload stays provider-compatible.

        Args:
            max_turns: Maximum number of recent turns to include.

        Returns:
            List of ``LLMMessage`` objects.
        """
        from mk.llm.models import LLMMessage, MessageRole

        messages: List[Any] = [LLMMessage(role=MessageRole.SYSTEM, content=_STREAM_SYSTEM_PROMPT)]
        recent = self.conversation.messages[-max_turns:]
        for msg in recent:
            role = MessageRole.ASSISTANT if msg.role == Role.ASSISTANT else MessageRole.USER
            messages.append(LLMMessage(role=role, content=msg.content))
        return messages

    async def stream_reply(self, user_input: str) -> AsyncIterator[str]:
        """Process user input and stream the reply in chunks.

        Streaming rules:
        * Direct commands and the no-LLM fallback are inherently non-streaming;
          their full text is yielded as a single chunk.
        * When an LLM router is configured, the conversational reply is streamed
          token-by-token via :meth:`LLMRouter.stream`.

        The assistant's full reply is recorded to the conversation once complete.

        Args:
            user_input: The user's input text.

        Yields:
            Reply text chunks in order.
        """
        self.conversation.add_message(Role.USER, user_input)

        # Direct command routing — instant, not token-streamed.
        route_result = self.command_router.route(user_input)
        if route_result.is_direct and route_result.tool_name:
            response = await self._handle_direct_command(
                route_result.tool_name, route_result.tool_args
            )
            self.conversation.add_message(Role.ASSISTANT, response.final_response)
            yield response.final_response
            return

        # Streaming LLM completion.
        if self._llm_router is not None:
            from mk.llm.models import LLMRequest

            request = LLMRequest(messages=self._build_stream_messages())
            chunks: List[str] = []
            async for chunk in self._llm_router.stream(request):
                chunks.append(chunk)
                yield chunk
            self.conversation.add_message(Role.ASSISTANT, "".join(chunks))
            return

        # No LLM configured — degrade to the offline handler (single chunk).
        response = await self._handle_no_llm(user_input)
        self.conversation.add_message(Role.ASSISTANT, response.final_response)
        yield response.final_response

    async def stream_agent(self, user_input: str) -> AsyncIterator[Dict[str, Any]]:
        """Run the full ReAct agent loop with streaming reasoning + tool execution.

        Unlike :meth:`stream_reply` (which is a single-turn LLM stream with no
        tool execution), this method performs multi-step reasoning: each
        iteration either streams reasoning tokens or executes a tool, yielding
        structured frames so the UI can render thoughts, actions, observations,
        and the final answer as they happen.

        Frame types yielded:
            ``{"type": "thought", "chunk": str}`` — a token of LLM reasoning
            ``{"type": "action", "tool": str, "args": dict}`` — about to execute
            ``{"type": "observation", "tool": str, "result": str, "success": bool}``
            ``{"type": "answer", "content": str}`` — final response (always last)

        Falls back to :meth:`stream_reply` behavior (single-turn, no tools) when
        no agent loop is configured.

        Args:
            user_input: The user's input text.

        Yields:
            Structured dicts describing each step of the agent's reasoning.
        """
        self.conversation.add_message(Role.USER, user_input)

        # Direct command routing — yields a single answer frame.
        route_result = self.command_router.route(user_input)
        if route_result.is_direct and route_result.tool_name:
            response = await self._handle_direct_command(
                route_result.tool_name, route_result.tool_args
            )
            self.conversation.add_message(Role.ASSISTANT, response.final_response)
            yield {"type": "answer", "content": response.final_response}
            return

        # If no LLM router, fall back to no-LLM handler.
        if self._llm_router is None:
            response = await self._handle_no_llm(user_input)
            self.conversation.add_message(Role.ASSISTANT, response.final_response)
            yield {"type": "answer", "content": response.final_response}
            return

        # Full streaming ReAct loop.
        from mk.llm.models import LLMRequest

        max_iterations = 10
        working_context = user_input
        all_thoughts: List[str] = []

        for iteration in range(max_iterations):
            # Build messages for this iteration.
            messages = self._build_agent_messages(working_context, iteration)
            request = LLMRequest(messages=messages)

            # Stream the LLM response for this iteration.
            response_text_parts: List[str] = []
            async for chunk in self._llm_router.stream(request):
                response_text_parts.append(chunk)
                yield {"type": "thought", "chunk": chunk}

            response_text = "".join(response_text_parts)
            all_thoughts.append(response_text)

            # Parse for tool calls (JSON tool-call format from the response).
            tool_calls = self._parse_tool_calls(response_text)

            if not tool_calls:
                # No tool calls → this is the final answer.
                self.conversation.add_message(Role.ASSISTANT, response_text)
                yield {"type": "answer", "content": response_text}
                return

            # Execute each tool call and yield action/observation frames.
            tool_results: List[str] = []
            for tc_name, tc_args in tool_calls:
                yield {"type": "action", "tool": tc_name, "args": tc_args}
                try:
                    result = await self._execute_tool(tc_name, tc_args)
                    result_str = str(result) if result is not None else "OK"
                    yield {
                        "type": "observation",
                        "tool": tc_name,
                        "result": result_str[:1000],
                        "success": True,
                    }
                    tool_results.append(f"Tool '{tc_name}': {result_str[:500]}")
                except Exception as exc:
                    error_str = f"{type(exc).__name__}: {exc}"
                    yield {
                        "type": "observation",
                        "tool": tc_name,
                        "result": error_str,
                        "success": False,
                    }
                    tool_results.append(f"Tool '{tc_name}' failed: {error_str}")

            # Feed tool results back for the next iteration.
            working_context = (
                f"{user_input}\n\n"
                f"[Tool results from step {iteration + 1}]\n"
                + "\n".join(tool_results)
                + "\n\nContinue or provide your final answer."
            )

        # Max iterations — synthesize a final answer.
        final = "I've completed my reasoning. " + (all_thoughts[-1] if all_thoughts else "")
        self.conversation.add_message(Role.ASSISTANT, final)
        yield {"type": "answer", "content": final}

    def _build_agent_messages(self, working_context: str, iteration: int) -> List[Any]:
        """Build messages for a streaming agent iteration.

        Includes the system prompt with tool descriptions, recent conversation,
        and the current working context (which may include tool results from
        prior iterations).
        """
        from mk.llm.models import LLMMessage, MessageRole

        tool_descs = self._get_tool_descriptions()
        tools_section = ""
        if tool_descs:
            tools_section = "\n\nAvailable tools (call by responding with JSON):\n"
            for t in tool_descs:
                tools_section += f"- {t['name']}: {t['description'][:80]}\n"
            tools_section += (
                "\nTo call a tool, respond with: "
                '{"tool": "tool_name", "params": {...}}\n'
                "To give a final answer, just respond normally without a tool call."
            )

        system = (
            "You are MK, a personal AI operating system managing a homelab. "
            "You can execute multi-step tasks by calling tools, observing results, "
            "and continuing until the task is complete. Think step by step."
            + tools_section
        )

        messages: List[Any] = [LLMMessage(role=MessageRole.SYSTEM, content=system)]

        # Recent conversation for context (skip current iteration's working input).
        if iteration == 0:
            recent = self.conversation.messages[-8:]
            for msg in recent:
                role = MessageRole.ASSISTANT if msg.role == Role.ASSISTANT else MessageRole.USER
                messages.append(LLMMessage(role=role, content=msg.content))
        else:
            # Subsequent iterations: just the working context with tool results.
            messages.append(LLMMessage(role=MessageRole.USER, content=working_context))

        return messages

    def _parse_tool_calls(self, text: str) -> List[tuple]:
        """Parse tool calls from LLM response text.

        Looks for JSON objects with a "tool" key and optional "params".
        Returns a list of (tool_name, args_dict) tuples.
        Defensive: returns empty list if no valid tool calls found.
        """
        import json as _json

        calls: List[tuple] = []
        # Find JSON objects by tracking brace depth (handles nested braces).
        i = 0
        while i < len(text):
            if text[i] == "{":
                depth = 0
                start = i
                while i < len(text):
                    if text[i] == "{":
                        depth += 1
                    elif text[i] == "}":
                        depth -= 1
                        if depth == 0:
                            candidate = text[start : i + 1]
                            try:
                                obj = _json.loads(candidate)
                                tool_name = obj.get("tool")
                                params = obj.get("params", obj.get("args", {}))
                                if tool_name and isinstance(tool_name, str):
                                    calls.append(
                                        (tool_name, params if isinstance(params, dict) else {})
                                    )
                            except (_json.JSONDecodeError, TypeError, ValueError):
                                pass
                            break
                    i += 1
            i += 1
        return calls

    async def _handle_no_llm(self, user_input: str) -> AgentResponse:
        """Handle user input when no LLM is configured.

        Order of operations:
        1. remember/forget (explicit memory commands)
        2. Try to extract learnings from natural conversation
        3. Match exact-word keywords for server commands
        4. Greetings and help
        5. Fallback message

        Args:
            user_input: The user's input text.

        Returns:
            AgentResponse.
        """
        text = user_input.strip().lower()
        words = set(text.split())

        # --- 1. remember/forget FIRST (before anything else) ---
        if text.startswith("remember"):
            fact = user_input.strip()
            for prefix in ("remember that ", "remember "):
                if fact.lower().startswith(prefix):
                    fact = fact[len(prefix) :]
                    break
            if not fact or fact.lower() in ("remember", "that", "remember that"):
                return AgentResponse(
                    steps=[],
                    final_response="What should I remember? Say: remember that [something]",
                    tokens_used=0,
                    cost=0.0,
                )
            if "server" in self._tools:
                try:
                    result = await self._tools["server"](
                        domain="chat", action="remember", args={"fact": fact}
                    )
                    output = (
                        getattr(result, "output", "") or getattr(result, "error", "") or str(result)
                    )
                    return AgentResponse(steps=[], final_response=output, tokens_used=0, cost=0.0)
                except Exception as e:
                    return AgentResponse(
                        steps=[], final_response=f"Error: {str(e)}", tokens_used=0, cost=0.0
                    )

        if text.startswith("forget"):
            key = user_input.strip()
            for prefix in ("forget that ", "forget about ", "forget "):
                if key.lower().startswith(prefix):
                    key = key[len(prefix) :]
                    break
            if not key or key.lower() in ("forget", "that", "about"):
                return AgentResponse(
                    steps=[],
                    final_response="What should I forget? Say: forget [something]",
                    tokens_used=0,
                    cost=0.0,
                )
            if "server" in self._tools:
                try:
                    result = await self._tools["server"](
                        domain="chat", action="forget", args={"key": key}
                    )
                    output = (
                        getattr(result, "output", "") or getattr(result, "error", "") or str(result)
                    )
                    return AgentResponse(steps=[], final_response=output, tokens_used=0, cost=0.0)
                except Exception as e:
                    return AgentResponse(
                        steps=[], final_response=f"Error: {str(e)}", tokens_used=0, cost=0.0
                    )

        # --- 2. Try to learn from natural conversation ---
        # "my name is X", "I like X", "I live in X", etc.
        learned = self._try_learn_from_input(user_input)
        if learned:
            return AgentResponse(
                steps=[],
                final_response=learned,
                tokens_used=0,
                cost=0.0,
            )

        # --- 3. Exact word keyword matching (no substring!) ---
        keyword_map = {
            "status": ("system", "overview", {}),
            "health": ("system", "health", {}),
            "overview": ("system", "overview", {}),
            "containers": ("containers", "list", {}),
            "docker": ("containers", "list", {}),
            "storage": ("storage", "list_pools", {}),
            "pools": ("storage", "list_pools", {}),
            "disks": ("storage", "list_disks", {}),
            "services": ("services", "failed", {}),
            "failed": ("services", "failed", {}),
            "network": ("network", "list_interfaces", {}),
            "interfaces": ("network", "list_interfaces", {}),
            "ip": ("homelab", "public_ip", {}),
            "temps": ("homelab", "temperatures", {}),
            "temperature": ("homelab", "temperatures", {}),
            "uptime": ("system", "overview", {}),
            "backup": ("backups", "health", {}),
            "backups": ("backups", "health", {}),
            "users": ("users", "list", {}),
            "keys": ("keys", "list", {}),
            "models": ("keys", "strategy", {}),
            "vms": ("vms", "list", {}),
            "lxc": ("lxc", "list", {}),
            "speedtest": ("homelab", "speedtest", {}),
            "rip": ("ripper", "disc_status", {}),
            "eject": ("ripper", "eject", {}),
            "hardware": ("system", "hardware", {}),
            "updates": ("system", "check_updates", {}),
            "aboutme": ("chat", "profile", {}),
            "profile": ("chat", "profile", {}),
        }

        # Match by exact word (not substring)
        for keyword, (domain, action, args) in keyword_map.items():
            if keyword in words:
                if "server" in self._tools:
                    try:
                        result = await self._tools["server"](
                            domain=domain, action=action, args=args
                        )
                        output = (
                            getattr(result, "output", "")
                            or getattr(result, "error", "")
                            or str(result)
                        )
                        return AgentResponse(
                            steps=[],
                            final_response=output,
                            tokens_used=0,
                            cost=0.0,
                        )
                    except Exception as e:
                        return AgentResponse(
                            steps=[],
                            final_response=f"Error: {str(e)}",
                            tokens_used=0,
                            cost=0.0,
                        )

        # --- 4. Greetings ---
        greetings = {"hello", "hi", "hey", "sup", "yo", "chat"}
        if words & greetings:
            return AgentResponse(
                steps=[],
                final_response=(
                    "Hey. MK is running but no AI provider is configured.\n"
                    "I can still run direct commands. Try:\n"
                    "  status, containers, storage, services, network,\n"
                    "  backup, hardware, temps, speedtest, users, keys\n\n"
                    "To add AI: /setkey your-api-key (from Telegram)\n"
                    "Or edit /etc/mk/config.yaml"
                ),
                tokens_used=0,
                cost=0.0,
            )

        # Help
        if words & {"help", "?", "commands"}:
            return AgentResponse(
                steps=[],
                final_response=(
                    "MK OS — Available without AI:\n\n"
                    "  status       — System overview\n"
                    "  health       — Full health report\n"
                    "  containers   — Docker containers\n"
                    "  storage      — ZFS pools\n"
                    "  services     — Failed services\n"
                    "  network      — Network interfaces\n"
                    "  backup       — Backup health\n"
                    "  hardware     — Hardware info\n"
                    "  temps        — Temperatures\n"
                    "  speedtest    — Internet speed\n"
                    "  users        — User accounts\n"
                    "  vms          — Virtual machines\n"
                    "  lxc          — LXC containers\n"
                    "  keys         — API keys configured\n"
                    "  rip          — Disc ripper status\n"
                    "  eject        — Eject disc\n"
                    "  updates      — Check for updates\n"
                    "  aboutme      — What I know about you\n\n"
                    "Memory commands:\n"
                    "  remember that [fact]\n"
                    "  forget [thing]\n"
                    "  my name is [name]\n"
                    "  I like [thing]\n\n"
                    "For full natural language: add an API key.\n"
                    "  /setkey your-key (from Telegram)\n"
                    "  Or edit /etc/mk/config.yaml"
                ),
                tokens_used=0,
                cost=0.0,
            )

        # --- 5. Default ---
        return AgentResponse(
            steps=[],
            final_response=(
                f'No AI configured — can\'t process: "{user_input}"\n'
                "Type 'help' to see what works without AI,\n"
                "or add a key: /setkey your-api-key"
            ),
            tokens_used=0,
            cost=0.0,
        )

    def _try_learn_from_input(self, user_input: str) -> str:
        """Try to extract and store learnings from natural conversation.

        Handles: "my name is X", "I like X", "I live in X", "I work at X"
        without needing an LLM.

        Args:
            user_input: User's raw input.

        Returns:
            Response string if something was learned, empty string if not.
        """
        if "server" not in self._tools:
            return ""

        from mk.chat import ChatMode

        chat = ChatMode()
        learnings = chat.extract_learnings(user_input)

        if not learnings:
            return ""

        # Build response
        responses = []
        for learning in learnings:
            if learning.startswith("name:"):
                name = learning.split(":", 1)[1]
                responses.append(f"Got it, {name}.")
            elif learning.startswith("fact:"):
                fact = learning.split(":", 1)[1]
                responses.append(f"✓ Noted: {fact}")
            elif learning.startswith("preference:"):
                pref = learning.split(":", 1)[1]
                responses.append(f"✓ Preference saved: {pref}")

        return "\n".join(responses) if responses else ""

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

    async def _execute_tool(self, name: str, args: Dict[str, Any]) -> Any:
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

    def setup_server_management(self, **kwargs: Any) -> None:
        """Initialize and register the server management layer.

        Sets up all server sub-managers (storage, containers, network,
        services, backups, users) and registers the unified server tool.

        Args:
            **kwargs: Passed to ServerManager constructor (sudo, compose_dir, etc.).
        """
        from mk.server import ServerManager, create_server_tools

        self._server_manager = ServerManager(**kwargs)
        server_tools = create_server_tools(self._server_manager)

        for tool in server_tools:
            self._tools[tool.name] = tool.execute
            logger.info(f"Registered server tool: {tool.name}")

    def setup_llm_providers(self, keys_file: Optional[str] = None) -> None:
        """Auto-configure LLM providers from stored API keys.

        Reads all keys from the KeyManager, creates the appropriate provider
        instances, registers them with an LLMRouter, and sets up the agent
        loop. Call this on startup after /setkey has stored keys.

        Args:
            keys_file: Optional path to keys file. Uses default if None.
        """
        import os

        from mk.llm.keys import KeyManager
        from mk.llm.provider_factory import LOCAL_BRAIN_URL_ENV, configure_router_from_keys

        kwargs = {}
        if keys_file is not None:
            kwargs["keys_file"] = keys_file

        key_manager = KeyManager(**kwargs)
        active = key_manager.get_active_providers()
        has_local_brain = bool(os.environ.get(LOCAL_BRAIN_URL_ENV))

        if not active and not has_local_brain:
            logger.info("No API keys stored and no local brain - LLM providers not configured")
            return

        # configure_router_from_keys registers keyed providers and the local
        # brain (if MK_LOCAL_BRAIN_URL is set), so MK can run purely on local
        # inference with no cloud keys at all.
        router = configure_router_from_keys(key_manager)

        if router.providers:
            self._llm_router = router
            # Use the router as the LLM provider for the agent loop
            self._setup_agent_loop(router)
            logger.info(
                f"LLM configured: {len(router.providers)} providers "
                f"({', '.join(router.providers.keys())})"
            )

    @property
    def server(self) -> Optional[Any]:
        """Access the ServerManager instance (if initialized).

        Returns:
            ServerManager or None if not set up.
        """
        return self._server_manager
