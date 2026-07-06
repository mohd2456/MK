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
from typing import Dict, List

from mk.llm.base import LLMProvider
from mk.llm.keys import PROVIDER_ENDPOINTS, PROVIDER_MODELS, KeyManager
from mk.llm.models import ProviderConfig
from mk.llm.providers.anthropic_provider import AnthropicProvider
from mk.llm.providers.gemini_provider import GeminiProvider
from mk.llm.providers.openai_provider import OpenAIProvider
from mk.llm.providers.universal_provider import UniversalProvider

logger = logging.getLogger(__name__)

# Providers that have custom (non-OpenAI-compatible) implementations
CUSTOM_PROVIDERS = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
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

    if providers:
        logger.info(f"Router configured with {len(providers)} providers")
    else:
        logger.info("No API keys found - router has no providers")

    return router
