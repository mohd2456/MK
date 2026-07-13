"""Tests for local-brain provider registration (keyless, first-class)."""

from __future__ import annotations

from mk.llm.keys import KeyManager
from mk.llm.providers.ollama_provider import OllamaProvider
from mk.llm.providers.universal_provider import UniversalProvider
from mk.llm.provider_factory import (
    configure_router_from_keys,
    create_local_provider,
)


def test_create_local_provider_openai_kind_defaults():
    p = create_local_provider()
    assert isinstance(p, UniversalProvider)
    assert p.name == "local"
    assert p.config.default_model == "mk-brain"
    assert p.config.cost_per_1k_input == 0.0
    assert p.config.base_url.endswith(":8080/v1")


def test_create_local_provider_ollama_kind():
    p = create_local_provider(kind="ollama")
    assert isinstance(p, OllamaProvider)
    assert p.config.base_url.endswith(":11434")


def test_create_local_provider_custom_url_and_model():
    p = create_local_provider(base_url="http://brain.local:9000/v1", model="mk-brain-v2")
    assert p.config.base_url == "http://brain.local:9000/v1"
    assert p.config.default_model == "mk-brain-v2"


def test_router_registers_local_brain_when_env_set(tmp_path, monkeypatch):
    monkeypatch.setenv("MK_LOCAL_BRAIN_URL", "http://localhost:8080/v1")
    km = KeyManager(keys_file=str(tmp_path / "keys.json"))  # no keys
    router = configure_router_from_keys(km)
    assert "local" in router.providers


def test_router_no_local_brain_when_env_unset(tmp_path, monkeypatch):
    monkeypatch.delenv("MK_LOCAL_BRAIN_URL", raising=False)
    km = KeyManager(keys_file=str(tmp_path / "keys.json"))
    router = configure_router_from_keys(km)
    assert "local" not in router.providers
    assert len(router.providers) == 0


def test_local_brain_coexists_with_cloud_and_is_cheapest_first(tmp_path, monkeypatch):
    """Local brain (cost 0) should sit first in the cost-sorted fallback chain."""
    monkeypatch.setenv("MK_LOCAL_BRAIN_URL", "http://localhost:8080/v1")
    km = KeyManager(keys_file=str(tmp_path / "keys.json"))
    km.add_key("sk-ant-testkey")  # anthropic (non-zero cost)
    router = configure_router_from_keys(km)
    assert "local" in router.providers
    assert "anthropic" in router.providers
    # Fallback chain is cost-sorted ascending; local (0.0) must be first.
    assert router._fallback_chain[0] == "local"
