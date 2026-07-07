"""Media filename normalizer — converts parsed metadata into Plex paths.

Takes a ParsedMedia result and generates the correct Plex-compatible
directory structure and filename:

Movies:  {library}/Title (Year)/Title (Year).ext
TV:      {library}/Show Name/Season XX/Show Name - SXXEXX - Episode Title.ext
Anime:   {library}/Show Name/Season XX/Show Name - SXXEXX.ext

Rules enforced:
- No illegal filesystem characters: / \\ : * ? \" < > |
- Consistent title casing
- Year always in parentheses for movies
- Season folders always zero-padded (Season 01, not Season 1)
- Episode numbers always zero-padded (S01E01, not S1E1)
- Subtitles placed alongside their media file with language suffix
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from mk.plugins.media_organizer.parser import MediaType, ParsedMedia


# Characters not allowed in filenames (Windows + Linux safe)
ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
# Multiple spaces/dots
MULTI_SPACE = re.compile(r'\s{2,}')
TRAILING_DOTS = re.compile(r'\.+$')


@dataclass
class PlexPath:
    """The computed Plex-compatible path for a media file.

    Contains the full relative path (from library root) split into
    components for flexibility.
    """

    library_folder: str  # "movies", "tv", "anime"
    show_folder: str     # "Title (Year)" or "Show Name"
    season_folder: str   # "" for movies, "Season XX" for TV/anime
    filename: str        # Final filename with extension
    original: str        # Original filename for reference

    @property
    def relative_path(self) -> str:
        """Full relative path from library root."""
        parts = [self.library_folder, self.show_folder]
        if self.season_folder:
            parts.append(self.season_folder)
        parts.append(self.filename)
        return str(Path(*parts))

    @property
    def directory(self) -> str:
        """Directory path (without filename)."""
        parts = [self.library_folder, self.show_folder]
        if self.season_folder:
            parts.append(self.season_folder)
        return str(Path(*parts))

    def full_path(self, base: str) -> str:
        """Get full absolute path given a base directory.

        Args:
            base: Base media directory (e.g., /data/media).

        Returns:
            Full path string.
        """
        return str(Path(base) / self.relative_path)



class MediaNormalizer:
    """Converts ParsedMedia into Plex-compatible file paths.

    Configurable library folder names and base paths.
    Handles all media types with proper naming conventions.
    """

    def __init__(
        self,
        movies_folder: str = "movies",
        tv_folder: str = "tv",
        anime_folder: str = "anime",
        default_year: int = 0,
    ) -> None:
        """Initialize the normalizer.

        Args:
            movies_folder: Library folder name for movies.
            tv_folder: Library folder name for TV shows.
            anime_folder: Library folder name for anime.
            default_year: Year to use when none is detected (0 = omit).
        """
        self._movies_folder = movies_folder
        self._tv_folder = tv_folder
        self._anime_folder = anime_folder
        self._default_year = default_year

    def normalize(self, parsed: ParsedMedia) -> PlexPath:
        """Convert parsed media info into a Plex-compatible path.

        Args:
            parsed: The parsed media metadata.

        Returns:
            PlexPath with the normalized directory structure.
        """
        if parsed.media_type == MediaType.MOVIE:
            return self._normalize_movie(parsed)
        elif parsed.media_type == MediaType.ANIME:
            return self._normalize_anime(parsed)
        elif parsed.media_type == MediaType.TV_SHOW:
            return self._normalize_tv(parsed)
        else:
            # Unknown — treat as movie if it has a year, else TV
            if parsed.year and not parsed.has_episode_info:
                return self._normalize_movie(parsed)
            elif parsed.has_episode_info:
                return self._normalize_tv(parsed)
            else:
                return self._normalize_movie(parsed)

    def normalize_subtitle(self, parsed: ParsedMedia) -> PlexPath:
        """Normalize a subtitle file path.

        Subtitles go alongside their media file with language suffix:
        Movie Title (2024)/Movie Title (2024).en.srt

        Args:
            parsed: The parsed subtitle metadata.

        Returns:
            PlexPath for the subtitle file.
        """
        # Generate the base path as if it were a media file
        base_result = self.normalize(parsed)

        # Replace extension with subtitle lang + ext
        stem = Path(base_result.filename).stem
        lang = parsed.subtitle_lang or "en"
        ext = parsed.file_extension or ".srt"
        subtitle_filename = f"{stem}.{lang}{ext}"

        return PlexPath(
            library_folder=base_result.library_folder,
            show_folder=base_result.show_folder,
            season_folder=base_result.season_folder,
            filename=subtitle_filename,
            original=parsed.original_filename,
        )


    def _normalize_movie(self, parsed: ParsedMedia) -> PlexPath:
        """Normalize a movie into Plex structure.

        Format: movies/Title (Year)/Title (Year).ext
        If no year: movies/Title/Title.ext
        Multi-part: movies/Title (Year)/Title (Year) - Part 1.ext
        """
        title = self._safe_filename(parsed.title or "Unknown")
        year = parsed.year or self._default_year
        ext = parsed.file_extension or ".mkv"

        if year:
            folder_name = f"{title} ({year})"
            base_filename = f"{title} ({year})"
        else:
            folder_name = title
            base_filename = title

        # Handle multi-part movies
        if parsed.is_multi_part and parsed.part_number:
            base_filename += f" - Part {parsed.part_number}"

        filename = f"{base_filename}{ext}"

        return PlexPath(
            library_folder=self._movies_folder,
            show_folder=folder_name,
            season_folder="",
            filename=filename,
            original=parsed.original_filename,
        )

    def _normalize_tv(self, parsed: ParsedMedia) -> PlexPath:
        """Normalize a TV show into Plex structure.

        Format: tv/Show Name/Season XX/Show Name - SXXEXX - Episode Title.ext
        No episode title: tv/Show Name/Season XX/Show Name - SXXEXX.ext
        Multi-ep: tv/Show Name/Season XX/Show Name - SXXEXX-EXX.ext
        """
        title = self._safe_filename(parsed.title or "Unknown Show")
        season = parsed.season or 1
        episode = parsed.episode or 1
        ext = parsed.file_extension or ".mkv"

        # Show folder: just the clean title
        show_folder = title

        # Season folder: Season XX (zero-padded to 2 digits)
        season_folder = f"Season {season:02d}"

        # Filename: Show Name - SXXEXX - Episode Title.ext
        ep_tag = f"S{season:02d}E{episode:02d}"

        # Multi-episode range
        if parsed.episode_end and parsed.episode_end > episode:
            ep_tag += f"-E{parsed.episode_end:02d}"

        # Build filename
        parts = [title, ep_tag]
        if parsed.episode_title:
            ep_title = self._safe_filename(parsed.episode_title)
            parts.append(ep_title)

        filename = " - ".join(parts) + ext

        return PlexPath(
            library_folder=self._tv_folder,
            show_folder=show_folder,
            season_folder=season_folder,
            filename=filename,
            original=parsed.original_filename,
        )

    def _normalize_anime(self, parsed: ParsedMedia) -> PlexPath:
        """Normalize an anime into Plex structure.

        Format: anime/Show Name/Season XX/Show Name - SXXEXX.ext

        Anime uses the same SXXEXX format as TV for Plex compatibility.
        For absolute numbering with high episodes, season stays 01.
        """
        title = self._safe_filename(parsed.title or "Unknown Anime")
        season = parsed.season or 1
        episode = parsed.episode or parsed.absolute_episode or 1
        ext = parsed.file_extension or ".mkv"

        # Show folder
        show_folder = title

        # Season folder
        season_folder = f"Season {season:02d}"

        # For anime with very high absolute episode numbers (>999),
        # use 4-digit episode padding
        if episode > 999:
            ep_tag = f"S{season:02d}E{episode:04d}"
        else:
            ep_tag = f"S{season:02d}E{episode:02d}"

        # Multi-episode
        if parsed.episode_end and parsed.episode_end > episode:
            if parsed.episode_end > 999:
                ep_tag += f"-E{parsed.episode_end:04d}"
            else:
                ep_tag += f"-E{parsed.episode_end:02d}"

        filename = f"{title} - {ep_tag}{ext}"

        return PlexPath(
            library_folder=self._anime_folder,
            show_folder=show_folder,
            season_folder=season_folder,
            filename=filename,
            original=parsed.original_filename,
        )


    def _safe_filename(self, name: str) -> str:
        """Make a string safe for use as a filename.

        Removes illegal characters, normalizes spaces,
        removes trailing dots (Windows issue).

        Args:
            name: Raw string to sanitize.

        Returns:
            Filesystem-safe string.
        """
        # Remove illegal characters
        safe = ILLEGAL_CHARS.sub('', name)
        # Collapse multiple spaces
        safe = MULTI_SPACE.sub(' ', safe)
        # Remove trailing dots (Windows)
        safe = TRAILING_DOTS.sub('', safe)
        # Strip leading/trailing whitespace
        safe = safe.strip()
        # Ensure not empty
        return safe or "Unknown"

    def preview(self, parsed: ParsedMedia) -> str:
        """Generate a human-readable preview of the normalization.

        Args:
            parsed: Parsed media metadata.

        Returns:
            Formatted string showing original → normalized.
        """
        plex_path = self.normalize(parsed)

        icon = {
            MediaType.MOVIE: "🎬",
            MediaType.TV_SHOW: "📺",
            MediaType.ANIME: "🎌",
            MediaType.UNKNOWN: "❓",
        }[parsed.media_type]

        return (
            f"{icon} {parsed.original_filename}\n"
            f"   → {plex_path.relative_path}"
        )
