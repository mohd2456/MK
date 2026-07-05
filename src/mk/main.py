"""MK CLI entry point.

Starts MK in terminal mode with a Rich-powered interactive REPL.
The terminal IS MK. MK IS the terminal.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from mk.config.settings import load_config
from mk.core.engine import MKEngine


console = Console()


def print_banner() -> None:
    """Print the MK startup banner."""
    banner = Text("MK", style="bold cyan")
    banner.append(" v0.1.0", style="dim")
    banner.append("\nPersonal AI Operating System", style="italic")
    console.print(Panel(banner, border_style="cyan", padding=(1, 2)))
    console.print("[dim]Type 'exit' or 'quit' to stop. Ctrl+C to interrupt.[/dim]\n")


async def repl_loop(engine: MKEngine) -> None:
    """Run the interactive REPL loop.

    Args:
        engine: Initialized MKEngine instance.
    """
    print_banner()

    while True:
        try:
            # Get input
            console.print("[bold cyan]MK>[/bold cyan] ", end="")
            user_input = await asyncio.get_event_loop().run_in_executor(
                None, input, ""
            )

            # Check for exit
            if user_input.strip().lower() in ("exit", "quit", "bye"):
                console.print("\n[cyan]MK shutting down. See you.[/cyan]")
                break

            # Skip empty input
            if not user_input.strip():
                continue

            # Process through engine
            response = await engine.process(user_input)

            # Display response
            console.print(f"\n[green]{response.final_response}[/green]")

            # Show cost info if any
            if response.tokens_used > 0:
                console.print(
                    f"[dim]({response.tokens_used} tokens, "
                    f"${response.cost:.4f})[/dim]"
                )
            console.print()

        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted.[/yellow]")
            continue
        except EOFError:
            console.print("\n[cyan]MK shutting down.[/cyan]")
            break


def cli_entry() -> None:
    """CLI entry point for the 'mk' command."""
    # Handle --help flag
    if "--help" in sys.argv or "-h" in sys.argv:
        console.print("[bold]MK - Personal AI Operating System[/bold]")
        console.print("\nUsage: mk [OPTIONS]")
        console.print("\nOptions:")
        console.print("  --config PATH   Path to config file")
        console.print("  --help, -h      Show this help message")
        console.print("  --version       Show version")
        sys.exit(0)

    if "--version" in sys.argv:
        console.print("mk v0.1.0")
        sys.exit(0)

    # Load config
    config_path: Optional[str] = None
    if "--config" in sys.argv:
        idx = sys.argv.index("--config")
        if idx + 1 < len(sys.argv):
            config_path = sys.argv[idx + 1]

    try:
        settings = load_config(config_path)
    except Exception as e:
        console.print(f"[red]Config error: {e}[/red]")
        console.print("[dim]Using default configuration.[/dim]")
        settings = load_config()

    engine = MKEngine(settings=settings)
    asyncio.run(repl_loop(engine))


if __name__ == "__main__":
    cli_entry()
