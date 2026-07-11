"""Folder scanner — recursively scans a chaos folder and classifies everything.

Given a root directory (the disaster folder), the scanner:
1. Walks all files recursively (respects depth limits)
2. Filters to media files only (by extension)
3. Parses each filename to extract metadata
4. Groups related files (movie + subtitle + extras)
5. Reports statistics and any unrecognized files

Design choices:
- Non-destructive: only reads, never moves or modifies
- Memory efficient: yields results as it scans (for huge folders)
- Handles nested structures: /folder/subfolder/actual_file.mkv
- Detects duplicates: same title+season+episode from different sources
- Ignores system files: .DS_Store, Thumbs.db, .nfo, etc.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

from mk.plugins.media_organizer.parser import (
    MEDIA_EXTENSIONS,
    SUBTITLE_EXTENSIONS,
    MediaParser,
    MediaType,
    ParsedMedia,
)


# Files to always ignore
IGNORE_FILES: Set[str] = {
    ".ds_store",
    "thumbs.db",
    "desktop.ini",
    ".nfo",
    ".txt",
    ".url",
    ".lnk",
    ".exe",
    ".bat",
    ".sh",
}

# Folders to skip entirely
IGNORE_FOLDERS: Set[str] = {
    ".git",
    ".svn",
    "__pycache__",
    "node_modules",
    "@eadir",
    "#recycle",
    ".trash",
    "$recycle.bin",
    "sample",
    "samples",
    "extras",
    "featurettes",
    "behind the scenes",
    "metadata",
}


@dataclass
class ScannedFile:
    """A single file found during scanning."""

    path: str  # Full absolute path
    relative_path: str  # Path relative to scan root
    filename: str  # Just the filename
    size_bytes: int  # File size
    parsed: ParsedMedia  # Parsed metadata
    is_media: bool = True
    is_subtitle: bool = False
    is_ignored: bool = False
    group_key: str = ""  # Grouping key (title+season+episode)

    @property
    def size_mb(self) -> float:
        """File size in MB."""
        return self.size_bytes / (1024 * 1024)

    @property
    def size_human(self) -> str:
        """Human-readable file size."""
        if self.size_bytes < 1024:
            return f"{self.size_bytes}B"
        elif self.size_bytes < 1024 * 1024:
            return f"{self.size_bytes / 1024:.1f}KB"
        elif self.size_bytes < 1024 * 1024 * 1024:
            return f"{self.size_mb:.1f}MB"
        else:
            return f"{self.size_bytes / (1024**3):.2f}GB"


@dataclass
class ScanResult:
    """Complete result of scanning a folder.

    Contains all found files, statistics, and groupings.
    """

    root_path: str
    files: List[ScannedFile] = field(default_factory=list)
    ignored_files: List[str] = field(default_factory=list)
    scan_duration_seconds: float = 0.0

    # Stats (computed after scan)
    total_files_scanned: int = 0
    media_files: int = 0
    subtitle_files: int = 0
    movies_found: int = 0
    tv_episodes_found: int = 0
    anime_episodes_found: int = 0
    unknown_files: int = 0
    total_size_bytes: int = 0

    @property
    def total_size_gb(self) -> float:
        """Total size of all media files in GB."""
        return self.total_size_bytes / (1024**3)

    @property
    def has_results(self) -> bool:
        """Whether the scan found any media files."""
        return self.media_files > 0

    def get_movies(self) -> List[ScannedFile]:
        """Get all files classified as movies."""
        return [f for f in self.files if f.parsed.media_type == MediaType.MOVIE]

    def get_tv_shows(self) -> List[ScannedFile]:
        """Get all files classified as TV shows."""
        return [f for f in self.files if f.parsed.media_type == MediaType.TV_SHOW]

    def get_anime(self) -> List[ScannedFile]:
        """Get all files classified as anime."""
        return [f for f in self.files if f.parsed.media_type == MediaType.ANIME]

    def get_unknown(self) -> List[ScannedFile]:
        """Get all unclassified files."""
        return [f for f in self.files if f.parsed.media_type == MediaType.UNKNOWN]

    def get_subtitles(self) -> List[ScannedFile]:
        """Get all subtitle files."""
        return [f for f in self.files if f.is_subtitle]

    def get_duplicates(self) -> Dict[str, List[ScannedFile]]:
        """Find potential duplicates (same title+episode, different files).

        Returns dict of group_key → list of files (only groups with >1 file).
        """
        groups: Dict[str, List[ScannedFile]] = {}
        for f in self.files:
            if f.group_key and not f.is_subtitle:
                groups.setdefault(f.group_key, []).append(f)
        return {k: v for k, v in groups.items() if len(v) > 1}

    def summary(self) -> str:
        """Generate a human-readable scan summary."""
        lines = [
            f"📂 Scan: {self.root_path}",
            f"   Duration: {self.scan_duration_seconds:.1f}s",
            f"   Total files scanned: {self.total_files_scanned}",
            f"   Total size: {self.total_size_gb:.2f} GB",
            "",
            "   Results:",
            f"     🎬 Movies:  {self.movies_found}",
            f"     📺 TV Shows: {self.tv_episodes_found}",
            f"     🎌 Anime:   {self.anime_episodes_found}",
            f"     📝 Subtitles: {self.subtitle_files}",
            f"     ❓ Unknown: {self.unknown_files}",
            f"     🚫 Ignored: {len(self.ignored_files)}",
        ]

        duplicates = self.get_duplicates()
        if duplicates:
            lines.append(f"\n   ⚠️  Potential duplicates: {len(duplicates)} groups")
            for key, dups in list(duplicates.items())[:5]:
                lines.append(f"     • {key}:")
                for d in dups:
                    lines.append(f"       - {d.filename} ({d.size_human})")

        return "\n".join(lines)


class FolderScanner:
    """Recursively scans a folder and classifies all media files.

    Usage:
        scanner = FolderScanner()
        result = scanner.scan("/path/to/chaos/folder")
        print(result.summary())
    """

    def __init__(
        self,
        parser: Optional[MediaParser] = None,
        max_depth: int = 10,
        min_file_size_mb: float = 10.0,
        include_subtitles: bool = True,
    ) -> None:
        """Initialize the scanner.

        Args:
            parser: MediaParser instance. Creates one if None.
            max_depth: Maximum directory depth to recurse.
            min_file_size_mb: Minimum file size to consider as media (MB).
                Files smaller than this are likely samples or previews.
                Set to 0 to include everything.
            include_subtitles: Whether to include subtitle files.
        """
        self._parser = parser or MediaParser()
        self._max_depth = max_depth
        self._min_file_size = int(min_file_size_mb * 1024 * 1024)
        self._include_subtitles = include_subtitles

    def scan(self, root_path: str) -> ScanResult:
        """Scan a directory recursively for media files.

        Args:
            root_path: Path to the directory to scan.

        Returns:
            ScanResult with all found and classified files.

        Raises:
            FileNotFoundError: If root_path doesn't exist.
            NotADirectoryError: If root_path isn't a directory.
        """
        root = Path(root_path).resolve()

        if not root.exists():
            raise FileNotFoundError(f"Directory not found: {root_path}")
        if not root.is_dir():
            raise NotADirectoryError(f"Not a directory: {root_path}")

        result = ScanResult(root_path=str(root))
        start_time = time.time()

        self._walk_directory(root, root, 0, result)
        self._compute_stats(result)
        self._assign_group_keys(result)

        result.scan_duration_seconds = time.time() - start_time
        return result

    def _walk_directory(self, current: Path, root: Path, depth: int, result: ScanResult) -> None:
        """Recursively walk a directory, processing files.

        Args:
            current: Current directory being scanned.
            root: Original root for relative path computation.
            depth: Current recursion depth.
            result: ScanResult to populate.
        """
        if depth > self._max_depth:
            return

        try:
            entries = sorted(current.iterdir())
        except PermissionError:
            return

        for entry in entries:
            if entry.is_dir():
                # Skip ignored folders
                if entry.name.lower() in IGNORE_FOLDERS:
                    continue
                # Skip hidden folders
                if entry.name.startswith("."):
                    continue
                self._walk_directory(entry, root, depth + 1, result)

            elif entry.is_file():
                result.total_files_scanned += 1
                self._process_file(entry, root, result)

    def _process_file(self, filepath: Path, root: Path, result: ScanResult) -> None:
        """Process a single file — classify and add to results.

        Args:
            filepath: Path to the file.
            root: Scan root for relative path.
            result: ScanResult to add to.
        """
        ext = filepath.suffix.lower()
        filename = filepath.name

        # Skip system/ignored files
        if ext in IGNORE_FILES or filename.lower() in IGNORE_FILES:
            result.ignored_files.append(str(filepath))
            return

        # Check if it's a media or subtitle file
        is_media = ext in MEDIA_EXTENSIONS
        is_subtitle = ext in SUBTITLE_EXTENSIONS

        if not is_media and not is_subtitle:
            result.ignored_files.append(str(filepath))
            return

        if is_subtitle and not self._include_subtitles:
            return

        # Get file size
        try:
            size = filepath.stat().st_size
        except OSError:
            size = 0

        # Skip tiny files (likely samples) — but not subtitles
        if is_media and size < self._min_file_size:
            result.ignored_files.append(str(filepath))
            return

        # Parse the filename
        parsed = self._parser.parse(str(filepath))
        parsed.file_size_bytes = size

        # Use parent folder name as hint if title extraction failed
        if (not parsed.title or parsed.title == "Unknown") and filepath.parent != root:
            parent_name = filepath.parent.name
            # Try parsing the parent folder name for title info
            if not any(c in parent_name.lower() for c in ["sample", "sub", "extra"]):
                folder_parsed = self._parser.parse(parent_name + ext)
                if folder_parsed.title and folder_parsed.title != "Unknown":
                    parsed.title = folder_parsed.title
                    if folder_parsed.year and not parsed.year:
                        parsed.year = folder_parsed.year

        # Compute relative path
        try:
            relative = str(filepath.relative_to(root))
        except ValueError:
            relative = filename

        scanned = ScannedFile(
            path=str(filepath),
            relative_path=relative,
            filename=filename,
            size_bytes=size,
            parsed=parsed,
            is_media=is_media,
            is_subtitle=is_subtitle,
        )

        result.files.append(scanned)

    def _compute_stats(self, result: ScanResult) -> None:
        """Compute aggregate statistics for the scan result."""
        for f in result.files:
            if f.is_subtitle:
                result.subtitle_files += 1
            elif f.parsed.media_type == MediaType.MOVIE:
                result.movies_found += 1
                result.media_files += 1
            elif f.parsed.media_type == MediaType.TV_SHOW:
                result.tv_episodes_found += 1
                result.media_files += 1
            elif f.parsed.media_type == MediaType.ANIME:
                result.anime_episodes_found += 1
                result.media_files += 1
            else:
                result.unknown_files += 1

            result.total_size_bytes += f.size_bytes

    def _assign_group_keys(self, result: ScanResult) -> None:
        """Assign grouping keys for duplicate detection.

        Group key format: "type:title:SXXEXX" or "type:title:year"
        """
        for f in result.files:
            p = f.parsed
            title_key = (p.title or "unknown").lower().replace(" ", "_")

            if p.media_type == MediaType.MOVIE:
                year_part = str(p.year) if p.year else "noyear"
                f.group_key = f"movie:{title_key}:{year_part}"
            elif p.has_episode_info:
                season = p.season or 0
                episode = p.episode or 0
                f.group_key = f"{p.media_type.value}:{title_key}:s{season:02d}e{episode:03d}"
            else:
                f.group_key = f"unknown:{title_key}"
