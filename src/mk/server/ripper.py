"""Disc Ripper - Autonomous Blu-ray/DVD ripping to Plex/Jellyfin.

Insert a disc → MK detects it → rips full quality MKV → names it properly →
moves it to Plex/Jellyfin library folder → triggers library scan → ejects disc.

You do nothing. Just feed it discs.

Open-source tools used:
    MakeMKV (makemkvcon) - Reads Blu-ray/DVD, outputs lossless MKV
    udevadm / lsblk     - Detect disc drive and disc insertion
    blkid               - Read disc label/title
    curl                - Trigger Plex/Jellyfin library scan API

File structure output (Plex/Jellyfin compatible):
    Movies:
        /media/movies/{Title} ({Year})/{Title} ({Year}).mkv
    TV Shows:
        /media/tv/{Show Name}/Season {XX}/{Show Name} - S{XX}E{XX}.mkv

Flow:
    1. Detect disc inserted (poll or udev trigger)
    2. Identify disc (Blu-ray vs DVD, read label)
    3. Rip all titles (or main feature) via MakeMKV → temp dir
    4. Identify movie/show title (from disc label or MakeMKV metadata)
    5. Rename and move to proper Plex/Jellyfin folder structure
    6. Trigger Plex/Jellyfin library scan
    7. Eject disc
    8. Log result
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import List, Optional

from mk.tools.base import ToolResult
from ._shell import safe_quote
from ._run import run_cmd

logger = logging.getLogger(__name__)

# Default paths
DEFAULT_TEMP_DIR = "/tmp/mk-rip"
DEFAULT_MOVIE_DIR = "/media/movies"
DEFAULT_TV_DIR = "/media/tv"


class DiscRipper:
    """Autonomous disc ripper — insert disc, get media in your library.

    Wraps MakeMKV (makemkvcon) for the actual ripping, handles
    file naming/organization for Plex/Jellyfin, and triggers
    library scans when done.
    """

    def __init__(
        self,
        movie_dir: str = DEFAULT_MOVIE_DIR,
        tv_dir: str = DEFAULT_TV_DIR,
        temp_dir: str = DEFAULT_TEMP_DIR,
        drive_device: str = "/dev/sr0",
        plex_url: Optional[str] = None,
        plex_token: Optional[str] = None,
        jellyfin_url: Optional[str] = None,
        jellyfin_api_key: Optional[str] = None,
        rip_mode: str = "main",
        min_title_seconds: int = 600,
    ) -> None:
        """Initialize the disc ripper.

        Args:
            movie_dir: Where movies go (Plex/Jellyfin library root).
            tv_dir: Where TV shows go.
            temp_dir: Temp directory for ripping (before rename/move).
            drive_device: Optical drive device path.
            plex_url: Plex server URL (e.g., http://localhost:32400).
            plex_token: Plex auth token.
            jellyfin_url: Jellyfin server URL (e.g., http://localhost:8096).
            jellyfin_api_key: Jellyfin API key.
            rip_mode: "main" (main feature only) or "all" (all titles).
            min_title_seconds: Minimum title length to rip (filters menus/extras).
        """
        self._movie_dir = movie_dir
        self._tv_dir = tv_dir
        self._temp_dir = temp_dir
        self._drive = drive_device
        self._plex_url = plex_url
        self._plex_token = plex_token
        self._jellyfin_url = jellyfin_url
        self._jellyfin_api_key = jellyfin_api_key
        self._rip_mode = rip_mode
        self._min_title_seconds = min_title_seconds

    # --- Drive Detection ---

    async def detect_drive(self) -> ToolResult:
        """Detect connected optical drives (DVD/Blu-ray).

        Returns:
            ToolResult with drive information.
        """
        rc, out, err = await run_cmd(
            'lsblk -Jno NAME,TYPE,SIZE,MODEL,TRAN | python3 -c "'
            "import json,sys; data=json.load(sys.stdin); "
            "drives=[d for d in data.get('blockdevices',[]) if d.get('type')=='rom']; "
            'print(json.dumps(drives, indent=2))"',
            sudo=False,
        )
        if rc != 0:
            # Fallback: check if device exists
            rc2, out2, _ = await run_cmd(f"test -b {self._drive} && echo 'found'", sudo=False)
            if rc2 == 0:
                return ToolResult(
                    success=True,
                    output=f"Drive detected: {self._drive}",
                    metadata={"drive": self._drive},
                )
            return ToolResult(success=False, error="No optical drive detected")

        return ToolResult(
            success=True,
            output=out if out != "[]" else "No optical drives found",
            metadata={"format": "json"},
        )

    async def disc_status(self) -> ToolResult:
        """Check if a disc is inserted and get its info.

        Returns:
            ToolResult with disc type, label, and title count.
        """
        # Check if disc is present
        rc, out, err = await run_cmd(
            f"blkid {safe_quote(self._drive)} 2>/dev/null",
            sudo=True,
        )
        if rc != 0:
            return ToolResult(
                success=True, output="No disc inserted", metadata={"disc_present": False}
            )

        # Get disc label
        rc, label, _ = await run_cmd(
            f"blkid -o value -s LABEL {safe_quote(self._drive)} 2>/dev/null",
            sudo=True,
        )

        # Determine disc type (BD or DVD)
        rc2, bd_check, _ = await run_cmd(
            "find /dev/disk/by-id/ -name '*BD*' 2>/dev/null | head -1",
            sudo=False,
        )
        disc_type = "bluray" if bd_check else "dvd"

        # Get title count from MakeMKV
        rc3, title_info, _ = await run_cmd(
            "makemkvcon -r info disc:0 2>/dev/null | grep -c '^TINFO'",
            sudo=False,
            timeout=30,
        )
        title_count = int(title_info) if title_info and title_info.isdigit() else 0

        info = {
            "disc_present": True,
            "label": label or "UNKNOWN",
            "type": disc_type,
            "title_count": title_count,
            "device": self._drive,
        }

        return ToolResult(
            success=True,
            output=f"Disc: {label or 'UNKNOWN'} ({disc_type.upper()}, {title_count} titles)",
            metadata=info,
        )

    # --- Ripping ---

    async def rip_disc(
        self,
        title_override: Optional[str] = None,
        year: Optional[int] = None,
        media_type: str = "movie",
        season: Optional[int] = None,
        episodes_start: int = 1,
    ) -> ToolResult:
        """Rip the inserted disc — full autonomous pipeline.

        Steps: detect → rip → rename → move → scan library → eject.

        Args:
            title_override: Override the disc label with this title.
            year: Release year (for movie folder naming).
            media_type: "movie" or "tv".
            season: Season number (for TV shows).
            episodes_start: Starting episode number (for TV shows).

        Returns:
            ToolResult with rip results and final file paths.
        """
        # 1. Check disc is present
        status = await self.disc_status()
        if not status.metadata.get("disc_present"):
            return ToolResult(success=False, error="No disc inserted")

        disc_label = title_override or status.metadata.get("label", "UNKNOWN")
        disc_label = self._clean_title(disc_label)

        logger.info(f"Starting rip: {disc_label} ({media_type})")

        # 2. Prepare temp directory
        rip_dir = f"{self._temp_dir}/{disc_label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        rc, _, err = await run_cmd(f"mkdir -p {safe_quote(rip_dir)}", sudo=False)
        if rc != 0:
            return ToolResult(success=False, error=f"Failed to create temp dir: {err}")

        # 3. Rip with MakeMKV
        rip_result = await self._run_makemkv(rip_dir)
        if not rip_result.success:
            return rip_result

        # 4. Get ripped files
        rc, files_out, _ = await run_cmd(
            f"find {safe_quote(rip_dir)} -name '*.mkv' -type f | sort",
            sudo=False,
        )
        ripped_files = [f.strip() for f in files_out.splitlines() if f.strip()]

        if not ripped_files:
            return ToolResult(success=False, error="Rip produced no MKV files")

        # 5. Filter by minimum duration (skip menus/trailers)
        valid_files = await self._filter_by_duration(ripped_files)
        if not valid_files:
            valid_files = ripped_files  # Fall back to all if filter too aggressive

        # 6. Rename and move to library
        if media_type == "movie":
            final_paths = await self._organize_movie(valid_files, disc_label, year)
        else:
            final_paths = await self._organize_tv(
                valid_files, disc_label, season or 1, episodes_start
            )

        # 7. Trigger library scans
        scan_results = await self._trigger_library_scans()

        # 8. Eject disc
        await self.eject_disc()

        # 9. Cleanup temp
        await run_cmd(f"rm -rf {safe_quote(rip_dir)}", sudo=False)

        output_lines = [f"Rip complete: {disc_label}"]
        output_lines.append(f"Files: {len(final_paths)}")
        for p in final_paths:
            output_lines.append(f"  → {p}")
        if scan_results:
            output_lines.append(f"Library scans: {scan_results}")

        return ToolResult(
            success=True,
            output="\n".join(output_lines),
            side_effects=[
                f"Ripped {len(final_paths)} file(s) from disc",
                "Files placed in library",
                "Library scan triggered",
                "Disc ejected",
            ],
            metadata={
                "title": disc_label,
                "files": final_paths,
                "media_type": media_type,
                "file_count": len(final_paths),
            },
        )

    async def _run_makemkv(self, output_dir: str) -> ToolResult:
        """Run MakeMKV to rip the disc.

        Args:
            output_dir: Directory to output MKV files.

        Returns:
            ToolResult with rip status.
        """
        if self._rip_mode == "main":
            # Rip main feature only (longest title)
            # First, find the main title
            rc, info_out, _ = await run_cmd(
                "makemkvcon -r info disc:0 2>/dev/null",
                sudo=False,
                timeout=60,
            )

            main_title = self._find_main_title(info_out or "")

            rc, out, err = await run_cmd(
                f"makemkvcon mkv disc:0 {main_title} {safe_quote(output_dir)}",
                sudo=False,
                timeout=7200,  # 2 hours max for rip
            )
        else:
            # Rip all titles
            rc, out, err = await run_cmd(
                f"makemkvcon mkv disc:0 all {safe_quote(output_dir)}",
                sudo=False,
                timeout=7200,
            )

        if rc != 0:
            return ToolResult(success=False, error=f"MakeMKV rip failed: {err}")

        return ToolResult(success=True, output=f"MakeMKV rip complete: {out[-200:]}")

    def _find_main_title(self, makemkv_info: str) -> str:
        """Parse MakeMKV info output to find the longest title (main feature).

        Args:
            makemkv_info: Raw output from makemkvcon info.

        Returns:
            Title index as string (default "0" if can't determine).
        """
        # MakeMKV output format: TINFO:title_index,attribute_id,code,value
        # Attribute 9 = duration in seconds
        longest_duration = 0
        longest_title = "0"

        for line in makemkv_info.splitlines():
            if not line.startswith("TINFO:"):
                continue
            parts = line.split(",", 3)
            if len(parts) < 4:
                continue
            title_idx = parts[0].replace("TINFO:", "")
            attr_id = parts[1]
            value = parts[3].strip('"')

            if attr_id == "9":  # Duration
                # Parse HH:MM:SS or seconds
                try:
                    if ":" in value:
                        h, m, s = value.split(":")
                        duration = int(h) * 3600 + int(m) * 60 + int(s)
                    else:
                        duration = int(value)

                    if duration > longest_duration:
                        longest_duration = duration
                        longest_title = title_idx
                except (ValueError, IndexError):
                    continue

        return longest_title

    async def _filter_by_duration(self, files: List[str]) -> List[str]:
        """Filter MKV files by minimum duration (skip menus/extras).

        Args:
            files: List of MKV file paths.

        Returns:
            Files that meet minimum duration.
        """
        valid = []
        for f in files:
            # Use ffprobe to get duration
            rc, out, _ = await run_cmd(
                f"ffprobe -v quiet -show_entries format=duration "
                f"-of csv=p=0 {safe_quote(f)} 2>/dev/null",
                sudo=False,
                timeout=10,
            )
            if rc == 0 and out:
                try:
                    duration = float(out.strip())
                    if duration >= self._min_title_seconds:
                        valid.append(f)
                except ValueError:
                    valid.append(f)  # Keep if can't determine
            else:
                valid.append(f)  # Keep if ffprobe unavailable
        return valid

    # --- File Organization ---

    async def _organize_movie(self, files: List[str], title: str, year: Optional[int]) -> List[str]:
        """Move ripped files to movie library structure.

        Structure: /media/movies/{Title} ({Year})/{Title} ({Year}).mkv

        Args:
            files: Ripped MKV file paths.
            title: Movie title.
            year: Release year.

        Returns:
            List of final file paths.
        """
        year_str = f" ({year})" if year else ""
        folder_name = f"{title}{year_str}"
        dest_dir = f"{self._movie_dir}/{folder_name}"

        await run_cmd(f"mkdir -p {safe_quote(dest_dir)}", sudo=False)

        final_paths = []
        for i, src in enumerate(files):
            if len(files) == 1:
                filename = f"{folder_name}.mkv"
            else:
                # Multiple files: main feature + extras
                filename = f"{folder_name} - Part {i + 1}.mkv"

            dest = f"{dest_dir}/{filename}"
            rc, _, err = await run_cmd(f"mv {safe_quote(src)} {safe_quote(dest)}", sudo=False)
            if rc == 0:
                final_paths.append(dest)
            else:
                logger.debug(f"Failed to move {src} to {dest}: {err}")

        return final_paths

    async def _organize_tv(
        self, files: List[str], show_name: str, season: int, ep_start: int
    ) -> List[str]:
        """Move ripped files to TV show library structure.

        Structure: /media/tv/{Show}/Season {XX}/{Show} - S{XX}E{XX}.mkv

        Args:
            files: Ripped MKV file paths.
            show_name: Show title.
            season: Season number.
            ep_start: Starting episode number.

        Returns:
            List of final file paths.
        """
        season_dir = f"{self._tv_dir}/{show_name}/Season {season:02d}"
        await run_cmd(f"mkdir -p {safe_quote(season_dir)}", sudo=False)

        final_paths = []
        for i, src in enumerate(files):
            ep_num = ep_start + i
            filename = f"{show_name} - S{season:02d}E{ep_num:02d}.mkv"
            dest = f"{season_dir}/{filename}"

            rc, _, err = await run_cmd(f"mv {safe_quote(src)} {safe_quote(dest)}", sudo=False)
            if rc == 0:
                final_paths.append(dest)
            else:
                logger.debug(f"Failed to move {src} to {dest}: {err}")

        return final_paths

    # --- Library Scans ---

    async def _trigger_library_scans(self) -> str:
        """Trigger Plex and/or Jellyfin library scans.

        Returns:
            Summary of scan results.
        """
        results = []

        # Plex scan
        if self._plex_url and self._plex_token:
            rc, _, _ = await run_cmd(
                f"curl -s -X POST "
                f"{safe_quote(self._plex_url)}/library/sections/all/refresh "
                f"-H 'X-Plex-Token: {safe_quote(self._plex_token)}'",
                sudo=False,
                timeout=10,
            )
            results.append("Plex" if rc == 0 else "Plex (failed)")

        # Jellyfin scan
        if self._jellyfin_url and self._jellyfin_api_key:
            rc, _, _ = await run_cmd(
                f"curl -s -X POST "
                f"{safe_quote(self._jellyfin_url)}/Library/Refresh "
                f"-H 'X-Emby-Token: {safe_quote(self._jellyfin_api_key)}'",
                sudo=False,
                timeout=10,
            )
            results.append("Jellyfin" if rc == 0 else "Jellyfin (failed)")

        return ", ".join(results) if results else "No media servers configured"

    # --- Disc Control ---

    async def eject_disc(self) -> ToolResult:
        """Eject the disc from the drive."""
        rc, _, err = await run_cmd(f"eject {safe_quote(self._drive)}", sudo=True)
        if rc != 0:
            return ToolResult(success=False, error=f"Eject failed: {err}")
        return ToolResult(success=True, output="Disc ejected")

    async def close_tray(self) -> ToolResult:
        """Close the disc tray."""
        rc, _, err = await run_cmd(f"eject -t {safe_quote(self._drive)}", sudo=True)
        if rc != 0:
            return ToolResult(success=False, error=f"Close tray failed: {err}")
        return ToolResult(success=True, output="Tray closed")

    # --- Autonomous Watcher ---

    async def watch_for_disc(self) -> ToolResult:
        """Check if a new disc was inserted (for polling in daemon mode).

        This is meant to be called periodically by MK's daemon loop.
        Returns disc info if present, or nothing if empty.

        Returns:
            ToolResult with disc presence info.
        """
        rc, out, _ = await run_cmd(
            f"udevadm info --query=property --name={safe_quote(self._drive)} 2>/dev/null "
            f"| grep -q 'ID_CDROM_MEDIA=1'",
            sudo=False,
        )
        if rc == 0:
            return await self.disc_status()
        return ToolResult(success=True, output="No disc", metadata={"disc_present": False})

    # --- Utilities ---

    def _clean_title(self, raw_label: str) -> str:
        """Clean a disc label into a proper title.

        Disc labels are often like "THE_DARK_KNIGHT" or "BREAKING_BAD_S1_D1".
        Convert to human-readable.

        Args:
            raw_label: Raw disc label string.

        Returns:
            Cleaned title.
        """
        # Replace underscores with spaces
        title = raw_label.replace("_", " ")
        # Remove disc indicators (D1, D2, DISC1, etc.)
        title = re.sub(r"\b(D|DISC)\s*\d+\b", "", title, flags=re.IGNORECASE)
        # Title case
        title = title.strip().title()
        # Clean up multiple spaces
        title = re.sub(r"\s+", " ", title).strip()
        return title

    # --- Configuration ---

    async def get_config(self) -> ToolResult:
        """Show current ripper configuration."""
        config = {
            "drive": self._drive,
            "movie_dir": self._movie_dir,
            "tv_dir": self._tv_dir,
            "temp_dir": self._temp_dir,
            "rip_mode": self._rip_mode,
            "min_title_seconds": self._min_title_seconds,
            "plex_configured": bool(self._plex_url),
            "jellyfin_configured": bool(self._jellyfin_url),
        }
        return ToolResult(
            success=True,
            output=json.dumps(config, indent=2),
            metadata=config,
        )

    async def check_dependencies(self) -> ToolResult:
        """Check if required tools are installed (MakeMKV, ffprobe, eject)."""
        deps = {
            "makemkvcon": "MakeMKV (disc ripping)",
            "ffprobe": "FFmpeg (duration detection)",
            "eject": "eject (disc control)",
            "curl": "curl (API calls)",
        }

        results = []
        all_ok = True
        for cmd, desc in deps.items():
            rc, path, _ = await run_cmd(f"which {cmd} 2>/dev/null", sudo=False)
            if rc == 0:
                results.append(f"  ✓ {desc}: {path}")
            else:
                results.append(f"  ✗ {desc}: NOT FOUND")
                all_ok = False

        # Check drive exists
        rc, _, _ = await run_cmd(f"test -b {self._drive}", sudo=False)
        if rc == 0:
            results.append(f"  ✓ Drive: {self._drive}")
        else:
            results.append(f"  ✗ Drive: {self._drive} NOT FOUND")
            all_ok = False

        output = "Disc Ripper Dependencies:\n" + "\n".join(results)
        return ToolResult(
            success=all_ok,
            output=output,
            metadata={"all_ok": all_ok},
        )
