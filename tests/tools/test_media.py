"""Tests for media tool with mocked Sonarr/Radarr/Plex responses."""

from __future__ import annotations

import pytest

from mk.tools.media import MediaTool


class TestMediaTool:
    """Tests for the MediaTool class."""

    def _configured_tool(self) -> MediaTool:
        """Create a media tool with all services configured."""
        return MediaTool(
            sonarr_url="http://192.168.1.50:8989",
            sonarr_api_key="test-sonarr-key",
            radarr_url="http://192.168.1.50:7878",
            radarr_api_key="test-radarr-key",
            plex_url="http://192.168.1.50:32400",
            plex_token="test-plex-token",
        )

    def _unconfigured_tool(self) -> MediaTool:
        """Create a media tool with no services configured."""
        return MediaTool()

    def test_tool_properties(self) -> None:
        """Tool has correct name, description, and schema."""
        tool = self._configured_tool()
        assert tool.name == "media"
        assert "Sonarr" in tool.description or "media" in tool.description.lower()
        schema = tool.parameters_schema
        assert "action" in schema["properties"]

    @pytest.mark.asyncio
    async def test_search_movie(self) -> None:
        """search_movie with configured Radarr succeeds."""
        tool = self._configured_tool()
        result = await tool.execute(action="search_movie", query="Inception")
        assert result.success is True
        assert "Inception" in result.output
        assert "api/v3/movie/lookup" in result.metadata.get("api_endpoint", "")

    @pytest.mark.asyncio
    async def test_search_movie_unconfigured(self) -> None:
        """search_movie without Radarr returns error."""
        tool = self._unconfigured_tool()
        result = await tool.execute(action="search_movie", query="Inception")
        assert result.success is False
        assert "not configured" in result.error.lower()

    @pytest.mark.asyncio
    async def test_search_movie_no_query(self) -> None:
        """search_movie without query returns error."""
        tool = self._configured_tool()
        result = await tool.execute(action="search_movie")
        assert result.success is False
        assert "required" in result.error.lower()

    @pytest.mark.asyncio
    async def test_request_movie(self) -> None:
        """request_movie with configured Radarr succeeds."""
        tool = self._configured_tool()
        result = await tool.execute(action="request_movie", title="The Matrix")
        assert result.success is True
        assert "The Matrix" in result.output
        assert len(result.side_effects) > 0

    @pytest.mark.asyncio
    async def test_request_movie_no_title(self) -> None:
        """request_movie without title returns error."""
        tool = self._configured_tool()
        result = await tool.execute(action="request_movie")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_search_show(self) -> None:
        """search_show with configured Sonarr succeeds."""
        tool = self._configured_tool()
        result = await tool.execute(action="search_show", query="Breaking Bad")
        assert result.success is True
        assert "Breaking Bad" in result.output
        assert "api/v3/series/lookup" in result.metadata.get("api_endpoint", "")

    @pytest.mark.asyncio
    async def test_search_show_unconfigured(self) -> None:
        """search_show without Sonarr returns error."""
        tool = self._unconfigured_tool()
        result = await tool.execute(action="search_show", query="Breaking Bad")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_request_show(self) -> None:
        """request_show with configured Sonarr succeeds."""
        tool = self._configured_tool()
        result = await tool.execute(
            action="request_show", title="Game of Thrones", season=1
        )
        assert result.success is True
        assert "Game of Thrones" in result.output
        assert "Season 1" in result.output

    @pytest.mark.asyncio
    async def test_request_show_no_season(self) -> None:
        """request_show without season requests all seasons."""
        tool = self._configured_tool()
        result = await tool.execute(action="request_show", title="Arcane")
        assert result.success is True
        assert "Arcane" in result.output

    @pytest.mark.asyncio
    async def test_check_download_status(self) -> None:
        """check_download_status with configured services succeeds."""
        tool = self._configured_tool()
        result = await tool.execute(action="check_download_status")
        assert result.success is True
        assert "Radarr" in result.output or "Sonarr" in result.output

    @pytest.mark.asyncio
    async def test_check_download_status_unconfigured(self) -> None:
        """check_download_status without services returns error."""
        tool = self._unconfigured_tool()
        result = await tool.execute(action="check_download_status")
        assert result.success is False
        assert "configured" in result.error.lower()

    @pytest.mark.asyncio
    async def test_get_plex_libraries(self) -> None:
        """get_plex_libraries with configured Plex succeeds."""
        tool = self._configured_tool()
        result = await tool.execute(action="get_plex_libraries")
        assert result.success is True
        assert "library/sections" in result.metadata.get("api_endpoint", "")

    @pytest.mark.asyncio
    async def test_get_plex_libraries_unconfigured(self) -> None:
        """get_plex_libraries without Plex returns error."""
        tool = self._unconfigured_tool()
        result = await tool.execute(action="get_plex_libraries")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_get_recently_added(self) -> None:
        """get_recently_added with configured Plex succeeds."""
        tool = self._configured_tool()
        result = await tool.execute(action="get_recently_added")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_get_recently_added_unconfigured(self) -> None:
        """get_recently_added without Plex returns error."""
        tool = self._unconfigured_tool()
        result = await tool.execute(action="get_recently_added")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_unknown_action(self) -> None:
        """Unknown action returns error."""
        tool = self._configured_tool()
        result = await tool.execute(action="delete_everything")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_missing_action(self) -> None:
        """Missing action returns error."""
        tool = self._configured_tool()
        result = await tool.execute(query="test")
        assert result.success is False

    def test_get_definition(self) -> None:
        """get_definition returns proper structure."""
        tool = self._configured_tool()
        definition = tool.get_definition()
        assert definition["name"] == "media"
        assert "parameters" in definition
        actions = definition["parameters"]["properties"]["action"]["enum"]
        assert "search_movie" in actions
        assert "request_show" in actions
        assert "get_plex_libraries" in actions
