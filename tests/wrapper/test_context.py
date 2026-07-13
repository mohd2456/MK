"""Tests for context-aware suggestion mapping."""

from __future__ import annotations

from mk.wrapper.context import label_for, suggestions_for
from mk.wrapper.models import PageContext


class TestSuggestionsFor:
    def test_dashboard_suggestions(self):
        actions = suggestions_for(PageContext(path="/"))
        assert actions
        assert all(a.prompt for a in actions)

    def test_storage_suggestions_differ_from_dashboard(self):
        dash = [a.prompt for a in suggestions_for(PageContext(path="/"))]
        storage = [a.prompt for a in suggestions_for(PageContext(path="/storage"))]
        assert dash != storage

    def test_nested_path_matches_prefix(self):
        actions = suggestions_for(PageContext(path="/storage/pools/tank"))
        labels = [a.label for a in actions]
        assert "Disk temperatures" in labels

    def test_media_manager_not_shadowed_by_media(self):
        # Longest-prefix wins: /media-manager must not fall back to /media.
        actions = suggestions_for(PageContext(path="/media-manager"))
        prompts = [a.prompt for a in actions]
        assert any("drop queue" in p.lower() for p in prompts)

    def test_unknown_path_falls_back_to_dashboard(self):
        actions = suggestions_for(PageContext(path="/totally-unknown"))
        assert actions == suggestions_for(PageContext(path="/"))

    def test_limit_is_respected(self):
        actions = suggestions_for(PageContext(path="/"), limit=2)
        assert len(actions) == 2

    def test_zero_limit_returns_empty(self):
        assert suggestions_for(PageContext(path="/"), limit=0) == []


class TestLabelFor:
    def test_explicit_label_wins(self):
        assert label_for(PageContext(path="/storage", label="Custom")) == "Custom"

    def test_derived_label(self):
        assert label_for(PageContext(path="/network")) == "Network"

    def test_root_label(self):
        assert label_for(PageContext(path="/")) == "Dashboard"
