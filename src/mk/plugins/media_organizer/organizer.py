"""Media organizer engine — plans and executes file organization.

The organizer takes a ScanResult and produces an OrganizePlan:
- Shows exactly what will be moved where (preview)
- Detects conflicts (two files → same destination)
- Supports dry-run mode (plan without executing)
- Moves files safely with rollback capability
- Tracks progress for large operations
- Handles duplicates (keep highest quality)

Safety features:
- Never deletes source files (moves only)
- Creates directories as needed
- Skips files that already exist at destination
- Reports all errors without stopping
- Can undo the last operation
"""

from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from mk.plugins.media_organizer.normalizer import MediaNormalizer, PlexPath
from mk.plugins.media_organizer.parser import MediaParser, MediaType, ParsedMedia
from mk.plugins.media_organizer.scanner import FolderScanner, ScanResult, ScannedFile



class MoveStatus(str, Enum):
    """Status of a single file move operation."""
    PENDING = "pending"
    SUCCESS = "success"
    SKIPPED = "skipped"      # Already exists at destination
    CONFLICT = "conflict"    # Another file targets the same destination
    ERROR = "error"
    UNDONE = "undone"


@dataclass
class MoveAction:
    """A single file move action in the plan."""

    source: str          # Original file path
    destination: str     # Target path (full)
    relative_dest: str   # Relative path (for display)
    parsed: ParsedMedia  # Parsed metadata
    status: MoveStatus = MoveStatus.PENDING
    error: Optional[str] = None
    size_bytes: int = 0
    is_subtitle: bool = False

    @property
    def filename(self) -> str:
        return Path(self.source).name

    @property
    def dest_filename(self) -> str:
        return Path(self.destination).name

    def format_preview(self) -> str:
        """Format this action for preview display."""
        icon = {
            MoveStatus.PENDING: "  ",
            MoveStatus.SUCCESS: "✓ ",
            MoveStatus.SKIPPED: "⊘ ",
            MoveStatus.CONFLICT: "⚠ ",
            MoveStatus.ERROR: "✗ ",
            MoveStatus.UNDONE: "↩ ",
        }[self.status]
        size = f"({self.size_bytes / (1024**3):.2f}GB)" if self.size_bytes > 1024**3 else f"({self.size_bytes / (1024**2):.0f}MB)"
        return f"{icon}{self.filename} {size}\n    → {self.relative_dest}"


@dataclass
class OrganizePlan:
    """Complete plan for organizing a folder.

    Contains all planned moves, conflicts, and statistics.
    Can be previewed before execution.
    """

    source_root: str
    dest_root: str
    actions: List[MoveAction] = field(default_factory=list)
    conflicts: List[Dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    executed: bool = False
    executed_at: Optional[float] = None

    @property
    def total_actions(self) -> int:
        return len(self.actions)

    @property
    def total_size_bytes(self) -> int:
        return sum(a.size_bytes for a in self.actions)

    @property
    def total_size_gb(self) -> float:
        return self.total_size_bytes / (1024**3)

    @property
    def pending_count(self) -> int:
        return sum(1 for a in self.actions if a.status == MoveStatus.PENDING)

    @property
    def success_count(self) -> int:
        return sum(1 for a in self.actions if a.status == MoveStatus.SUCCESS)

    @property
    def error_count(self) -> int:
        return sum(1 for a in self.actions if a.status == MoveStatus.ERROR)

    @property
    def movies(self) -> List[MoveAction]:
        return [a for a in self.actions if a.parsed.media_type == MediaType.MOVIE and not a.is_subtitle]

    @property
    def tv_shows(self) -> List[MoveAction]:
        return [a for a in self.actions if a.parsed.media_type == MediaType.TV_SHOW and not a.is_subtitle]

    @property
    def anime(self) -> List[MoveAction]:
        return [a for a in self.actions if a.parsed.media_type == MediaType.ANIME and not a.is_subtitle]


    def preview(self) -> str:
        """Generate a human-readable preview of the plan."""
        lines = [
            f"📋 Organization Plan",
            f"   Source: {self.source_root}",
            f"   Destination: {self.dest_root}",
            f"   Total files: {self.total_actions}",
            f"   Total size: {self.total_size_gb:.2f} GB",
            "",
        ]

        # Group by type
        if self.movies:
            lines.append(f"🎬 Movies ({len(self.movies)}):")
            for a in sorted(self.movies, key=lambda x: x.relative_dest):
                lines.append(f"  {a.format_preview()}")
            lines.append("")

        if self.tv_shows:
            lines.append(f"📺 TV Shows ({len(self.tv_shows)}):")
            for a in sorted(self.tv_shows, key=lambda x: x.relative_dest):
                lines.append(f"  {a.format_preview()}")
            lines.append("")

        if self.anime:
            lines.append(f"🎌 Anime ({len(self.anime)}):")
            for a in sorted(self.anime, key=lambda x: x.relative_dest):
                lines.append(f"  {a.format_preview()}")
            lines.append("")

        # Subtitles
        subs = [a for a in self.actions if a.is_subtitle]
        if subs:
            lines.append(f"📝 Subtitles ({len(subs)}):")
            for a in subs[:10]:
                lines.append(f"  {a.format_preview()}")
            if len(subs) > 10:
                lines.append(f"  ... and {len(subs) - 10} more")
            lines.append("")

        # Conflicts
        if self.conflicts:
            lines.append(f"⚠️  Conflicts ({len(self.conflicts)}):")
            for c in self.conflicts[:5]:
                lines.append(f"  • {c['dest']}: {len(c['sources'])} files target this path")
                for src in c['sources'][:3]:
                    lines.append(f"    - {Path(src).name}")
            lines.append("")

        return "\n".join(lines)

    def execution_summary(self) -> str:
        """Summary after execution."""
        lines = [
            f"✅ Organization Complete",
            f"   Moved: {self.success_count}/{self.total_actions}",
            f"   Errors: {self.error_count}",
            f"   Skipped: {sum(1 for a in self.actions if a.status == MoveStatus.SKIPPED)}",
        ]
        if self.error_count > 0:
            lines.append("\n   Errors:")
            for a in self.actions:
                if a.status == MoveStatus.ERROR:
                    lines.append(f"     ✗ {a.filename}: {a.error}")
        return "\n".join(lines)



class MediaOrganizer:
    """The main organizer engine.

    Ties together scanner, parser, and normalizer to produce
    and execute organization plans.

    Usage:
        organizer = MediaOrganizer(dest_root="/data/media")
        plan = organizer.plan("/path/to/chaos")
        print(plan.preview())
        organizer.execute(plan)  # Actually moves files
    """

    def __init__(
        self,
        dest_root: str = "/data/media",
        movies_folder: str = "movies",
        tv_folder: str = "tv",
        anime_folder: str = "anime",
        min_file_size_mb: float = 10.0,
        copy_mode: bool = False,
    ) -> None:
        """Initialize the organizer.

        Args:
            dest_root: Base destination directory for organized media.
            movies_folder: Subfolder name for movies.
            tv_folder: Subfolder name for TV shows.
            anime_folder: Subfolder name for anime.
            min_file_size_mb: Minimum file size to process (MB).
            copy_mode: If True, copies instead of moves (safer but uses more disk).
        """
        self._dest_root = dest_root
        self._copy_mode = copy_mode
        self._parser = MediaParser()
        self._normalizer = MediaNormalizer(
            movies_folder=movies_folder,
            tv_folder=tv_folder,
            anime_folder=anime_folder,
        )
        self._scanner = FolderScanner(
            parser=self._parser,
            min_file_size_mb=min_file_size_mb,
        )
        self._last_plan: Optional[OrganizePlan] = None

    def plan(self, source_path: str) -> OrganizePlan:
        """Scan a folder and create an organization plan.

        Does NOT move anything — just plans.

        Args:
            source_path: Path to the chaos folder.

        Returns:
            OrganizePlan ready for preview or execution.
        """
        # Scan the source
        scan_result = self._scanner.scan(source_path)

        # Build the plan
        plan = OrganizePlan(
            source_root=source_path,
            dest_root=self._dest_root,
        )

        # Track destinations for conflict detection
        dest_map: Dict[str, List[str]] = {}

        for scanned_file in scan_result.files:
            parsed = scanned_file.parsed

            # Skip unknown files
            if parsed.media_type == MediaType.UNKNOWN and not parsed.is_subtitle:
                continue

            # Normalize to Plex path
            if parsed.is_subtitle:
                plex_path = self._normalizer.normalize_subtitle(parsed)
            else:
                plex_path = self._normalizer.normalize(parsed)

            # Build full destination path
            full_dest = plex_path.full_path(self._dest_root)

            # Track for conflict detection
            dest_map.setdefault(full_dest, []).append(scanned_file.path)

            # Create the action
            action = MoveAction(
                source=scanned_file.path,
                destination=full_dest,
                relative_dest=plex_path.relative_path,
                parsed=parsed,
                size_bytes=scanned_file.size_bytes,
                is_subtitle=parsed.is_subtitle,
            )
            plan.actions.append(action)

        # Detect conflicts
        for dest, sources in dest_map.items():
            if len(sources) > 1:
                plan.conflicts.append({
                    "dest": dest,
                    "sources": sources,
                })
                # Mark conflicting actions
                for action in plan.actions:
                    if action.destination == dest:
                        action.status = MoveStatus.CONFLICT

        # Resolve conflicts: keep the largest file (best quality heuristic)
        self._resolve_conflicts(plan)

        self._last_plan = plan
        return plan


    def execute(
        self,
        plan: OrganizePlan,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> OrganizePlan:
        """Execute an organization plan — actually move/copy files.

        Args:
            plan: The plan to execute.
            progress_callback: Optional callback(current, total, filename)
                called after each file is processed.

        Returns:
            The updated plan with execution results.
        """
        pending = [a for a in plan.actions if a.status == MoveStatus.PENDING]
        total = len(pending)

        for i, action in enumerate(pending):
            try:
                # Create destination directory
                dest_dir = Path(action.destination).parent
                dest_dir.mkdir(parents=True, exist_ok=True)

                # Check if destination already exists
                if Path(action.destination).exists():
                    action.status = MoveStatus.SKIPPED
                    action.error = "File already exists at destination"
                    continue

                # Move or copy
                if self._copy_mode:
                    shutil.copy2(action.source, action.destination)
                else:
                    shutil.move(action.source, action.destination)

                action.status = MoveStatus.SUCCESS

            except Exception as e:
                action.status = MoveStatus.ERROR
                action.error = str(e)

            # Progress callback
            if progress_callback:
                progress_callback(i + 1, total, action.filename)

        plan.executed = True
        plan.executed_at = time.time()
        return plan

    def undo(self, plan: Optional[OrganizePlan] = None) -> int:
        """Undo a previously executed plan (move files back).

        Only works for plans that used move mode (not copy).

        Args:
            plan: Plan to undo. Uses last plan if None.

        Returns:
            Number of files successfully moved back.
        """
        plan = plan or self._last_plan
        if not plan or not plan.executed:
            return 0

        undone = 0
        for action in plan.actions:
            if action.status != MoveStatus.SUCCESS:
                continue

            try:
                if Path(action.destination).exists():
                    # Move back to source
                    source_dir = Path(action.source).parent
                    source_dir.mkdir(parents=True, exist_ok=True)
                    shutil.move(action.destination, action.source)
                    action.status = MoveStatus.UNDONE
                    undone += 1

                    # Clean up empty destination dirs
                    self._cleanup_empty_dirs(Path(action.destination).parent)
            except Exception:
                pass  # Best effort

        return undone

    def _resolve_conflicts(self, plan: OrganizePlan) -> None:
        """Resolve conflicts by keeping the best quality file.

        Heuristic: largest file = best quality (usually true for
        video files — higher bitrate = larger file = better quality).
        """
        for conflict in plan.conflicts:
            dest = conflict["dest"]
            sources = conflict["sources"]

            # Find all actions targeting this destination
            conflicting = [
                a for a in plan.actions
                if a.destination == dest and a.status == MoveStatus.CONFLICT
            ]

            if not conflicting:
                continue

            # Sort by size (largest first)
            conflicting.sort(key=lambda a: a.size_bytes, reverse=True)

            # Keep the largest, skip the rest
            conflicting[0].status = MoveStatus.PENDING  # Winner proceeds
            for loser in conflicting[1:]:
                loser.status = MoveStatus.SKIPPED
                loser.error = f"Duplicate: keeping larger file ({conflicting[0].filename})"

    def _cleanup_empty_dirs(self, directory: Path) -> None:
        """Remove empty directories up the tree (for undo cleanup)."""
        try:
            while directory != Path(self._dest_root):
                if directory.exists() and not any(directory.iterdir()):
                    directory.rmdir()
                    directory = directory.parent
                else:
                    break
        except (OSError, ValueError):
            pass

    def quick_organize(
        self,
        source_path: str,
        dry_run: bool = True,
    ) -> str:
        """One-shot organize: scan, plan, optionally execute.

        Convenience method for simple usage.

        Args:
            source_path: Path to the chaos folder.
            dry_run: If True, only preview (don't move).

        Returns:
            Preview string (if dry_run) or execution summary.
        """
        plan = self.plan(source_path)

        if dry_run:
            return plan.preview()

        self.execute(plan)
        return plan.execution_summary()
