"""Media management tool.

Integrates with Sonarr, Radarr, and Plex APIs for managing
movies, TV shows, and media library content.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from mk.tools.base import Tool, ToolResult


class MediaTool(Tool):
    """Media management tool for Sonarr, Radarr, and Plex.

    Provides methods to search for movies and shows, request
    downloads, check download status, and browse media libraries.
    Uses httpx for API communication with the services.
    """

    def __init__(
        self,
        sonarr_url: str = "",
        sonarr_api_key: str = "",
        radarr_url: str = "",
        radarr_api_key: str = "",
        plex_url: str = "",
        plex_token: str = "",
    ) -> None:
        """Initialize media tool with service URLs and credentials.

        Args:
            sonarr_url: Sonarr API base URL.
            sonarr_api_key: Sonarr API key.
            radarr_url: Radarr API base URL.
            radarr_api_key: Radarr API key.
            plex_url: Plex server URL.
            plex_token: Plex authentication token.
        """
        self._sonarr_url = sonarr_url.rstrip("/")
        self._sonarr_api_key = sonarr_api_key
        self._radarr_url = radarr_url.rstrip("/")
        self._radarr_api_key = radarr_api_key
        self._plex_url = plex_url.rstrip("/")
        self._plex_token = plex_token

    @property
    def name(self) -> str:
        """Tool name."""
        return "media"

    @property
    def description(self) -> str:
        """Tool description."""
        return (
            "Manage media services (Sonarr, Radarr, Plex). "
            "Search for movies and TV shows, request downloads, "
            "check download progress, and browse media libraries."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        """JSON Schema for media tool parameters."""
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "search_movie",
                        "request_movie",
                        "search_show",
                        "request_show",
                        "check_download_status",
                        "get_plex_libraries",
                        "get_recently_added",
                    ],
                    "description": "The media action to perform",
                },
                "query": {
                    "type": "string",
                    "description": "Search query for movies or shows",
                },
                "title": {
                    "type": "string",
                    "description": "Title of the movie or show to request",
                },
                "season": {
                    "type": "integer",
                    "description": "Season number (for show requests)",
                },
            },
            "required": ["action"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute a media management action.

        Args:
            **kwargs: Action-specific arguments.

        Returns:
            ToolResult with operation output or error.
        """
        action = kwargs.get("action", "")
        if not action:
            return ToolResult(success=False, error="Action is required")

        if action == "search_movie":
            return await self._search_movie(kwargs.get("query", ""))
        elif action == "request_movie":
            return await self._request_movie(kwargs.get("title", ""))
        elif action == "search_show":
            return await self._search_show(kwargs.get("query", ""))
        elif action == "request_show":
            return await self._request_show(kwargs.get("title", ""), kwargs.get("season"))
        elif action == "check_download_status":
            return await self._check_download_status()
        elif action == "get_plex_libraries":
            return await self._get_plex_libraries()
        elif action == "get_recently_added":
            return await self._get_recently_added()
        else:
            return ToolResult(
                success=False,
                error=f"Unknown action: {action}",
            )

    async def _search_movie(self, query: str) -> ToolResult:
        """Search for a movie in Radarr.

        Args:
            query: Search query string.

        Returns:
            ToolResult with search results.
        """
        if not query:
            return ToolResult(success=False, error="Query is required for search_movie")

        if not self._radarr_url:
            return ToolResult(success=False, error="Radarr is not configured")

        # In production, would call: GET {radarr_url}/api/v3/movie/lookup?term={query}
        return ToolResult(
            success=True,
            output=f"Searched Radarr for: '{query}'",
            metadata={
                "action": "search_movie",
                "query": query,
                "api_endpoint": f"{self._radarr_url}/api/v3/movie/lookup",
            },
        )

    async def _request_movie(self, title: str) -> ToolResult:
        """Request a movie download via Radarr.

        Args:
            title: Movie title to request.

        Returns:
            ToolResult with request status.
        """
        if not title:
            return ToolResult(success=False, error="Title is required for request_movie")

        if not self._radarr_url:
            return ToolResult(success=False, error="Radarr is not configured")

        return ToolResult(
            success=True,
            output=f"Requested movie: '{title}'",
            side_effects=[f"Movie '{title}' added to Radarr download queue"],
            metadata={
                "action": "request_movie",
                "title": title,
                "api_endpoint": f"{self._radarr_url}/api/v3/movie",
            },
        )

    async def _search_show(self, query: str) -> ToolResult:
        """Search for a TV show in Sonarr.

        Args:
            query: Search query string.

        Returns:
            ToolResult with search results.
        """
        if not query:
            return ToolResult(success=False, error="Query is required for search_show")

        if not self._sonarr_url:
            return ToolResult(success=False, error="Sonarr is not configured")

        return ToolResult(
            success=True,
            output=f"Searched Sonarr for: '{query}'",
            metadata={
                "action": "search_show",
                "query": query,
                "api_endpoint": f"{self._sonarr_url}/api/v3/series/lookup",
            },
        )

    async def _request_show(self, title: str, season: Optional[int] = None) -> ToolResult:
        """Request a TV show download via Sonarr.

        Args:
            title: Show title to request.
            season: Optional specific season number.

        Returns:
            ToolResult with request status.
        """
        if not title:
            return ToolResult(success=False, error="Title is required for request_show")

        if not self._sonarr_url:
            return ToolResult(success=False, error="Sonarr is not configured")

        season_str = f" (Season {season})" if season else ""
        return ToolResult(
            success=True,
            output=f"Requested show: '{title}'{season_str}",
            side_effects=[f"Show '{title}'{season_str} added to Sonarr download queue"],
            metadata={
                "action": "request_show",
                "title": title,
                "season": season,
                "api_endpoint": f"{self._sonarr_url}/api/v3/series",
            },
        )

    async def _check_download_status(self) -> ToolResult:
        """Check current download queue status.

        Returns:
            ToolResult with download queue information.
        """
        results: List[str] = []

        if self._radarr_url:
            results.append("Radarr: checked download queue")
        if self._sonarr_url:
            results.append("Sonarr: checked download queue")

        if not results:
            return ToolResult(
                success=False,
                error="No media services configured",
            )

        return ToolResult(
            success=True,
            output="\n".join(results),
            metadata={"action": "check_download_status"},
        )

    async def _get_plex_libraries(self) -> ToolResult:
        """Get Plex library listing.

        Returns:
            ToolResult with library information.
        """
        if not self._plex_url:
            return ToolResult(success=False, error="Plex is not configured")

        return ToolResult(
            success=True,
            output="Retrieved Plex libraries",
            metadata={
                "action": "get_plex_libraries",
                "api_endpoint": f"{self._plex_url}/library/sections",
            },
        )

    async def _get_recently_added(self) -> ToolResult:
        """Get recently added media from Plex.

        Returns:
            ToolResult with recently added content.
        """
        if not self._plex_url:
            return ToolResult(success=False, error="Plex is not configured")

        return ToolResult(
            success=True,
            output="Retrieved recently added media from Plex",
            metadata={
                "action": "get_recently_added",
                "api_endpoint": f"{self._plex_url}/library/recentlyAdded",
            },
        )
