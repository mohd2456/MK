"""Media file parser — extracts metadata from chaotic filenames.

The parser is the brain of the organizer. Given any filename, it:
1. Classifies it as movie, TV show, or anime
2. Extracts: title, year, season, episode, quality, codec, source
3. Handles every naming convention known to scene/fansub releases

Naming patterns handled:
- Scene:     Show.Name.S01E05.720p.BluRay.x264-GROUP
- Anime sub: [SubsPlease] Jujutsu Kaisen - 01 (1080p) [hash].mkv
- Anime alt: Jujutsu_Kaisen_-_01_[1080p].mkv
- Daily:     Show Name 2024.03.15 Episode Title.mkv
- Absolute:  Show Name - 145.mkv (anime absolute episode)
- Simple:    Movie Name 2024.mkv
- Messy:     movie.name.2024.1080p.web-dl.h265.mkv
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class MediaType(str, Enum):
    """Classification of a media file."""
    MOVIE = "movie"
    TV_SHOW = "tv_show"
    ANIME = "anime"
    UNKNOWN = "unknown"


# File extensions we care about
MEDIA_EXTENSIONS = {
    ".mkv", ".mp4", ".avi", ".m4v", ".wmv", ".flv", ".mov",
    ".ts", ".m2ts", ".webm", ".ogv", ".divx", ".mpg", ".mpeg",
}
SUBTITLE_EXTENSIONS = {
    ".srt", ".sub", ".idx", ".ass", ".ssa", ".vtt", ".sup", ".pgs",
}


# Quality/resolution tags (order matters for matching)
QUALITY_PATTERNS = [
    (r"2160p|4k|uhd", "2160p"),
    (r"1080p|1080i|fhd", "1080p"),
    (r"720p|hd", "720p"),
    (r"480p|sd", "480p"),
    (r"360p", "360p"),
]

# Source tags
SOURCE_PATTERNS = [
    (r"blu-?ray|bdremux|bdrip", "BluRay"),
    (r"web-?dl|webrip|web", "WEB-DL"),
    (r"hdtv|pdtv|dsr", "HDTV"),
    (r"dvdrip|dvd-?r|dvdscr", "DVD"),
    (r"cam-?rip|hdcam|ts-?rip", "CAM"),
    (r"remux", "REMUX"),
]

# Codec tags
CODEC_PATTERNS = [
    (r"x265|h\.?265|hevc", "HEVC"),
    (r"x264|h\.?264|avc", "H.264"),
    (r"av1", "AV1"),
    (r"xvid|divx", "XviD"),
    (r"vp9", "VP9"),
]

# Audio tags
AUDIO_PATTERNS = [
    (r"atmos", "Atmos"),
    (r"truehd", "TrueHD"),
    (r"dts-?hd\.?ma|dts-?hd", "DTS-HD MA"),
    (r"dts", "DTS"),
    (r"dd\+|ddp|e-?ac-?3|eac3", "EAC3"),
    (r"dd5\.?1|ac-?3|ac3", "AC3"),
    (r"aac", "AAC"),
    (r"flac", "FLAC"),
    (r"opus", "Opus"),
]

# Known anime fansub groups (partial list — helps classify as anime)
ANIME_GROUPS = {
    "subsplease", "erai-raws", "horriblesubs", "commie",
    "damedesuyo", "gg", "coalgirls", "hi10", "anime",
    "judas", "ember", "sallysubs", "setsugen", "yameii",
    "cerberus", "tenshi", "anidl", "bonkai77", "kawaiisubs",
    "nyanpasu", "ohys-raws", "leopard-raws", "animetime",
}


# Anime indicators in title/filename
ANIME_INDICATORS = {
    "ova", "ona", "special", "specials", "nced", "ncop",
    "batch", "complete", "dual audio", "multi-sub",
    "jp", "jpn", "japanese", "eng sub", "engsub",
}

# Words that indicate it's NOT a year (to avoid 1080 being parsed as year)
NOT_YEAR_WORDS = {"1080", "720", "480", "2160", "360", "264", "265"}


@dataclass
class ParsedMedia:
    """Result of parsing a media filename.

    Contains all extracted metadata plus confidence in the classification.
    """
    original_filename: str
    media_type: MediaType = MediaType.UNKNOWN
    title: str = ""
    year: Optional[int] = None
    season: Optional[int] = None
    episode: Optional[int] = None
    episode_end: Optional[int] = None  # For multi-ep (E01-E03)
    episode_title: Optional[str] = None
    absolute_episode: Optional[int] = None  # Anime absolute numbering

    # Technical metadata
    quality: Optional[str] = None
    source: Optional[str] = None
    codec: Optional[str] = None
    audio: Optional[str] = None
    release_group: Optional[str] = None

    # Classification metadata
    confidence: float = 0.0  # 0.0 to 1.0
    is_subtitle: bool = False
    subtitle_lang: Optional[str] = None
    is_extra: bool = False  # Behind-the-scenes, trailers, etc.
    is_sample: bool = False
    is_multi_part: bool = False
    part_number: Optional[int] = None

    # Raw parsed data
    file_extension: str = ""
    file_size_bytes: int = 0

    @property
    def has_episode_info(self) -> bool:
        """Whether this has season/episode data (TV/anime indicator)."""
        return self.season is not None or self.episode is not None or self.absolute_episode is not None

    @property
    def is_movie(self) -> bool:
        return self.media_type == MediaType.MOVIE

    @property
    def is_tv(self) -> bool:
        return self.media_type == MediaType.TV_SHOW

    @property
    def is_anime(self) -> bool:
        return self.media_type == MediaType.ANIME



class MediaParser:
    """Parses media filenames into structured metadata.

    The parser uses a multi-stage approach:
    1. Pre-process: strip extension, normalize separators
    2. Extract technical tags (quality, codec, source, group)
    3. Detect episode patterns (S01E01, absolute, daily)
    4. Extract title and year from what remains
    5. Classify type based on all evidence
    """

    def __init__(self) -> None:
        """Initialize the parser with compiled regex patterns."""
        # Episode patterns — ordered by specificity (most specific first)
        self._episode_patterns = self._compile_episode_patterns()
        self._quality_re = [(re.compile(p, re.I), v) for p, v in QUALITY_PATTERNS]
        self._source_re = [(re.compile(p, re.I), v) for p, v in SOURCE_PATTERNS]
        self._codec_re = [(re.compile(p, re.I), v) for p, v in CODEC_PATTERNS]
        self._audio_re = [(re.compile(p, re.I), v) for p, v in AUDIO_PATTERNS]

    def parse(self, filepath: str) -> ParsedMedia:
        """Parse a file path into structured media metadata.

        Args:
            filepath: Full path or just filename.

        Returns:
            ParsedMedia with all extracted information.
        """
        path = Path(filepath)
        filename = path.stem  # Without extension
        ext = path.suffix.lower()

        result = ParsedMedia(
            original_filename=path.name,
            file_extension=ext,
        )

        # Check if it's a media file at all
        if ext not in MEDIA_EXTENSIONS and ext not in SUBTITLE_EXTENSIONS:
            result.media_type = MediaType.UNKNOWN
            return result

        if ext in SUBTITLE_EXTENSIONS:
            result.is_subtitle = True
            # Extract subtitle language from filename
            result.subtitle_lang = self._detect_subtitle_lang(filename)

        # Check for sample files
        if re.search(r'\bsample\b', filename, re.I):
            result.is_sample = True

        # Stage 1: Extract anime fansub group tag [GroupName]
        filename, group_from_brackets = self._extract_bracket_group(filename)
        if group_from_brackets:
            result.release_group = group_from_brackets

        # Stage 2: Extract technical metadata (removes tags from filename)
        filename = self._extract_technical(filename, result)

        # Stage 3: Try episode patterns
        filename = self._extract_episode(filename, result)

        # Stage 4: Extract title and year
        self._extract_title_year(filename, result)

        # Stage 5: Classify media type
        self._classify(result)

        return result


    def parse_batch(self, filepaths: List[str]) -> List[ParsedMedia]:
        """Parse multiple files.

        Args:
            filepaths: List of file paths.

        Returns:
            List of ParsedMedia results.
        """
        return [self.parse(fp) for fp in filepaths]

    def _extract_bracket_group(self, filename: str) -> Tuple[str, Optional[str]]:
        """Extract [GroupName] from anime fansub releases.

        Returns the cleaned filename and the group name (if found).
        """
        # Match [GroupName] at the start
        match = re.match(r'^\[([^\]]+)\]\s*', filename)
        if match:
            group = match.group(1).strip()
            cleaned = filename[match.end():]
            # Check if it's a known anime group or looks like one
            if group.lower() in ANIME_GROUPS or len(group) < 20:
                return cleaned, group
            return cleaned, group

        # Also check for group at end: filename [hash]
        # Remove trailing [hash] (8-char hex)
        filename = re.sub(r'\s*\[[0-9a-fA-F]{6,8}\]\s*$', '', filename)
        return filename, None

    def _extract_technical(self, filename: str, result: ParsedMedia) -> str:
        """Extract quality, source, codec, audio tags from filename.

        Removes matched tags and returns the cleaned filename.
        """
        # Extract release group from end (e.g., -GROUP or .GROUP)
        group_match = re.search(r'[-.]([A-Za-z0-9]+)$', filename)
        if group_match and not result.release_group:
            potential_group = group_match.group(1)
            # Only if it looks like a group (not a common word)
            if (len(potential_group) >= 2 and len(potential_group) <= 15
                    and potential_group.upper() not in {'MKV', 'AVI', 'MP4', 'THE', 'AND'}):
                result.release_group = potential_group
                filename = filename[:group_match.start()]

        # Extract quality
        for pattern, value in self._quality_re:
            if pattern.search(filename):
                result.quality = value
                filename = pattern.sub('', filename)
                break

        # Extract source
        for pattern, value in self._source_re:
            if pattern.search(filename):
                result.source = value
                filename = pattern.sub('', filename)
                break

        # Extract codec
        for pattern, value in self._codec_re:
            if pattern.search(filename):
                result.codec = value
                filename = pattern.sub('', filename)
                break

        # Extract audio
        for pattern, value in self._audio_re:
            if pattern.search(filename):
                result.audio = value
                filename = pattern.sub('', filename)
                break

        return filename


    def _compile_episode_patterns(self) -> List[Tuple[re.Pattern, str]]:
        """Compile episode detection patterns.

        Returns list of (compiled_regex, pattern_name) tuples.
        Ordered by specificity — most specific first.
        """
        patterns = [
            # S01E01-E03 (multi-episode)
            (r'[Ss](\d{1,2})[Ee](\d{1,3})[-–]?[Ee](\d{1,3})', 'multi_ep'),
            # S01E01 (standard)
            (r'[Ss](\d{1,2})[Ee](\d{1,3})', 'standard'),
            # S01.E01 or S01_E01
            (r'[Ss](\d{1,2})[._][Ee](\d{1,3})', 'standard_sep'),
            # 1x01 format
            (r'(\d{1,2})[xX](\d{1,3})', 'x_format'),
            # Season 1 Episode 5 (verbose)
            (r'[Ss]eason\s*(\d{1,2})\s*[Ee]pisode\s*(\d{1,3})', 'verbose'),
            # Daily show: 2024.03.15 or 2024-03-15
            (r'(\d{4})[.\-](\d{2})[.\-](\d{2})', 'daily'),
            # Anime: " - 01" or " - 145" (absolute, preceded by title)
            (r'\s*[-–]\s*(\d{1,4})\s*(?:\(|\[|$|v\d)', 'absolute'),
            # Anime: "E01" without S (sometimes used, up to 4 digits for long anime)
            (r'(?<![Ss])(?:EP?|ep?)(\d{1,4})(?:\s|$|[._\-\[\(])', 'ep_only'),
            # Part number: Part 1, Part.2, pt1, pt.2
            (r'(?:Part|Pt)\.?\s*(\d{1,2})', 'part'),
        ]
        return [(re.compile(p), name) for p, name in patterns]

    def _extract_episode(self, filename: str, result: ParsedMedia) -> str:
        """Try to extract episode/season info from the filename.

        Returns the filename with episode info removed (for title extraction).
        """
        for pattern, ptype in self._episode_patterns:
            match = pattern.search(filename)
            if not match:
                continue

            if ptype == 'multi_ep':
                result.season = int(match.group(1))
                result.episode = int(match.group(2))
                result.episode_end = int(match.group(3))
                return filename[:match.start()]

            elif ptype in ('standard', 'standard_sep'):
                result.season = int(match.group(1))
                result.episode = int(match.group(2))
                return filename[:match.start()]

            elif ptype == 'x_format':
                result.season = int(match.group(1))
                result.episode = int(match.group(2))
                return filename[:match.start()]

            elif ptype == 'verbose':
                result.season = int(match.group(1))
                result.episode = int(match.group(2))
                return filename[:match.start()]

            elif ptype == 'daily':
                # Daily shows — store as season = year, episode from date
                year = int(match.group(1))
                month = int(match.group(2))
                day = int(match.group(3))
                # Only treat as date if it's a valid date range
                if 2000 <= year <= 2030 and 1 <= month <= 12 and 1 <= day <= 31:
                    result.year = year
                    result.season = year
                    # Use ordinal day as episode (not perfect but functional)
                    result.episode = month * 100 + day
                    result.episode_title = f"{year}-{month:02d}-{day:02d}"
                    return filename[:match.start()]

            elif ptype == 'absolute':
                ep_num = int(match.group(1))
                # Sanity check: absolute eps are usually < 2000
                if ep_num < 2000:
                    result.absolute_episode = ep_num
                    result.season = 1  # Default to season 1 for absolute
                    result.episode = ep_num
                    return filename[:match.start()]

            elif ptype == 'ep_only':
                ep_num = int(match.group(1))
                if ep_num < 2000:
                    result.episode = ep_num
                    result.season = 1
                    result.absolute_episode = ep_num
                    return filename[:match.start()]

            elif ptype == 'part':
                result.is_multi_part = True
                result.part_number = int(match.group(1))
                # Don't remove — title extraction still needs the rest

        return filename


    def _extract_title_year(self, filename: str, result: ParsedMedia) -> None:
        """Extract title and year from the remaining filename.

        After episode/technical tags are removed, what's left should be
        the title (possibly with year).
        """
        # Clean up separators
        # Replace dots, underscores with spaces (scene naming)
        cleaned = re.sub(r'[._]', ' ', filename)
        # Remove extra whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        # Remove trailing/leading dashes and brackets
        cleaned = re.sub(r'^[-–\s]+|[-–\s]+$', '', cleaned)

        # Extract year from parentheses BEFORE stripping them: Title (2023)
        paren_year_match = re.search(r'\((\d{4})\)', cleaned)
        if paren_year_match:
            year_str = paren_year_match.group(1)
            if year_str not in NOT_YEAR_WORDS:
                year_val = int(year_str)
                if 1920 <= year_val <= 2030:
                    if result.year is None:
                        result.year = year_val
                    title_part = cleaned[:paren_year_match.start()].strip()
                    if title_part:
                        # Remove any remaining brackets
                        title_part = re.sub(r'\s*[\(\[\{].*?[\)\]\}]\s*', ' ', title_part).strip()
                        result.title = self._clean_title(title_part)
                        return

        # Remove remaining bracket content
        cleaned = re.sub(r'\s*[\(\[\{].*?[\)\]\}]\s*', ' ', cleaned).strip()

        # Try to extract year (4 digits, 1920-2030)
        year_match = re.search(r'\b((?:19|20)\d{2})\b', cleaned)
        if year_match:
            year_str = year_match.group(1)
            if year_str not in NOT_YEAR_WORDS:
                year_val = int(year_str)
                if 1920 <= year_val <= 2030:
                    if result.year is None:
                        result.year = year_val
                    # Title is everything before the year
                    title_part = cleaned[:year_match.start()].strip()
                    if title_part:
                        result.title = self._clean_title(title_part)
                        return
                    # Year at the start — title is after
                    title_part = cleaned[year_match.end():].strip()
                    if title_part:
                        result.title = self._clean_title(title_part)
                        return

        # No year found — entire cleaned string is the title
        if cleaned:
            result.title = self._clean_title(cleaned)
        else:
            # Last resort: use original filename
            result.title = self._clean_title(
                re.sub(r'[._]', ' ', Path(result.original_filename).stem)
            )

    def _clean_title(self, title: str) -> str:
        """Clean up an extracted title.

        - Title case
        - Remove trailing noise (dashes, dots)
        - Fix common issues
        """
        # Remove trailing/leading separators
        title = re.sub(r'^[-–.\s]+|[-–.\s]+$', '', title)
        # Remove common noise words at the end
        title = re.sub(r'\s+(proper|repack|internal|limited|extended|unrated|directors\s*cut)\s*$', '', title, flags=re.I)
        # Collapse whitespace
        title = re.sub(r'\s+', ' ', title).strip()

        if not title:
            return "Unknown"

        # Title case — but preserve all-caps acronyms (FBI, CIA, etc.)
        words = title.split()
        result_words = []
        for word in words:
            if word.isupper() and len(word) <= 4:
                result_words.append(word)  # Keep acronyms
            elif word.islower():
                result_words.append(word.capitalize())
            else:
                result_words.append(word)

        return ' '.join(result_words)


    def _classify(self, result: ParsedMedia) -> None:
        """Classify the media type based on all extracted evidence.

        Decision logic:
        1. Has episode info → TV or Anime
        2. Has anime indicators → Anime
        3. Has year but no episode → likely Movie
        4. Fallback: single file = movie, short title = unknown
        """
        score_movie = 0.0
        score_tv = 0.0
        score_anime = 0.0

        # Episode info strongly suggests TV/Anime
        if result.has_episode_info:
            score_tv += 3.0

        # Absolute episode numbering → anime
        if result.absolute_episode is not None:
            score_anime += 4.0

        # Fansub group → anime
        if result.release_group:
            group_lower = result.release_group.lower()
            if group_lower in ANIME_GROUPS:
                score_anime += 5.0
            # Bracket groups at start are typically anime
            if re.match(r'^[A-Z]', result.release_group or ''):
                score_anime += 0.5

        # Title contains anime indicators
        title_lower = result.title.lower() if result.title else ""
        for indicator in ANIME_INDICATORS:
            if indicator in title_lower:
                score_anime += 2.0
                break

        # Japanese characters in title → anime
        if result.title and re.search(r'[\u3000-\u9fff\uff00-\uffef]', result.title):
            score_anime += 5.0

        # Year without episode → movie
        if result.year and not result.has_episode_info:
            score_movie += 3.0

        # No season/episode info at all → likely movie
        if not result.has_episode_info:
            score_movie += 2.0

        # Common movie sources/quality without episodes → movie
        if result.source in ('BluRay', 'REMUX', 'WEB-DL') and not result.has_episode_info:
            score_movie += 1.0

        # Multi-part → movie (parts of a movie, not episodes)
        if result.is_multi_part and not result.has_episode_info:
            score_movie += 2.0

        # Very high episode numbers (> 50) → probably anime
        if result.episode and result.episode > 50:
            score_anime += 2.0

        # Season > 1 with normal episode numbers → TV (not usually anime)
        if result.season and result.season > 1 and result.episode and result.episode < 30:
            score_tv += 1.0

        # Make final decision
        max_score = max(score_movie, score_tv, score_anime)

        if max_score == 0:
            result.media_type = MediaType.UNKNOWN
            result.confidence = 0.3
        elif score_anime >= score_tv and score_anime >= score_movie:
            result.media_type = MediaType.ANIME
            result.confidence = min(1.0, score_anime / 5.0)
        elif score_tv >= score_movie:
            result.media_type = MediaType.TV_SHOW
            result.confidence = min(1.0, score_tv / 5.0)
        else:
            result.media_type = MediaType.MOVIE
            result.confidence = min(1.0, score_movie / 5.0)

    def _detect_subtitle_lang(self, filename: str) -> Optional[str]:
        """Detect subtitle language from filename."""
        # Common patterns: movie.en.srt, movie.eng.srt, movie.English.srt
        lang_patterns = {
            r'\.en(?:g(?:lish)?)?\.': 'en',
            r'\.ar(?:abic)?\.': 'ar',
            r'\.fr(?:ench|a)?\.': 'fr',
            r'\.es(?:panish|p)?\.': 'es',
            r'\.de(?:utsch|u)?\.': 'de',
            r'\.it(?:alian|a)?\.': 'it',
            r'\.pt(?:b|r)?\.': 'pt',
            r'\.ja(?:p(?:anese)?)?\.': 'ja',
            r'\.zh|\.chi(?:nese)?\.': 'zh',
            r'\.ko(?:r(?:ean)?)?\.': 'ko',
            r'\.ru(?:s(?:sian)?)?\.': 'ru',
            r'\.hi(?:ndi)?\.': 'hi',
        }
        for pattern, lang in lang_patterns.items():
            if re.search(pattern, filename, re.I):
                return lang
        return None
