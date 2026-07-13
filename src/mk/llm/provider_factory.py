"""Provider factory - creates LLM provider instances from stored API keys.

When keys are stored via /setkey, this factory creates the right provider
instance for each active provider. The engine calls this on startup to
auto-configure the LLMRouter with all available providers.

Provider mapping:
- anthropic -> AnthropicProvider (custom Anthropic Messages API)
- openai -> OpenAIProvider (native OpenAI)
- gemini -> GeminiProvider (custom Google generateContent API)
- groq, mistral, together, fireworks, perplexity, deepseek, openrouter, cohere
    -> UniversalProvider (OpenAI-compatible /v1/chat/completions)
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from mk.llm.router import LLMRouter

from mk.llm.base import LLMProvider
from mk.llm.keys import PROVIDER_ENDPOINTS, PROVIDER_MODELS, KeyManager
from mk.llm.models import ProviderConfig
from mk.llm.providers.anthropic_provider import AnthropicProvider
from mk.llm.providers.gemini_provider import GeminiProvider
from mk.llm.providers.ollama_provider import OllamaProvider
from mk.llm.providers.openai_provider import OpenAIProvider
from mk.llm.providers.universal_provider import UniversalProvider

logger = logging.getLogger(__name__)

# Environment variables that enable/point at the local brain.
LOCAL_BRAIN_URL_ENV = "MK_LOCAL_BRAIN_URL"
LOCAL_BRAIN_KIND_ENV = "MK_LOCAL_BRAIN_KIND"  # "openai" (llama.cpp) or "ollama"
LOCAL_BRAIN_MODEL_ENV = "MK_LOCAL_BRAIN_MODEL"

# Providers that have custom (non-OpenAI-compatible) implementations
CUSTOM_PROVIDERS = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
    "ollama": OllamaProvider,
}

# All other known providers use the OpenAI-compatible UniversalProvider
UNIVERSAL_PROVIDERS = {
    "groq",
    "mistral",
    "together",
    "fireworks",
    "perplexity",
    "deepseek",
    "openrouter",
    "cohere",
    "xai",
    "nvidia",
    "sambanova",
    "cerebras",
    "hyperbolic",
    "lepton",
    "novita",
    "octo",
    "anyscale",
    # llama.cpp OpenAI-compatible local server (MK's fine-tuned brain).
    "local",
}


def _build_config(provider_name: str, api_key: str) -> ProviderConfig:
    """Build a ProviderConfig from provider name and API key.

    Uses PROVIDER_ENDPOINTS and PROVIDER_MODELS from keys.py for
    base URLs, model lists, and cost information.

    Args:
        provider_name: The provider identifier (e.g. "groq", "openai").
        api_key: The API key for authentication.

    Returns:
        A fully populated ProviderConfig.
    """
    base_url = PROVIDER_ENDPOINTS.get(provider_name, "")
    models_data = PROVIDER_MODELS.get(provider_name, [])

    model_ids = [m["model"] for m in models_data]
    default_model = model_ids[0] if model_ids else ""

    # Use the first model's cost as the default for the config
    cost_input = models_data[0]["input"] if models_data else 0.0
    cost_output = models_data[0]["output"] if models_data else 0.0

    return ProviderConfig(
        name=provider_name,
        api_key=api_key,
        base_url=base_url,
        models=model_ids,
        default_model=default_model,
        cost_per_1k_input=cost_input,
        cost_per_1k_output=cost_output,
        timeout_seconds=60.0,
        max_retries=3,
    )


def create_provider(provider_name: str, api_key: str) -> LLMProvider:
    """Create a single provider instance.

    Args:
        provider_name: The provider identifier.
        api_key: The API key.

    Returns:
        An LLMProvider instance (correct subclass for the provider).
    """
    config = _build_config(provider_name, api_key)

    if provider_name in CUSTOM_PROVIDERS:
        cls = CUSTOM_PROVIDERS[provider_name]
        return cls(config)

    # All others use the universal OpenAI-compatible provider
    return UniversalProvider(config)


def create_local_provider(
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    kind: str = "openai",
    name: str = "local",
) -> LLMProvider:
    """Create a keyless provider for MK's local brain.

    The local brain is MK's own fine-tuned model served on local hardware —
    a first-class provider that needs no API key and costs nothing to run.

    Args:
        base_url: Local server URL. Falls back to ``MK_LOCAL_BRAIN_URL`` and
            then the default for the transport kind.
        model: Model name to request (default ``mk-brain`` or ``MK_LOCAL_BRAIN_MODEL``).
        kind: ``"openai"`` for a llama.cpp OpenAI-compatible server (default)
            or ``"ollama"`` for an Ollama server.
        name: Provider name to register under.

    Returns:
        A ready ``LLMProvider`` (UniversalProvider for openai kind, OllamaProvider
        for ollama kind).
    """
    kind = (kind or "openai").lower()
    default_url = "http://localhost:11434" if kind == "ollama" else "http://localhost:8080/v1"
    url = base_url or os.environ.get(LOCAL_BRAIN_URL_ENV) or default_url
    model_name = model or os.environ.get(LOCAL_BRAIN_MODEL_ENV) or "mk-brain"

    config = ProviderConfig(
        name=name,
        api_key="",  # local inference needs no key
        base_url=url,
        models=[model_name],
        default_model=model_name,
        cost_per_1k_input=0.0,
        cost_per_1k_output=0.0,
        timeout_seconds=120.0,  # local CPU inference can be slow
        max_retries=2,
    )

    if kind == "ollama":
        return OllamaProvider(config)
    return UniversalProvider(config)


def _maybe_register_local_brain(router: "LLMRouter") -> bool:
    """Register the local brain provider if configured via environment.

    The local brain is enabled by setting ``MK_LOCAL_BRAIN_URL``. Because its
    cost is zero, the router prefers it first and falls back to cloud providers
    only when it is unavailable.

    Returns:
        True if a local provider was registered.
    """
    url = os.environ.get(LOCAL_BRAIN_URL_ENV)
    if not url:
        return False
    kind = os.environ.get(LOCAL_BRAIN_KIND_ENV, "openai")
    try:
        router.register_provider(create_local_provider(base_url=url, kind=kind))
        logger.info("Registered local brain provider at %s (%s)", url, kind)
        return True
    except Exception as exc:  # noqa: BLE001 - never block startup on local brain
        logger.warning("Failed to register local brain: %s", exc)
        return False


def create_providers_from_keys(key_manager: KeyManager) -> List[LLMProvider]:
    """Create provider instances for all active keys in the KeyManager.

    Iterates over all providers that have at least one key stored,
    creates the appropriate provider instance, and returns the list.

    Args:
        key_manager: The KeyManager instance with stored keys.

    Returns:
        List of LLMProvider instances ready to register with LLMRouter.
    """
    providers: List[LLMProvider] = []

    for provider_name in key_manager.get_active_providers():
        api_key = key_manager.get_key(provider_name)
        if not api_key:
            continue

        try:
            provider = create_provider(provider_name, api_key)
            providers.append(provider)
            logger.info(f"Created provider: {provider_name} ({provider.__class__.__name__})")
        except Exception as e:
            logger.warning(f"Failed to create provider {provider_name}: {e}")
            continue

    return providers


def configure_router_from_keys(key_manager: KeyManager) -> "LLMRouter":
    """Create and configure an LLMRouter with all available providers.

    Convenience function that creates providers from keys and registers
    them all with a new LLMRouter instance.

    Args:
        key_manager: The KeyManager instance with stored keys.

    Returns:
        A configured LLMRouter with all available providers registered.
    """
    from mk.llm.router import LLMRouter

    router = LLMRouter()
    providers = create_providers_from_keys(key_manager)

    for provider in providers:
        router.register_provider(provider)

    # Register MK's local brain (keyless) if configured. It sits alongside any
    # cloud providers and, being free, is preferred first with cloud fallback.
    local_registered = _maybe_register_local_brain(router)

    total = len(providers) + (1 if local_registered else 0)
    if total:
        logger.info(f"Router configured with {total} providers")
    else:
        logger.info("No API keys found - router has no providers")

    return router
