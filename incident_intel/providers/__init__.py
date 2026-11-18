"""Provider registry. Add a provider by subclassing Provider and listing it here."""
from ..errors import ProviderNotConfigured, ValidationError
from .anthropic_provider import AnthropicProvider
from .bedrock import BedrockProvider
from .demo import DemoProvider
from .gemini_provider import GeminiProvider
from .openai_provider import OpenAIProvider

PROVIDERS = {cls.name: cls for cls in (DemoProvider, BedrockProvider, OpenAIProvider, GeminiProvider,
                                       AnthropicProvider)}


def get_provider(name, settings):


    """Return a ready provider or raise ValidationError (unknown) / ProviderNotConfigured (missing key or model)."""
    cls = PROVIDERS.get(name)
    if cls is None:
        raise ValidationError(f"Unknown provider '{name}'. Choose one of: {', '.join(PROVIDERS)}.")
    provider = cls(settings)
    if not provider.is_configured():
        raise ProviderNotConfigured(f"{provider.label} is not configured on the server. {provider.config_hint()}")
    return provider


def describe_providers(settings):
    """Public provider list. Contains no secrets - only whether each is configured."""
    out = []
    for cls in PROVIDERS.values():
        p = cls(settings)
        out.append({"id": p.name, "label": p.label, "simulated": p.simulated,
                    "configured": p.is_configured(), "model": p.model or None,
                    "hint": "" if p.is_configured() else p.config_hint()})
    return out
