"""MK - Personal AI Operating System.

Entry point for all MK modes:
- terminal: Interactive REPL (login shell, local)
- daemon: Background service (systemd managed)

The boot sequence runs first, probing hardware/network/storage/services/AI,
then drops into the appropriate mode.

Power on → Boot → Ready. Just talk.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Optional

from rich.console import Console
from rich.text import Text

from mk.boot import boot_sequence
from mk.config.settings import Settings
from mk.core.engine import MKEngine

console = Console()

# Configure logging — only show warnings+ in terminal, debug to journal in daemon
logging.basicConfig(
    level=logging.WARNING,
    format="%(name)s: %(message)s",
    stream=sys.stderr,
)


# ─── Interactive REPL ─────────────────────────────────────────────────────────


async def repl_loop(engine: MKEngine) -> None:
    """Run the interactive REPL loop.

    This is MK's primary interface. No menus, no buttons.
    You type, MK responds. Natural language to system commands.

    Args:
        engine: Initialized MKEngine instance.
    """
    while True:
        try:
            # Prompt
            console.print("[bold cyan]MK>[/bold cyan] ", end="")
            user_input = await asyncio.get_event_loop().run_in_executor(
                None, input, ""
            )

            # Exit commands
            if user_input.strip().lower() in ("exit", "quit", "bye", "shutdown"):
                console.print("\n[cyan]MK shutting down. See you.[/cyan]")
                break

            # Skip empty
            if not user_input.strip():
                continue

            # Process
            response = await engine.process(user_input)

            # Display
            console.print(f"\n[green]{response.final_response}[/green]")

            # Token/cost info
            if response.tokens_used > 0:
                console.print(
                    f"[dim]({response.tokens_used} tokens, "
                    f"${response.cost:.4f})[/dim]"
                )
            console.print()

        except KeyboardInterrupt:
            console.print("\n[yellow]^C[/yellow]")
            continue
        except EOFError:
            console.print("\n[cyan]MK shutting down.[/cyan]")
            break


# ─── Daemon Mode ──────────────────────────────────────────────────────────────


async def daemon_loop(engine: MKEngine) -> None:
    """Run MK as a background daemon.

    In daemon mode, MK:
    - Monitors system health
    - Responds to Telegram/API messages
    - Executes scheduled tasks
    - Manages backups and services

    Args:
        engine: Initialized MKEngine instance.
    """
    import logging

    logger = logging.getLogger("mk.daemon")
    logger.info("MK daemon running. Waiting for events...")

    # In daemon mode, we keep running and handle events
    # The actual event sources (API, Telegram, timers) will be
    # integrated as they're built out.
    try:
        while True:
            await asyncio.sleep(60)
            # Future: health check loop, event polling, etc.
    except asyncio.CancelledError:
        logger.info("MK daemon shutting down")


# ─── Main Entry Point ─────────────────────────────────────────────────────────


async def main(mode: str = "terminal", config_path: Optional[str] = None) -> None:
    """Main async entry point for MK.

    Runs the boot sequence then enters the requested mode.

    Args:
        mode: Operating mode (terminal or daemon).
        config_path: Path to config YAML.
    """
    # ─── Boot ─────────────────────────────────────────────────
    quiet = mode == "daemon"
    settings, boot_info = await boot_sequence(
        config_path=config_path,
        quiet=quiet,
        mode=mode,
    )

    # Use default settings if config failed
    if settings is None:
        settings = Settings()

    # ─── Initialize Engine ────────────────────────────────────
    engine = MKEngine(settings=settings)
    engine.setup_server_management()

    # Store boot info for the AI to reference
    engine._boot_info = boot_info  # type: ignore[attr-defined]

    # ─── Enter Mode ───────────────────────────────────────────
    if mode == "terminal":
        await repl_loop(engine)
    elif mode == "daemon":
        await daemon_loop(engine)
    else:
        console.print(f"[red]Unknown mode: {mode}[/red]")
        sys.exit(1)


def cli_entry() -> None:
    """CLI entry point for the 'mk' command."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="mk",
        description="MK - Personal AI Operating System",
    )
    parser.add_argument(
        "--mode",
        choices=["terminal", "daemon"],
        default="terminal",
        help="Operating mode (default: terminal)",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config.yaml",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="mk v2.0.0",
    )

    args = parser.parse_args()
    asyncio.run(main(mode=args.mode, config_path=args.config))


if __name__ == "__main__":
    cli_entry()
