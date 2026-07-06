"""MK Engine - The main entry point for the core system.

Ties everything together: configuration, LLM providers, memory,
tools, and the agent loop. Exposes a simple process(input) interface.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from mk.config.settings import Settings, load_config
from mk.core.agent_loop import AgentLoop, LLMProvider
from mk.core.command_router import CommandRouter
from mk.core.context import ContextBuilder
from mk.core.models import AgentResponse, AgentStep, Conversation, Role, ToolCall

logger = logging.getLogger(__name__)


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
            # No LLM — try to handle common commands directly
            response = await self._handle_no_llm(user_input)

        self.conversation.add_message(Role.ASSISTANT, response.final_response)
        return response

    async def _handle_no_llm(self, user_input: str) -> AgentResponse:
        """Handle user input when no LLM is configured.

        Tries to match common server commands by keyword.
        Falls back to a helpful message.

        Args:
            user_input: The user's input text.

        Returns:
            AgentResponse.
        """
        text = user_input.strip().lower()

        # Map keywords to server tool calls
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

        # Check for keyword match
        for keyword, (domain, action, args) in keyword_map.items():
            if keyword in text:
                # Try to execute via server tool
                if "server" in self._tools:
                    try:
                        result = await self._tools["server"](
                            domain=domain, action=action, args=args
                        )
                        output = getattr(result, "output", "") or getattr(result, "error", "") or str(result)
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

        # "remember that..." handling
        if text.startswith("remember"):
            fact = user_input.strip()
            # Strip "remember that" prefix
            for prefix in ("remember that ", "remember "):
                if fact.lower().startswith(prefix):
                    fact = fact[len(prefix):]
                    break
            # If after stripping we still have "remember" or empty, reject
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
                    output = getattr(result, "output", str(result))
                    return AgentResponse(steps=[], final_response=output, tokens_used=0, cost=0.0)
                except Exception as e:
                    return AgentResponse(steps=[], final_response=f"Error: {str(e)}", tokens_used=0, cost=0.0)

        # "forget..." handling
        if text.startswith("forget"):
            key = user_input.strip()
            for prefix in ("forget that ", "forget about ", "forget "):
                if key.lower().startswith(prefix):
                    key = key[len(prefix):]
                    break
            # Reject empty or just "forget"
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
                    output = getattr(result, "output", str(result))
                    return AgentResponse(steps=[], final_response=output, tokens_used=0, cost=0.0)
                except Exception as e:
                    return AgentResponse(steps=[], final_response=f"Error: {str(e)}", tokens_used=0, cost=0.0)

        # Greetings
        greetings = ("hello", "hi", "hey", "sup", "yo", "chat")
        if text in greetings or text.rstrip("!") in greetings:
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
        if text in ("help", "?", "commands"):
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
                    "  updates      — Check for updates\n\n"
                    "For full natural language: add an API key.\n"
                    "  /setkey your-key (from Telegram)\n"
                    "  Or edit /etc/mk/config.yaml"
                ),
                tokens_used=0,
                cost=0.0,
            )

        # Default: no match
        return AgentResponse(
            steps=[],
            final_response=(
                f"No AI configured — can't process: \"{user_input}\"\n"
                "Type 'help' to see what works without AI,\n"
                "or add a key: /setkey your-api-key"
            ),
            tokens_used=0,
            cost=0.0,
        )

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

    @property
    def server(self) -> Optional[Any]:
        """Access the ServerManager instance (if initialized).

        Returns:
            ServerManager or None if not set up.
        """
        return self._server_manager
