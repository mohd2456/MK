"""Unit tests for context-aware suggestion mapping."""

from __future__ import annotations

from mk.wrapper.context import get_suggestions, known_pages
from mk.wrapper.models import PageContext


def test_known_pages_nonempty():
    pages = known_pages()
    assert "/dashboard" in pages
    assert "/storage" in pages


def test_dashboard_suggestions():
    actions = get_suggestions(PageContext(page="/dashboard"))
    ids = {a.id for a in actions}
    assert "dash.status" in ids
    assert all(a.command for a in actions)


def test_nested_route_inherits_parent_prefix():
    # /apps/containers has no dedicated table entry, should inherit /apps.
    actions = get_suggestions(PageContext(page="/apps/containers"))
    ids = {a.id for a in actions}
    assert "apps.containers" in ids


def test_unknown_page_falls_back_to_default():
    actions = get_suggestions(PageContext(page="/totally/unknown"))
    ids = {a.id for a in actions}
    assert "default.status" in ids
    assert "default.help" in ids


def test_selection_adds_inspect_action_first():
    actions = get_suggestions(PageContext(page="/apps", selection="plex"))
    assert actions[0].id == "context.inspect_selection"
    assert "plex" in actions[0].command


def test_suggestions_never_empty():
    assert len(get_suggestions(PageContext(page="/"))) > 0


def test_longest_prefix_wins():
    # /storage should match the storage table, not the default set.
    actions = get_suggestions(PageContext(page="/storage/pools"))
    categories = {a.category for a in actions}
    assert "storage" in categories


def test_sibling_route_does_not_false_match_prefix():
    """Regression: '/media-manager' must NOT inherit '/media' suggestions.

    A raw string-prefix check would wrongly match it; matching must be on
    path segments. Such sibling routes fall back to the generic set.
    """
    actions = get_suggestions(PageContext(page="/media-manager"))
    ids = {a.id for a in actions}
    assert "media.library" not in ids
    assert "default.status" in ids  # generic fallback


def test_sibling_route_networking_not_network():
    actions = get_suggestions(PageContext(page="/networking"))
    ids = {a.id for a in actions}
    assert "net.interfaces" not in ids
    assert "default.status" in ids


def test_nested_route_still_matches_parent():
    # The valid nested case must keep working after the segment-match fix.
    actions = get_suggestions(PageContext(page="/media/library/2024"))
    ids = {a.id for a in actions}
    assert "media.library" in ids
