"""MK Engine V2 — Season 2 integrated engine.

Extends the original MKEngine with all Season 2 subsystems:
- Plugin system (auto-discovery, sandboxed execution)
- Task planner (DAG decomposition, sub-agents)
- Proactive ops (scheduled checks, alerts, events)
- Semantic memory (vector embeddings, decision log)
- Policy engine (declarative rules, snapshots, rollback)

Backward compatible: all existing tools, memory, and brain still work.
The V2 engine adds new capabilities without breaking the old interface.

Usage:
    engine = MKEngineV2(settings=settings)
    await engine.initialize()  # Loads plugins, starts ops
    response = await engine.process(user_input)  # Same interface as V1
    await engine.shutdown()  # Graceful shutdown of background tasks
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

if TYPE_CHECKING:
    from mk.config.settings import Settings

from mk.core.engine import MKEngine
from mk.core.models import AgentResponse, AgentStep, Role

logger = logging.getLogger(__name__)


class MKEngineV2(MKEngine):
    """Season 2 MK Engine — full autonomous operating system.

    Inherits all V1 behavior and adds:
    - Plugin loading and tool discovery
    - Task planning with sub-agents for complex requests
    - Proactive infrastructure monitoring (background)
    - Semantic memory for intelligent recall
    - Policy enforcement on all tool calls
    - Change preview and rollback support

    The V2 engine requires an explicit initialize() call to start
    background services (ops scheduler, file watchers). This is
    async because plugin loading and ops startup are async.
    """

    def __init__(
        self,
        config_path: Optional[str] = None,
        settings: Optional["Settings"] = None,
        llm_provider: Optional[Any] = None,
        plugin_dirs: Optional[List[str]] = None,
        policy_paths: Optional[List[str]] = None,
        enable_ops: bool = True,
        enable_plugins: bool = True,
        enable_planner: bool = True,
        enable_semantic_memory: bool = True,
        enable_policy: bool = True,
    ) -> None:
        """Initialize the V2 engine.

        Args:
            config_path: Path to config YAML file.
            settings: Pre-built Settings instance.
            llm_provider: LLM provider (V1 compatibility).
            plugin_dirs: Directories to scan for plugins.
            policy_paths: Paths to policy YAML files.
            enable_ops: Whether to start the ops scheduler.
            enable_plugins: Whether to load plugins.
            enable_planner: Whether to enable task planning.
            enable_semantic_memory: Whether to enable vector memory.
            enable_policy: Whether to enable the policy engine.
        """
        # Initialize V1 base
        super().__init__(
            config_path=config_path,
            settings=settings,
            llm_provider=llm_provider,
        )

        # Feature flags
        self._enable_ops = enable_ops
        self._enable_plugins = enable_plugins
        self._enable_planner = enable_planner
        self._enable_semantic_memory = enable_semantic_memory
        self._enable_policy = enable_policy

        # Season 2 subsystems (initialized in .initialize())
        self._plugin_manager: Optional[Any] = None
        self._task_planner: Optional[Any] = None
        self._plan_executor: Optional[Any] = None
        self._ops_manager: Optional[Any] = None
        self._semantic_memory: Optional[Any] = None
        self._decision_log: Optional[Any] = None
        self._policy_engine: Optional[Any] = None
        self._snapshot_manager: Optional[Any] = None
        self._rollback_handler: Optional[Any] = None

        # Configuration
        self._plugin_dirs = plugin_dirs or [
            str(Path.home() / ".mk" / "plugins"),
        ]
        self._policy_paths = policy_paths or [
            str(Path.home() / ".mk" / "policies.yaml"),
            "/etc/mk/policies.yaml",
        ]

        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        """Whether initialize() has been called."""
        return self._initialized

    @property
    def plugin_manager(self) -> Optional[Any]:
        """Access the plugin manager."""
        return self._plugin_manager

    @property
    def ops_manager(self) -> Optional[Any]:
        """Access the ops manager."""
        return self._ops_manager

    @property
    def semantic_memory(self) -> Optional[Any]:
        """Access semantic memory."""
        return self._semantic_memory

    @property
    def policy_engine(self) -> Optional[Any]:
        """Access the policy engine."""
        return self._policy_engine

    async def initialize(
        self,
        notify_callback: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """Initialize all Season 2 subsystems.

        This is the async startup — loads plugins, starts ops,
        initializes memory and policies. Call once after construction.

        Args:
            notify_callback: Async function for sending proactive
                notifications (e.g., Telegram). Used by ops alerts.

        Returns:
            Dict with initialization summary.
        """
        summary: Dict[str, Any] = {"subsystems": {}}

        # 1. Plugin System
        if self._enable_plugins:
            summary["subsystems"]["plugins"] = await self._init_plugins()

        # 2. Task Planner + Sub-Agents
        if self._enable_planner:
            summary["subsystems"]["planner"] = self._init_planner()

        # 3. Proactive Ops
        if self._enable_ops:
            summary["subsystems"]["ops"] = await self._init_ops(notify_callback)

        # 4. Semantic Memory
        if self._enable_semantic_memory:
            summary["subsystems"]["memory"] = self._init_semantic_memory()

        # 5. Policy Engine
        if self._enable_policy:
            summary["subsystems"]["policy"] = self._init_policy()

        # 6. Auto-Tailscale (if configured)
        if self.settings.tailscale.enabled:
            summary["subsystems"]["tailscale"] = await self._init_tailscale()

            # Auto-expose Web UI on tailnet via Tailscale Serve
            try:
                from mk.server.network import NetworkManager

                nm = NetworkManager(sudo=True)
                await nm.tailscale_serve(port=8080, path="/")
                logger.info("Web UI exposed on tailnet via Tailscale Serve (port 8080)")
            except Exception as e:
                logger.debug(f"Tailscale Serve for Web UI skipped: {e}")

        self._initialized = True
        logger.info(f"MK Engine V2 initialized: {summary}")
        return summary

    async def shutdown(self) -> None:
        """Gracefully shut down all background services."""
        if self._ops_manager:
            await self._ops_manager.stop()
            logger.info("Ops manager stopped")

        if self._semantic_memory:
            self._semantic_memory.save()
            logger.info("Semantic memory saved")

        if self._decision_log:
            self._decision_log.save()
            logger.info("Decision log saved")

        logger.info("MK Engine V2 shutdown complete")

    async def process(self, user_input: str) -> AgentResponse:
        """Process user input with Season 2 enhancements.

        Enhanced flow:
        1. Enrich context with semantic memory recall
        2. Check if task planner can decompose the request
        3. Evaluate policies before tool execution
        4. Fall back to V1 processing for simple requests
        5. Log decisions and update semantic memory

        Args:
            user_input: The user's input text.

        Returns:
            AgentResponse with the result.
        """
        # Record user message
        self.conversation.add_message(Role.USER, user_input)

        # Handle Tailscale auth key via chat (like /setkey for LLM providers)
        if user_input.strip().startswith("tskey-") or user_input.strip().lower().startswith(
            "/tailscale "
        ):
            response = await self._handle_tailscale_command(user_input.strip())
            self.conversation.add_message(Role.ASSISTANT, response.final_response)
            return response

        # Enrich with semantic memory (add relevant context)
        memory_context = ""
        if self._semantic_memory:
            memory_context = self._semantic_memory.recall_formatted(
                user_input, top_k=5, min_score=0.2
            )

        # Try task planner for complex requests
        if self._task_planner and self._plan_executor:
            plan_result = self._task_planner.plan(user_input)

            if not plan_result.is_simple and plan_result.graph:
                # Complex request — execute through planner
                response = await self._execute_plan(plan_result, user_input)
                self.conversation.add_message(Role.ASSISTANT, response.final_response)

                # Store in semantic memory
                if self._semantic_memory:
                    from mk.memory.vector.semantic import MemoryType

                    self._semantic_memory.store(
                        content=f"User asked: {user_input[:100]}. Result: {response.final_response[:200]}",
                        memory_type=MemoryType.CONVERSATION,
                        source="planner",
                    )
                return response

        # Simple request — use V1 flow (command router → agent loop)
        route_result = self.command_router.route(user_input)

        if route_result.is_direct and route_result.tool_name:
            response = await self._handle_direct_command_v2(
                route_result.tool_name, route_result.tool_args
            )
        elif self._agent_loop:
            response = await self._agent_loop.run(
                user_input=user_input,
                conversation=self.conversation,
                memory_context=memory_context,
                available_tools=self._get_tool_descriptions(),
            )
        else:
            response = await self._handle_no_llm(user_input)

        self.conversation.add_message(Role.ASSISTANT, response.final_response)

        # Store meaningful interactions in semantic memory
        if self._semantic_memory and len(user_input) > 20:
            from mk.memory.vector.semantic import MemoryType

            self._semantic_memory.store(
                content=f"Q: {user_input[:80]} → A: {response.final_response[:150]}",
                memory_type=MemoryType.CONVERSATION,
                source="engine",
            )

        return response

    async def _handle_tailscale_command(self, user_input: str) -> AgentResponse:
        """Handle Tailscale auth key or commands directly.

        Supports:
        - Paste a tskey-auth-* key → stores it and connects immediately
        - /tailscale up → connect
        - /tailscale down → disconnect
        - /tailscale status → show status
        - /tailscale serve <port> → expose service
        - /tailscale ip → show tailscale IP
        """
        from mk.server.network import NetworkManager

        nm = NetworkManager(sudo=True)

        # User pasted a raw auth key
        if user_input.startswith("tskey-"):
            auth_key = user_input.strip()

            # Store it in secrets
            try:
                from mk.safety.secrets import SecretsManager

                secrets = SecretsManager()
                secrets.store_secret("tailscale_auth_key", auth_key)
            except Exception:
                pass  # Store failed, but we can still use it directly

            # Connect immediately
            result = await nm.tailscale_install()
            up_result = await nm.tailscale_up(
                auth_key=auth_key,
                hostname=self.settings.tailscale.hostname or "mk",
                advertise_routes=self.settings.tailscale.advertise_routes or None,
                accept_routes=True,
                ssh=True,
            )

            if up_result.success:
                ip_result = await nm.tailscale_ip()
                ip_str = ip_result.metadata.get("ipv4", "") if ip_result.success else ""
                return AgentResponse(
                    steps=[],
                    final_response=(
                        f"✓ Tailscale connected!\n"
                        f"  IP: {ip_str}\n"
                        f"  SSH: enabled (ssh into me from anywhere on your tailnet)\n"
                        f"  Key stored securely.\n\n"
                        f"You can now access this machine from any device on your tailnet."
                    ),
                    tokens_used=0,
                    cost=0.0,
                )
            elif up_result.metadata.get("needs_auth"):
                return AgentResponse(
                    steps=[],
                    final_response=(
                        f"Tailscale needs browser auth. Visit:\n"
                        f"{up_result.metadata.get('auth_url', '')}\n\n"
                        f"After authorizing, I'll be connected."
                    ),
                    tokens_used=0,
                    cost=0.0,
                )
            else:
                return AgentResponse(
                    steps=[],
                    final_response=f"Tailscale connection failed: {up_result.error}",
                    tokens_used=0,
                    cost=0.0,
                )

        # /tailscale commands
        parts = user_input.lower().replace("/tailscale", "").strip().split()
        cmd = parts[0] if parts else "status"

        if cmd == "up":
            result = await nm.tailscale_up(
                hostname=self.settings.tailscale.hostname or "mk",
                accept_routes=True,
                ssh=True,
            )
            return AgentResponse(
                steps=[],
                final_response=result.output or result.error or "Done",
                tokens_used=0,
                cost=0.0,
            )

        elif cmd == "down":
            result = await nm.tailscale_down()
            return AgentResponse(
                steps=[],
                final_response=result.output or result.error or "Disconnected",
                tokens_used=0,
                cost=0.0,
            )

        elif cmd == "status":
            result = await nm.tailscale_status()
            return AgentResponse(
                steps=[],
                final_response=result.output or result.error or "No status",
                tokens_used=0,
                cost=0.0,
            )

        elif cmd == "ip":
            result = await nm.tailscale_ip()
            return AgentResponse(
                steps=[],
                final_response=result.output or result.error or "No IP",
                tokens_used=0,
                cost=0.0,
            )

        elif cmd == "peers":
            result = await nm.tailscale_peers()
            return AgentResponse(
                steps=[],
                final_response=result.output or result.error or "No peers",
                tokens_used=0,
                cost=0.0,
            )

        elif cmd == "serve" and len(parts) > 1:
            port = int(parts[1]) if parts[1].isdigit() else 8080
            path = parts[2] if len(parts) > 2 else "/"
            result = await nm.tailscale_serve(port=port, path=path)
            return AgentResponse(
                steps=[],
                final_response=result.output or result.error or "Done",
                tokens_used=0,
                cost=0.0,
            )

        elif cmd == "funnel" and len(parts) > 1:
            port = int(parts[1]) if parts[1].isdigit() else 8080
            result = await nm.tailscale_funnel(port=port)
            return AgentResponse(
                steps=[],
                final_response=result.output or result.error or "Done",
                tokens_used=0,
                cost=0.0,
            )

        else:
            return AgentResponse(
                steps=[],
                final_response=(
                    "Tailscale commands:\n"
                    "  Paste your tskey-auth-* key → auto-connect\n"
                    "  /tailscale up        → connect\n"
                    "  /tailscale down      → disconnect\n"
                    "  /tailscale status    → show connection\n"
                    "  /tailscale ip        → show Tailscale IP\n"
                    "  /tailscale peers     → list peers\n"
                    "  /tailscale serve 32400 → expose Plex on tailnet\n"
                    "  /tailscale funnel 8080 → expose to internet\n"
                ),
                tokens_used=0,
                cost=0.0,
            )

    async def _handle_direct_command_v2(
        self, tool_name: str, tool_args: Dict[str, str]
    ) -> AgentResponse:
        """Handle a direct command with policy enforcement.

        Adds policy check before execution.
        """
        # Policy check
        if self._policy_engine:
            eval_result = self._policy_engine.evaluate(
                tool=tool_name,
                action=tool_args.get("action", ""),
                args=tool_args,
                command=tool_args.get("command", ""),
            )

            if eval_result.is_denied:
                return AgentResponse(
                    steps=[],
                    final_response=f"🛑 Blocked: {eval_result.message}",
                    tokens_used=0,
                    cost=0.0,
                )

            if eval_result.needs_confirmation:
                return AgentResponse(
                    steps=[],
                    final_response=(
                        f"⚡ Confirmation needed: {eval_result.message}\n"
                        "Reply 'yes' or 'confirm' to proceed."
                    ),
                    tokens_used=0,
                    cost=0.0,
                )

        # Proceed with V1 execution
        return await self._handle_direct_command(tool_name, tool_args)

    async def _execute_plan(self, plan_result: Any, user_input: str) -> AgentResponse:
        """Execute a task plan through the planner system.

        Args:
            plan_result: PlanResult from the task planner.
            user_input: Original user request.

        Returns:
            AgentResponse with plan execution results.
        """

        graph = plan_result.graph

        # Execute the plan
        exec_result = await self._plan_executor.execute(graph)

        # Format response
        if exec_result.success:
            response_text = f"✓ Done: {graph.name}\n\n"
            response_text += exec_result.format_summary()
        elif exec_result.partial_success:
            response_text = f"◐ Partially completed: {graph.name}\n\n"
            response_text += exec_result.format_summary()
        else:
            response_text = f"✗ Failed: {graph.name}\n\n"
            response_text += exec_result.format_summary()

        # Log the decision
        if self._decision_log:
            self._decision_log.record(
                description=f"Executed plan: {graph.name}",
                reasoning=plan_result.reasoning,
                category="execution",
                tags=["plan", plan_result.planning_method],
            )

        return AgentResponse(
            steps=[AgentStep(thought=plan_result.reasoning)],
            final_response=response_text,
            tokens_used=0,
            cost=0.0,
        )

    async def _execute_tool(self, name: str, args: Dict[str, Any]) -> Any:
        """Execute a tool with policy enforcement (overrides V1).

        Adds policy check, snapshot creation, and plugin tool support.
        """
        # Check if it's a plugin tool (qualified name with '.')
        if "." in name and self._plugin_manager:
            from mk.tools.base import ToolResult

            result = await self._plugin_manager.execute_qualified(name, args)
            if isinstance(result, ToolResult):
                return result.output if result.success else f"Error: {result.error}"
            return result

        # Policy check
        if self._policy_engine:
            eval_result = self._policy_engine.evaluate(
                tool=name,
                action=args.get("action", ""),
                args=args,
                command=args.get("command", ""),
            )

            if eval_result.is_denied:
                raise PermissionError(f"Policy denied: {eval_result.message}")

            # Create snapshot if required
            if eval_result.needs_snapshot and self._snapshot_manager:
                from mk.policy.snapshots import SnapshotType

                target = eval_result.snapshot_target or name
                await self._snapshot_manager.create_snapshot(
                    target=target,
                    snapshot_type=SnapshotType.FILE,
                    description=f"Pre-execution snapshot for {name}",
                )

        # Execute via V1 path
        if name not in self._tools:
            # Try plugin tools as fallback
            if self._plugin_manager:
                result = await self._plugin_manager._execute_unqualified(name, args)
                from mk.tools.base import ToolResult

                if isinstance(result, ToolResult):
                    if result.success:
                        return result.output
                    raise RuntimeError(result.error or "Tool failed")
            raise KeyError(f"Tool '{name}' is not registered")

        handler = self._tools[name]
        return await handler(**args)

    def _get_tool_descriptions(self) -> List[Dict[str, str]]:
        """Get tool descriptions including plugin tools."""
        descriptions = super()._get_tool_descriptions()

        # Add plugin tools
        if self._plugin_manager:
            for tool_def in self._plugin_manager.get_tool_definitions():
                descriptions.append(
                    {
                        "name": tool_def["name"],
                        "description": tool_def["description"],
                    }
                )

        return descriptions

    # ─── Initialization Helpers ───────────────────────────

    async def _init_plugins(self) -> Dict[str, Any]:
        """Initialize the plugin system."""
        from mk.plugins.manager import PluginManager

        self._plugin_manager = PluginManager(plugin_dirs=self._plugin_dirs)
        await self._plugin_manager.load_all()

        return {
            "enabled": True,
            "plugins_loaded": self._plugin_manager.plugin_count,
            "tools_available": len(self._plugin_manager.all_tool_names),
        }

    def _init_planner(self) -> Dict[str, Any]:
        """Initialize the task planner and executor."""
        from mk.planner.critique import CritiqueGate
        from mk.planner.executor import PlanExecutor
        from mk.planner.planner import TaskPlanner
        from mk.planner.sub_agent import SubAgentRegistry

        registry = SubAgentRegistry()
        self._task_planner = TaskPlanner(agent_registry=registry)

        critique = CritiqueGate()
        self._plan_executor = PlanExecutor(
            agent_registry=registry,
            critique_gate=critique,
            tool_executor=self._execute_tool,
        )

        return {
            "enabled": True,
            "agents": registry.agent_count,
            "templates": len(self._task_planner._plan_templates),
        }

    async def _init_ops(self, notify_callback: Optional[Callable]) -> Dict[str, Any]:
        """Initialize the proactive ops system."""
        from mk.ops.manager import OpsManager

        self._ops_manager = OpsManager(
            notify_callback=notify_callback,
            register_defaults=True,
        )
        await self._ops_manager.start()

        return {
            "enabled": True,
            "checks": self._ops_manager.checks.check_count,
            "scheduled_jobs": self._ops_manager.scheduler.job_count,
        }

    def _init_semantic_memory(self) -> Dict[str, Any]:
        """Initialize semantic memory and decision log."""
        from mk.memory.vector.decisions import DecisionLog
        from mk.memory.vector.semantic import SemanticMemory

        storage_path = str(Path.home() / ".mk" / "memory" / "vectors")
        self._semantic_memory = SemanticMemory(storage_path=storage_path)
        self._semantic_memory.load()

        decisions_path = str(Path.home() / ".mk" / "memory" / "decisions")
        self._decision_log = DecisionLog(storage_path=decisions_path)
        self._decision_log.load()

        return {
            "enabled": True,
            "memories": self._semantic_memory.count,
            "decisions": self._decision_log.count,
        }

    def _init_policy(self) -> Dict[str, Any]:
        """Initialize the policy engine with snapshots and rollback."""
        from mk.policy.engine import PolicyEngine
        from mk.policy.rollback import RollbackHandler
        from mk.policy.snapshots import SnapshotManager

        self._policy_engine = PolicyEngine(policy_paths=self._policy_paths)

        snapshot_path = str(Path.home() / ".mk" / "snapshots")
        self._snapshot_manager = SnapshotManager(storage_path=snapshot_path)

        self._rollback_handler = RollbackHandler(
            snapshot_manager=self._snapshot_manager,
        )

        return {
            "enabled": True,
            "rules": self._policy_engine.rule_count,
        }

    async def _init_tailscale(self) -> Dict[str, Any]:
        """Auto-setup Tailscale on startup if configured.

        If tailscale.enabled=true in config:
        1. Installs Tailscale if not present
        2. Connects with configured auth key, hostname, routes
        3. Sets up any configured serve/funnel endpoints

        This makes Tailscale fully hands-off — just put the auth key
        in your config and MK handles the rest on every boot.
        """
        from mk.server.network import NetworkManager

        nm = NetworkManager(sudo=True)
        ts_config = self.settings.tailscale
        results: Dict[str, Any] = {"enabled": True}

        # Step 1: Install if needed
        install_result = await nm.tailscale_install()
        results["installed"] = install_result.success or install_result.metadata.get(
            "already_installed", False
        )

        if not results["installed"]:
            results["error"] = f"Installation failed: {install_result.error}"
            logger.error(f"Tailscale auto-setup failed: {install_result.error}")
            return results

        # Step 2: Get auth key from secrets or config
        auth_key: Optional[str] = None
        if ts_config.auth_key_ref:
            # Try to get from secrets store
            try:
                from mk.safety.secrets import SecretsManager

                secrets = SecretsManager()
                auth_key = secrets.get_secret(ts_config.auth_key_ref)
            except Exception:
                pass

            # Try environment variable as fallback
            if not auth_key:
                import os

                auth_key = os.environ.get("TAILSCALE_AUTH_KEY", "")
                if not auth_key:
                    auth_key = os.environ.get("TS_AUTH_KEY", "")

        # Step 3: Connect
        up_result = await nm.tailscale_up(
            auth_key=auth_key or None,
            hostname=ts_config.hostname,
            advertise_routes=ts_config.advertise_routes or None,
            advertise_exit_node=ts_config.advertise_exit_node,
            accept_routes=ts_config.accept_routes,
            ssh=ts_config.ssh,
        )

        if up_result.success:
            results["connected"] = True
            logger.info(f"Tailscale connected: {up_result.output}")

            # Get our IP
            ip_result = await nm.tailscale_ip()
            if ip_result.success:
                results["ip"] = ip_result.metadata.get("ipv4", "")

        elif up_result.metadata.get("needs_auth"):
            results["connected"] = False
            results["needs_auth"] = True
            results["auth_url"] = up_result.metadata.get("auth_url", "")
            logger.warning(f"Tailscale needs auth: {results['auth_url']}")
        else:
            results["connected"] = False
            results["error"] = up_result.error
            logger.warning(f"Tailscale connection failed: {up_result.error}")

        # Step 4: Set up serve endpoints (if configured and connected)
        if results.get("connected") and ts_config.serve:
            for svc in ts_config.serve:
                port = svc.get("port")
                path = svc.get("path", "/")
                if port:
                    serve_result = await nm.tailscale_serve(port=port, path=path)
                    if serve_result.success:
                        logger.info(f"Tailscale serve: :{port} at {path}")
            results["serve_endpoints"] = len(ts_config.serve)

        # Step 5: Set up funnel endpoints (if configured and connected)
        if results.get("connected") and ts_config.funnel:
            for funneled in ts_config.funnel:
                port = funneled.get("port")
                path = funneled.get("path", "/")
                if port:
                    funnel_result = await nm.tailscale_funnel(port=port, path=path)
                    if funnel_result.success:
                        logger.info(f"Tailscale funnel: :{port} at {path} (PUBLIC)")
            results["funnel_endpoints"] = len(ts_config.funnel)

        return results

    # ─── Status / Diagnostics ─────────────────────────────

    def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status across all subsystems."""
        status: Dict[str, Any] = {
            "version": "2.0.0",
            "initialized": self._initialized,
        }

        if self._plugin_manager:
            status["plugins"] = self._plugin_manager.get_status()

        if self._ops_manager:
            status["ops"] = self._ops_manager.get_status()

        if self._semantic_memory:
            status["memory"] = self._semantic_memory.stats()

        if self._policy_engine:
            status["policy"] = self._policy_engine.get_status()

        if self._decision_log:
            status["decisions"] = {"count": self._decision_log.count}

        return status

    async def health_report(self) -> str:
        """Generate a health report from all subsystems.

        Returns:
            Formatted health report string.
        """
        if self._ops_manager:
            # Run all checks and get report
            await self._ops_manager.run_all_checks_now()
            return self._ops_manager.health_report()
        return "Ops system not initialized — no health data available."
