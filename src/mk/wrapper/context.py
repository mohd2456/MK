"""Context-awareness: map the current page/screen to suggested actions.

This is the backend authority for what the assistant should proactively
offer on each screen. The web UI's ``ContextSuggestions`` component can fetch
these from ``/api/v1/chat/suggestions`` so that suggestions stay in sync with
the assistant's actual capabilities instead of being hard-coded in two places.

The mapping is intentionally simple and data-driven: a route prefix maps to a
human label and an ordered list of suggestions. Longest-prefix wins so that
e.g. ``/media-manager`` is not shadowed by ``/media``.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from mk.wrapper.models import ActionKind, PageContext, SuggestedAction

# Ordered mapping of route prefix -> (label, [(id, label, prompt), ...]).
# Kept in sync with webui/src/components/chat/ContextSuggestions.tsx.
_PAGE_SUGGESTIONS: Dict[str, Tuple[str, List[Tuple[str, str, str]]]] = {
    "/": (
        "Dashboard",
        [
            ("pool-health", "Pool health", "Show me pool health"),
            ("start-backup", "Start a backup", "Start a backup now"),
            ("alerts", "Any alerts?", "Any alerts I should know about?"),
            ("system-status", "System status", "How's my system doing?"),
        ],
    ),
    "/storage": (
        "Storage",
        [
            ("disk-temps", "Disk temperatures", "Show disk temperatures"),
            ("snapshot", "Snapshot tank", "Create a snapshot of tank"),
            ("disks-attention", "Disks needing attention", "Which disks need attention?"),
            ("space-left", "Free space", "How much space is left?"),
        ],
    ),
    "/apps": (
        "Apps",
        [
            ("ram-hogs", "Top RAM users", "Which containers are using the most RAM?"),
            ("restart-plex", "Restart Plex", "Restart the plex container"),
            ("stopped", "Stopped containers", "Show me stopped containers"),
            ("deploy", "Deploy a stack", "Deploy a new stack"),
        ],
    ),
    "/network": (
        "Network",
        [
            ("wg-peers", "WireGuard peers", "Show active WireGuard peers"),
            ("fw-blocks", "Firewall blocks", "Any firewall blocks today?"),
            ("proxy-status", "Reverse proxy", "Check reverse proxy status"),
            ("external-ip", "External IP", "What's my external IP?"),
        ],
    ),
    "/protection": (
        "Protection",
        [
            ("last-backup", "Last backup", "When was the last backup?"),
            ("scrub", "Run a scrub", "Run a scrub on tank"),
            ("repl-lag", "Replication lag", "Show replication lag"),
            ("failed-jobs", "Failed jobs", "Any failed backup jobs?"),
        ],
    ),
    "/media": (
        "Media",
        [
            ("drive-contents", "What's in the drive?", "What's in the drive?"),
            ("recent-rips", "Recent rips", "Show recent rips"),
            ("library-size", "Library size", "How big is my library?"),
            ("start-rip", "Start ripping", "Start ripping the disc"),
        ],
    ),
    "/media-manager": (
        "Media Manager",
        [
            ("drop-queue", "Drop queue", "What's in the drop queue?"),
            ("process-drops", "Process drops", "Process all pending drops now"),
            ("failed-items", "Failed items", "Show failed items"),
            ("jellyfin-scan", "Jellyfin scan", "Trigger Jellyfin library scan"),
        ],
    ),
    "/system": (
        "System",
        [
            ("services", "Running services", "What services are running?"),
            ("updates", "Available updates", "Any updates available?"),
            ("uptime", "System uptime", "Show system uptime"),
            ("ups", "UPS status", "Check UPS status"),
        ],
    ),
}

_DEFAULT_KEY = "/"


def _match_prefix(path: str) -> str:
    """Return the best-matching route key for a path (longest prefix wins)."""
    if path == "/":
        return "/"
    best = _DEFAULT_KEY
    best_len = 0
    for key in _PAGE_SUGGESTIONS:
        if key == "/":
            continue
        if (path == key or path.startswith(key + "/") or path.startswith(key)) and len(
            key
        ) > best_len:
            best = key
            best_len = len(key)
    return best


def label_for(context: PageContext) -> str:
    """Return a human-readable label for the given context.

    An explicit ``context.label`` always wins; otherwise the label is derived
    from the matched route.
    """
    if context.label:
        return context.label
    key = _match_prefix(context.path)
    return _PAGE_SUGGESTIONS[key][0]


def suggestions_for(context: PageContext, limit: int = 4) -> List[SuggestedAction]:
    """Return context-aware suggested actions for the given page context.

    Args:
        context: The current UI context.
        limit: Maximum number of suggestions to return.

    Returns:
        A list of :class:`SuggestedAction`, possibly empty but never None.
    """
    key = _match_prefix(context.path)
    _, entries = _PAGE_SUGGESTIONS[key]
    actions = [
        SuggestedAction(id=aid, label=alabel, prompt=aprompt, kind=ActionKind.SUGGESTION)
        for (aid, alabel, aprompt) in entries
    ]
    if limit >= 0:
        actions = actions[:limit]
    return actions
