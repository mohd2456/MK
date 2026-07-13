"""API Key Manager — Store up to 40 keys, auto-configure providers.

Set keys from Telegram with /setkey and MK figures out the rest:
  - Which provider the key belongs to
  - What models are available
  - Cost per token for each
  - Smart routing: best model for the task, cheapest for simple stuff

MK uses tokens like they're nothing — picks cheap models for simple tasks,
expensive ones only when it actually needs reasoning power.

Key storage: encrypted at rest in /etc/mk/keys.json (chmod 600).
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

KEYS_FILE = "/etc/mk/keys.json"
MAX_KEYS = 40

# Provider detection: match API key patterns to providers
KEY_PATTERNS = {
    "anthropic": re.compile(r"^sk-ant-"),
    "openai": re.compile(r"^sk-(?!ant|or)"),
    "gemini": re.compile(r"^AIza"),
    "groq": re.compile(r"^gsk_"),
    "mistral": re.compile(r"^[a-zA-Z0-9]{32}$"),
    "openrouter": re.compile(r"^sk-or-"),
    "together": re.compile(r"^[a-f0-9]{64}$"),
    "fireworks": re.compile(r"^fw_"),
    "perplexity": re.compile(r"^pplx-"),
    "cohere": re.compile(r"^[a-zA-Z0-9]{40}$"),
    "deepseek": re.compile(r"^sk-[a-f0-9]{48,}"),
    "xai": re.compile(r"^xai-"),
    "nvidia": re.compile(r"^nvapi-"),
    "sambanova": re.compile(r"^[a-f0-9]{8}-[a-f0-9]{4}-"),
    "cerebras": re.compile(r"^csk-"),
    "hyperbolic": re.compile(r"^hyp_"),
    "lepton": re.compile(r"^lpt_"),
    "novita": re.compile(r"^nvt-"),
    "octo": re.compile(r"^octo-"),
    "anyscale": re.compile(r"^esecret_"),
}

# Best models per provider (ranked by capability)
PROVIDER_MODELS: Dict[str, List[Dict[str, Any]]] = {
    # Model pins verified against provider docs as of July 2026. The first
    # entry in each list is the provider's default model (see provider_factory),
    # so a balanced/cost-conscious model is listed first, matching MK's
    # "cheap by default, smart when needed" routing philosophy. Cost figures
    # are approximate ($/1K tokens) and only influence routing preference.
    "anthropic": [
        {
            "model": "claude-sonnet-4-6",
            "input": 0.003,
            "output": 0.015,
            "max_ctx": 200000,
            "tier": "fast",
        },
        {
            "model": "claude-haiku-4-5",
            "input": 0.001,
            "output": 0.005,
            "max_ctx": 200000,
            "tier": "cheap",
        },
        {
            "model": "claude-opus-4-8",
            "input": 0.015,
            "output": 0.075,
            "max_ctx": 200000,
            "tier": "smart",
        },
    ],
    "openai": [
        {
            "model": "gpt-5.4-mini",
            "input": 0.00025,
            "output": 0.002,
            "max_ctx": 400000,
            "tier": "fast",
        },
        {
            "model": "gpt-5.4-nano",
            "input": 0.00005,
            "output": 0.0004,
            "max_ctx": 400000,
            "tier": "cheap",
        },
        {"model": "gpt-5.5", "input": 0.00125, "output": 0.01, "max_ctx": 400000, "tier": "smart"},
    ],
    "gemini": [
        {
            "model": "gemini-3.5-flash",
            "input": 0.00015,
            "output": 0.0006,
            "max_ctx": 1000000,
            "tier": "fast",
        },
        {
            "model": "gemini-2.5-pro",
            "input": 0.00125,
            "output": 0.01,
            "max_ctx": 1000000,
            "tier": "smart",
        },
    ],
    "groq": [
        {
            "model": "openai/gpt-oss-120b",
            "input": 0.00015,
            "output": 0.0006,
            "max_ctx": 128000,
            "tier": "fast",
        },
        {
            "model": "meta-llama/llama-4-scout-17b-16e-instruct",
            "input": 0.00011,
            "output": 0.00034,
            "max_ctx": 1000000,
            "tier": "cheap",
        },
        {
            "model": "openai/gpt-oss-20b",
            "input": 0.00005,
            "output": 0.0002,
            "max_ctx": 128000,
            "tier": "cheap",
        },
    ],
    "mistral": [
        {
            "model": "mistral-large-latest",
            "input": 0.002,
            "output": 0.006,
            "max_ctx": 128000,
            "tier": "smart",
        },
        {
            "model": "mistral-small-latest",
            "input": 0.0002,
            "output": 0.0006,
            "max_ctx": 128000,
            "tier": "cheap",
        },
    ],
    "openrouter": [
        {
            "model": "anthropic/claude-sonnet-4.6",
            "input": 0.003,
            "output": 0.015,
            "max_ctx": 200000,
            "tier": "smart",
        },
        {
            "model": "google/gemini-3.5-flash",
            "input": 0.00015,
            "output": 0.0006,
            "max_ctx": 1000000,
            "tier": "fast",
        },
        {
            "model": "meta-llama/llama-4-maverick",
            "input": 0.0004,
            "output": 0.0004,
            "max_ctx": 1000000,
            "tier": "cheap",
        },
    ],
    "together": [
        {
            "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
            "input": 0.00054,
            "output": 0.00054,
            "max_ctx": 128000,
            "tier": "fast",
        },
        {
            "model": "meta-llama/Llama-3.1-8B-Instruct-Turbo",
            "input": 0.00005,
            "output": 0.00005,
            "max_ctx": 128000,
            "tier": "cheap",
        },
    ],
    "fireworks": [
        {
            "model": "accounts/fireworks/models/llama-v3p3-70b-instruct",
            "input": 0.0009,
            "output": 0.0009,
            "max_ctx": 128000,
            "tier": "fast",
        },
    ],
    "perplexity": [
        {"model": "sonar-pro", "input": 0.003, "output": 0.015, "max_ctx": 200000, "tier": "smart"},
        {"model": "sonar", "input": 0.001, "output": 0.001, "max_ctx": 128000, "tier": "fast"},
    ],
    "deepseek": [
        {
            "model": "deepseek-chat",
            "input": 0.00014,
            "output": 0.00028,
            "max_ctx": 128000,
            "tier": "cheap",
        },
        {
            "model": "deepseek-reasoner",
            "input": 0.00055,
            "output": 0.0022,
            "max_ctx": 128000,
            "tier": "smart",
        },
    ],
    "cohere": [
        {
            "model": "command-r-plus",
            "input": 0.003,
            "output": 0.015,
            "max_ctx": 128000,
            "tier": "smart",
        },
        {
            "model": "command-r",
            "input": 0.0005,
            "output": 0.0015,
            "max_ctx": 128000,
            "tier": "fast",
        },
    ],
    "xai": [
        {
            "model": "grok-4.3",
            "input": 0.00125,
            "output": 0.0025,
            "max_ctx": 1000000,
            "tier": "fast",
        },
        {"model": "grok-4.5", "input": 0.003, "output": 0.015, "max_ctx": 1000000, "tier": "smart"},
        {
            "model": "grok-build",
            "input": 0.001,
            "output": 0.002,
            "max_ctx": 256000,
            "tier": "smart",
        },
    ],
    "nvidia": [
        {
            "model": "nvidia/llama-3.1-nemotron-70b-instruct",
            "input": 0.00035,
            "output": 0.0004,
            "max_ctx": 128000,
            "tier": "fast",
        },
        {
            "model": "nvidia/nemotron-4-340b-instruct",
            "input": 0.0042,
            "output": 0.0042,
            "max_ctx": 4096,
            "tier": "smart",
        },
        {
            "model": "meta/llama-3.3-70b-instruct",
            "input": 0.00035,
            "output": 0.0004,
            "max_ctx": 128000,
            "tier": "fast",
        },
        {
            "model": "meta/llama-3.1-8b-instruct",
            "input": 0.00005,
            "output": 0.00005,
            "max_ctx": 128000,
            "tier": "cheap",
        },
    ],
    "sambanova": [
        {
            "model": "Meta-Llama-3.3-70B-Instruct",
            "input": 0.0006,
            "output": 0.0006,
            "max_ctx": 128000,
            "tier": "fast",
        },
        {
            "model": "Meta-Llama-3.1-8B-Instruct",
            "input": 0.0001,
            "output": 0.0001,
            "max_ctx": 128000,
            "tier": "cheap",
        },
        {
            "model": "DeepSeek-R1",
            "input": 0.002,
            "output": 0.008,
            "max_ctx": 128000,
            "tier": "smart",
        },
    ],
    "cerebras": [
        {
            "model": "llama-3.3-70b",
            "input": 0.00059,
            "output": 0.00079,
            "max_ctx": 128000,
            "tier": "fast",
        },
        {
            "model": "llama-3.1-8b",
            "input": 0.0001,
            "output": 0.0001,
            "max_ctx": 128000,
            "tier": "cheap",
        },
    ],
    "hyperbolic": [
        {
            "model": "meta-llama/Llama-3.3-70B-Instruct",
            "input": 0.0004,
            "output": 0.0004,
            "max_ctx": 128000,
            "tier": "fast",
        },
        {
            "model": "meta-llama/Llama-3.1-8B-Instruct",
            "input": 0.00006,
            "output": 0.00006,
            "max_ctx": 128000,
            "tier": "cheap",
        },
        {
            "model": "deepseek-ai/DeepSeek-R1",
            "input": 0.002,
            "output": 0.002,
            "max_ctx": 128000,
            "tier": "smart",
        },
    ],
    "lepton": [
        {
            "model": "llama-3.3-70b",
            "input": 0.0004,
            "output": 0.0004,
            "max_ctx": 128000,
            "tier": "fast",
        },
        {
            "model": "llama-3.1-8b",
            "input": 0.00006,
            "output": 0.00006,
            "max_ctx": 128000,
            "tier": "cheap",
        },
    ],
    "novita": [
        {
            "model": "meta-llama/llama-3.3-70b-instruct",
            "input": 0.0004,
            "output": 0.0004,
            "max_ctx": 128000,
            "tier": "fast",
        },
        {
            "model": "meta-llama/llama-3.1-8b-instruct",
            "input": 0.00005,
            "output": 0.00005,
            "max_ctx": 128000,
            "tier": "cheap",
        },
    ],
    "octo": [
        {
            "model": "meta-llama-3.1-70b-instruct",
            "input": 0.0009,
            "output": 0.0009,
            "max_ctx": 128000,
            "tier": "fast",
        },
        {
            "model": "meta-llama-3.1-8b-instruct",
            "input": 0.0001,
            "output": 0.0001,
            "max_ctx": 128000,
            "tier": "cheap",
        },
    ],
    "anyscale": [
        {
            "model": "meta-llama/Meta-Llama-3.1-70B-Instruct",
            "input": 0.001,
            "output": 0.001,
            "max_ctx": 128000,
            "tier": "fast",
        },
        {
            "model": "meta-llama/Meta-Llama-3.1-8B-Instruct",
            "input": 0.00015,
            "output": 0.00015,
            "max_ctx": 128000,
            "tier": "cheap",
        },
    ],
    # Local brain — MK's own fine-tuned model, running for free on local
    # hardware. Registered without an API key (see configure_router_from_keys).
    # Cost 0 means the router prefers it first, falling back to cloud on failure.
    "local": [
        {"model": "mk-brain", "input": 0.0, "output": 0.0, "max_ctx": 8192, "tier": "cheap"},
    ],
    "ollama": [
        {"model": "mk-brain", "input": 0.0, "output": 0.0, "max_ctx": 8192, "tier": "cheap"},
        {
            "model": "qwen2.5:3b-instruct",
            "input": 0.0,
            "output": 0.0,
            "max_ctx": 32768,
            "tier": "cheap",
        },
    ],
}

# Provider API endpoints
PROVIDER_ENDPOINTS = {
    "anthropic": "https://api.anthropic.com",
    "openai": "https://api.openai.com/v1",
    "gemini": "https://generativelanguage.googleapis.com",
    "groq": "https://api.groq.com/openai/v1",
    "mistral": "https://api.mistral.ai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "together": "https://api.together.xyz/v1",
    "fireworks": "https://api.fireworks.ai/inference/v1",
    "perplexity": "https://api.perplexity.ai",
    "deepseek": "https://api.deepseek.com/v1",
    "cohere": "https://api.cohere.ai/v1",
    "xai": "https://api.x.ai/v1",
    "nvidia": "https://integrate.api.nvidia.com/v1",
    "sambanova": "https://api.sambanova.ai/v1",
    "cerebras": "https://api.cerebras.ai/v1",
    "hyperbolic": "https://api.hyperbolic.xyz/v1",
    "lepton": "https://llama-3-3-70b.lepton.run/api/v1",
    "novita": "https://api.novita.ai/v3/openai",
    "octo": "https://text.octoai.run/v1",
    "anyscale": "https://api.endpoints.anyscale.com/v1",
    # Local inference servers (no API key). Defaults match the training/deploy
    # setup: llama.cpp OpenAI-compatible server on :8080, Ollama on :11434.
    # Override the local URL with the MK_LOCAL_BRAIN_URL environment variable.
    "local": "http://localhost:8080/v1",
    "ollama": "http://localhost:11434",
}


class KeyManager:
    """Manages API keys for all LLM providers.

    Features:
    - Auto-detects which provider a key belongs to
    - Stores up to 40 keys
    - Persists to disk (encrypted-at-rest via file permissions)
    - Provides smart model selection per task tier
    """

    def __init__(self, keys_file: str = KEYS_FILE) -> None:
        self._keys_file = keys_file
        self._keys: Dict[str, List[str]] = {}  # provider -> [keys]
        self._load()

    def _load(self) -> None:
        """Load keys from disk."""
        path = Path(self._keys_file)
        if path.exists():
            try:
                data = json.loads(path.read_text())
                self._keys = data.get("keys", {})
            except (json.JSONDecodeError, OSError):
                self._keys = {}

    def _save(self) -> None:
        """Save keys to disk with restricted permissions."""
        path = Path(self._keys_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"keys": self._keys}, indent=2))
        os.chmod(self._keys_file, 0o600)

    def total_keys(self) -> int:
        """Count total keys across all providers."""
        return sum(len(keys) for keys in self._keys.values())

    def detect_provider(self, api_key: str) -> Optional[str]:
        """Detect which provider an API key belongs to.

        Args:
            api_key: The API key string.

        Returns:
            Provider name or None if unrecognized.
        """
        for provider, pattern in KEY_PATTERNS.items():
            if pattern.match(api_key):
                return provider
        return None

    def add_key(self, api_key: str, provider_override: Optional[str] = None) -> Tuple[bool, str]:
        """Add an API key.

        Auto-detects the provider, or use provider_override.

        Args:
            api_key: The API key.
            provider_override: Force a specific provider.

        Returns:
            Tuple of (success, message).
        """
        if self.total_keys() >= MAX_KEYS:
            return False, f"Maximum {MAX_KEYS} keys reached. Remove one first."

        provider = provider_override or self.detect_provider(api_key)
        if not provider:
            return (
                False,
                "Cannot detect provider from key format. Use: /setkey provider_name your-key",
            )

        if provider not in PROVIDER_ENDPOINTS:
            return (
                False,
                f"Unknown provider '{provider}'. Supported: {', '.join(PROVIDER_ENDPOINTS.keys())}",
            )

        # Check for duplicate
        existing = self._keys.get(provider, [])
        if api_key in existing:
            return False, f"Key already exists for {provider}."

        # Add
        if provider not in self._keys:
            self._keys[provider] = []
        self._keys[provider].append(api_key)
        self._save()

        models = PROVIDER_MODELS.get(provider, [])
        model_names = [m["model"] for m in models[:3]]

        return True, (
            f"✓ Key added for {provider}\n"
            f"  Models available: {', '.join(model_names)}\n"
            f"  Total keys: {self.total_keys()}/{MAX_KEYS}"
        )

    def remove_key(self, provider: str, index: int = 0) -> Tuple[bool, str]:
        """Remove an API key by provider and index.

        Args:
            provider: Provider name.
            index: Key index (0-based, default removes first).

        Returns:
            Tuple of (success, message).
        """
        keys = self._keys.get(provider, [])
        if not keys:
            return False, f"No keys for {provider}."
        if index >= len(keys):
            return False, f"Key index {index} out of range (have {len(keys)})."

        keys.pop(index)
        if not keys:
            del self._keys[provider]
        self._save()
        return True, f"✓ Key removed from {provider}. Total: {self.total_keys()}/{MAX_KEYS}"

    def list_keys(self) -> Dict[str, Any]:
        """List all configured providers and key counts (not the actual keys).

        Returns:
            Dict with provider info.
        """
        result = {}
        for provider, keys in self._keys.items():
            models = PROVIDER_MODELS.get(provider, [])
            result[provider] = {
                "key_count": len(keys),
                "endpoint": PROVIDER_ENDPOINTS.get(provider, ""),
                "models": [m["model"] for m in models],
                "tiers": list(set(m["tier"] for m in models)),
            }
        return result

    def get_key(self, provider: str) -> Optional[str]:
        """Get an API key for a provider (round-robin if multiple).

        Args:
            provider: Provider name.

        Returns:
            API key string or None.
        """
        keys = self._keys.get(provider, [])
        if not keys:
            return None
        # Simple round-robin: rotate the list
        key = keys[0]
        if len(keys) > 1:
            self._keys[provider] = keys[1:] + [keys[0]]
            self._save()
        return key

    def get_active_providers(self) -> List[str]:
        """Get list of providers that have at least one key."""
        return [p for p, keys in self._keys.items() if keys]

    # --- Smart Model Selection ---

    def pick_model(self, tier: str = "fast") -> Optional[Dict[str, Any]]:
        """Pick the best available model for a given tier.

        Tier strategy:
          "cheap" — Use the cheapest model available (simple queries, confirmations)
          "fast"  — Balance of speed and quality (most tasks)
          "smart" — Best reasoning model available (complex planning, code)

        MK uses "cheap" for most things, "smart" only when it needs to think hard.

        Args:
            tier: "cheap", "fast", or "smart"

        Returns:
            Dict with model, provider, and cost info, or None if no keys.
        """
        active = self.get_active_providers()
        if not active:
            return None

        candidates: List[Dict[str, Any]] = []

        for provider in active:
            models = PROVIDER_MODELS.get(provider, [])
            for model in models:
                if model["tier"] == tier or (tier == "fast" and model["tier"] in ("fast", "cheap")):
                    candidates.append(
                        {
                            "provider": provider,
                            "model": model["model"],
                            "input_cost": model["input"],
                            "output_cost": model["output"],
                            "max_ctx": model["max_ctx"],
                            "tier": model["tier"],
                        }
                    )

        if not candidates:
            # Fallback: any available model
            for provider in active:
                models = PROVIDER_MODELS.get(provider, [])
                if models:
                    m = models[0]
                    candidates.append(
                        {
                            "provider": provider,
                            "model": m["model"],
                            "input_cost": m["input"],
                            "output_cost": m["output"],
                            "max_ctx": m["max_ctx"],
                            "tier": m["tier"],
                        }
                    )

        if not candidates:
            return None

        # Sort by cost (cheapest first for cheap/fast, most capable for smart)
        if tier == "smart":
            # For smart: prefer higher-cost models (they're better)
            candidates.sort(key=lambda c: c["output_cost"], reverse=True)
        else:
            # For cheap/fast: prefer lowest cost
            candidates.sort(key=lambda c: c["input_cost"] + c["output_cost"])

        return candidates[0]

    def pick_cheapest(self) -> Optional[Dict[str, Any]]:
        """Pick the absolute cheapest model available."""
        return self.pick_model("cheap")

    def pick_smartest(self) -> Optional[Dict[str, Any]]:
        """Pick the most capable model available."""
        return self.pick_model("smart")

    def get_token_budget_strategy(self) -> Dict[str, Any]:
        """Get the token usage strategy based on available models.

        MK uses tokens like they're nothing:
        - Simple stuff (confirmations, status): cheap model, <100 tokens
        - Normal tasks (commands, lookups): fast model, <500 tokens
        - Complex reasoning (planning, debugging): smart model, <2000 tokens

        Returns:
            Strategy dict with model picks per tier.
        """
        return {
            "cheap": self.pick_model("cheap"),
            "fast": self.pick_model("fast"),
            "smart": self.pick_model("smart"),
            "total_providers": len(self.get_active_providers()),
            "total_keys": self.total_keys(),
            "strategy": (
                "Simple queries → cheapest model (~$0.0001/query)\n"
                "Normal tasks → fast model (~$0.001/query)\n"
                "Complex reasoning → smart model (~$0.01/query)\n"
                "MK auto-picks based on query complexity."
            ),
        }
