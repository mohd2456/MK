"""MK Media Organizer — Sort chaos into Plex-perfect structure.

Takes a disaster folder full of mixed movies, TV shows, and anime
and organizes everything into proper Plex-compatible naming:

Movies:  Title (Year)/Title (Year).ext
TV:      Show Name/Season XX/Show Name - SXXEXX - Episode Title.ext
Anime:   Show Name/Season XX/Show Name - SXXEXX.ext

Handles the worst naming conventions:
- Scene releases: Show.Name.S01E05.720p.HDTV.x264-GROUP
- Anime batches: [SubsPlease] Jujutsu Kaisen - 01 (1080p).mkv
- Messy renames: my movie 2024 hdrip.mkv
- Nested folders: Movie (2024)/CD1/movie.avi
- Multi-episode: Show S01E01-E03.mkv
"""

from mk.plugins.media_organizer.parser import MediaParser, ParsedMedia, MediaType
from mk.plugins.media_organizer.normalizer import MediaNormalizer, PlexPath
from mk.plugins.media_organizer.scanner import FolderScanner, ScanResult
from mk.plugins.media_organizer.organizer import MediaOrganizer, OrganizePlan, MoveAction

__all__ = [
    "MediaParser",
    "ParsedMedia",
    "MediaType",
    "MediaNormalizer",
    "PlexPath",
    "FolderScanner",
    "ScanResult",
    "MediaOrganizer",
    "OrganizePlan",
    "MoveAction",
]
