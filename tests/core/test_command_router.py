"""Unit tests for the command router."""

from __future__ import annotations

import pytest

from mk.core.command_router import CommandRouter, CommandPattern, RouteResult


class TestCommandRouter:
    """Tests for CommandRouter."""

    def setup_method(self) -> None:
        """Set up router for each test."""
        self.router = CommandRouter()

    def test_restart_command(self) -> None:
        """Restart commands are routed directly."""
        result = self.router.route("restart sonarr")
        assert result.is_direct is True
        assert result.tool_name == "restart_service"
        assert result.tool_args["target"] == "sonarr"

    def test_reboot_command(self) -> None:
        """Reboot commands are routed as restart."""
        result = self.router.route("reboot media-server")
        assert result.is_direct is True
        assert result.tool_name == "restart_service"
        assert result.tool_args["target"] == "media-server"

    def test_check_status_command(self) -> None:
        """Status check commands are routed directly."""
        result = self.router.route("status of plex")
        assert result.is_direct is True
        assert result.tool_name == "check_status"
        assert result.tool_args["target"] == "plex"

    def test_is_running_command(self) -> None:
        """'Is X running?' commands are routed directly."""
        result = self.router.route("is sonarr running?")
        assert result.is_direct is True
        assert result.tool_name == "check_status"
        assert result.tool_args["target"] == "sonarr"

    def test_stop_command(self) -> None:
        """Stop commands are routed directly."""
        result = self.router.route("stop radarr")
        assert result.is_direct is True
        assert result.tool_name == "stop_service"
        assert result.tool_args["target"] == "radarr"

    def test_start_command(self) -> None:
        """Start commands are routed directly."""
        result = self.router.route("start plex")
        assert result.is_direct is True
        assert result.tool_name == "start_service"
        assert result.tool_args["target"] == "plex"

    def test_complex_query_not_routed(self) -> None:
        """Complex questions are not routed directly."""
        result = self.router.route("What movies were added this week?")
        assert result.is_direct is False

    def test_reasoning_query_not_routed(self) -> None:
        """Questions requiring reasoning are not routed."""
        result = self.router.route("Why is my media server slow?")
        assert result.is_direct is False

    def test_multi_sentence_not_routed(self) -> None:
        """Multi-sentence inputs are not routed directly."""
        result = self.router.route(
            "I want to set up a new download client. "
            "Can you help me configure transmission?"
        )
        assert result.is_direct is False

    def test_case_insensitive(self) -> None:
        """Command matching is case-insensitive."""
        result = self.router.route("RESTART Sonarr")
        assert result.is_direct is True
        assert result.tool_name == "restart_service"

    def test_is_complex_query_method(self) -> None:
        """is_complex_query correctly identifies complex inputs."""
        assert self.router.is_complex_query("Tell me about my setup") is True
        assert self.router.is_complex_query("restart plex") is False

    def test_register_custom_pattern(self) -> None:
        """Custom patterns can be registered."""
        self.router.register_pattern(
            CommandPattern(
                name="deploy",
                patterns=[r"^deploy\s+(\w+)"],
                tool_name="deploy_service",
                description="Deploy a service",
            )
        )

        result = self.router.route("deploy webapp")
        assert result.is_direct is True
        assert result.tool_name == "deploy_service"
        assert result.tool_args["target"] == "webapp"

    def test_registered_commands_list(self) -> None:
        """Can list all registered commands."""
        commands = self.router.registered_commands
        assert len(commands) >= 4  # At least the defaults
        names = [c[0] for c in commands]
        assert "restart_service" in names
        assert "check_status" in names
        assert "stop_service" in names
        assert "start_service" in names

    def test_check_status_shorthand(self) -> None:
        """'check status' shorthand works."""
        result = self.router.route("check status of media-server")
        assert result.is_direct is True
        assert result.tool_name == "check_status"

    def test_how_is_pattern(self) -> None:
        """'how is X?' pattern is routed directly."""
        result = self.router.route("how is plex?")
        assert result.is_direct is True
        assert result.tool_name == "check_status"
        assert result.tool_args["target"] == "plex"

    def test_confidence_score(self) -> None:
        """Matched commands have high confidence."""
        result = self.router.route("restart nginx")
        assert result.confidence >= 0.8

        result = self.router.route("Tell me a story")
        assert result.confidence < 0.8
