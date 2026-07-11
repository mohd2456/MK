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
