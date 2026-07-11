"""Context-awareness: map the current page/screen to relevant actions.

The mapping is data-driven and matched by longest route prefix, so
``/apps/containers`` inherits ``/apps`` suggestions unless it defines its own,
and unknown pages fall back to a sensible generic set. This keeps the
"what can I do here?" logic in one declarative place, shared by the web UI
and any future OS/terminal surface.
"""

from __future__ import annotations

from typing import Dict, List

from mk.wrapper.models import PageContext, SuggestedAction

# Ordered mapping of route prefix -> suggestions. Longest matching prefix wins.
# Each command is phrased as something the assistant can actually act on.
_PAGE_ACTIONS: Dict[str, List[SuggestedAction]] = {
    "/dashboard": [
        SuggestedAction(
            id="dash.status",
            label="System status",
            description="Show a quick health overview",
            command="status",
            category="system",
            icon="activity",
        ),
        SuggestedAction(
            id="dash.alerts",
            label="Active alerts",
            description="List any current alerts",
            command="show active alerts",
            category="system",
            icon="bell",
        ),
        SuggestedAction(
            id="dash.health",
            label="Run health checks",
            description="Run all health checks now",
            command="health",
            category="system",
            icon="heart-pulse",
        ),
    ],
    "/storage": [
        SuggestedAction(
            id="storage.pools",
            label="List pools",
            description="Show ZFS storage pools",
            command="storage",
            category="storage",
            icon="database",
        ),
        SuggestedAction(
            id="storage.disks",
            label="List disks",
            description="Show physical disks and health",
            command="disks",
            category="storage",
            icon="hard-drive",
        ),
        SuggestedAction(
            id="storage.scrub",
            label="Check scrubs",
            description="Review scrub schedules and status",
            command="show scrub status",
            category="storage",
            icon="shield-check",
        ),
    ],
    "/apps": [
        SuggestedAction(
            id="apps.containers",
            label="List containers",
            description="Show Docker containers",
            command="containers",
            category="apps",
            icon="box",
        ),
        SuggestedAction(
            id="apps.restart",
            label="Restart a container",
            description="Restart a container by name",
            command="restart container ",
            category="apps",
            icon="rotate-cw",
        ),
    ],
    "/network": [
        SuggestedAction(
            id="net.interfaces",
            label="List interfaces",
            description="Show network interfaces",
            command="network",
            category="network",
            icon="network",
        ),
        SuggestedAction(
            id="net.tailscale",
            label="Tailscale status",
            description="Show Tailscale connection",
            command="/tailscale status",
            category="network",
            icon="globe",
        ),
    ],
    "/media": [
        SuggestedAction(
            id="media.library",
            label="Library stats",
            description="Show media library statistics",
            command="show media library stats",
            category="media",
            icon="film",
        ),
        SuggestedAction(
            id="media.rip",
            label="Disc status",
            description="Check the disc ripper",
            command="rip",
            category="media",
            icon="disc",
        ),
    ],
    "/protection": [
        SuggestedAction(
            id="protection.backups",
            label="Backup health",
            description="Review backup jobs and status",
            command="backup",
            category="protection",
            icon="save",
        ),
        SuggestedAction(
            id="protection.replication",
            label="Replication",
            description="Show replication tasks",
            command="show replication tasks",
            category="protection",
            icon="copy",
        ),
    ],
    "/system": [
        SuggestedAction(
            id="system.info",
            label="System info",
            description="Show hardware and OS details",
            command="hardware",
            category="system",
            icon="cpu",
        ),
        SuggestedAction(
            id="system.updates",
            label="Check updates",
            description="Check for available updates",
            command="updates",
            category="system",
            icon="download",
        ),
        SuggestedAction(
            id="system.services",
            label="Services",
            description="Show failed services",
            command="services",
            category="system",
            icon="server",
        ),
    ],
    "/keys": [
        SuggestedAction(
            id="keys.list",
            label="Configured keys",
            description="Show which API keys are configured",
            command="keys",
            category="settings",
            icon="key",
        ),
        SuggestedAction(
            id="keys.models",
            label="Model strategy",
            description="Show the active LLM routing strategy",
            command="models",
            category="settings",
            icon="sparkles",
        ),
    ],
}

# Generic fallback for unknown or root pages.
_DEFAULT_ACTIONS: List[SuggestedAction] = [
    SuggestedAction(
        id="default.status",
        label="System status",
        description="Show a quick health overview",
        command="status",
        category="system",
        icon="activity",
    ),
    SuggestedAction(
        id="default.help",
        label="What can you do?",
        description="List available commands and capabilities",
        command="help",
        category="general",
        icon="help-circle",
    ),
]


def get_suggestions(context: PageContext) -> List[SuggestedAction]:
    """Return context-relevant suggestions for the given page.

    Uses longest-prefix matching against the known route table so nested
    routes inherit their parent's suggestions. Unknown pages get a generic
    fallback set so the UI is never empty.
    """
    page = context.page or "/"

    best_prefix = ""
    for prefix in _PAGE_ACTIONS:
        if (page == prefix or page.startswith(prefix + "/") or page.startswith(prefix)) and len(
            prefix
        ) > len(best_prefix):
            best_prefix = prefix

    if best_prefix:
        actions = list(_PAGE_ACTIONS[best_prefix])
    else:
        actions = list(_DEFAULT_ACTIONS)

    # If a specific entity is selected, offer a tailored inspect action first.
    if context.selection:
        actions.insert(
            0,
            SuggestedAction(
                id="context.inspect_selection",
                label=f"Inspect {context.selection}",
                description=f"Show details for {context.selection}",
                command=f"show details for {context.selection}",
                category="context",
                icon="search",
            ),
        )

    return actions


def known_pages() -> List[str]:
    """Return the list of route prefixes with tailored suggestions."""
    return sorted(_PAGE_ACTIONS.keys())
