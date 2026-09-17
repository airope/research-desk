"""Explicit provider registry. Models are examples, not an exhaustive allowlist."""

from dataclasses import dataclass, field
from urllib.parse import urlsplit

from django.conf import settings


class ProviderError(ValueError):
    pass


@dataclass(frozen=True)
class Provider:
    label: str
    endpoint: str
    key_env: str
    model: str
    mode: str = "json_schema"


PROVIDERS = {
    "openai": Provider("OpenAI", "https://api.openai.com/v1", "OPENAI_API_KEY", "gpt-4.1"),
    "anthropic": Provider(
        "Anthropic",
        "https://api.anthropic.com/v1",
        "ANTHROPIC_API_KEY",
        "claude-sonnet-4-6",
        "tool",
    ),
    "gemini": Provider(
        "Google Gemini",
        "https://generativelanguage.googleapis.com/v1beta/openai",
        "GEMINI_API_KEY",
        "gemini-3.8-flash",
    ),
    "mistral": Provider(
        "Mistral",
        "https://api.mistral.ai/v1",
        "MISTRAL_API_KEY",
        "mistral-small-latest",
        "json_object",
    ),
    "deepseek": Provider(
        "DeepSeek", "https://api.deepseek.com", "DEEPSEEK_API_KEY", "deepseek-flash", "json_object"
    ),
    "groq": Provider(
        "Groq", "https://api.groq.com/openai/v1", "GROQ_API_KEY", "openai/gpt-oss-120b"
    ),
    "xai": Provider("xAI", "https://api.x.ai/v1", "XAI_API_KEY", "grok-4.6"),
    "openrouter": Provider(
        "OpenRouter", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", "openai/gpt-4.1"
    ),
    "openai_compatible": Provider("OpenAI-compatible API", "", "LLM_API_KEY", "", "json_object"),
}


@dataclass(frozen=True)
class Configuration:
    name: str
    provider: Provider
    model: str
    base_url: str
    key: str = field(repr=False)
    mode: str = "json_schema"
    max_tokens: int = 8192
    timeout: int = 180


def configuration():
    name = settings.LLM_PROVIDER
    provider = PROVIDERS.get(name)
    if provider is None:
        raise ProviderError("Select a supported LLM_PROVIDER in the server configuration.")
    key = settings.LLM_API_KEY or settings.LLM_PROVIDER_KEYS.get(provider.key_env, "")
    base_url = provider.endpoint
    if name == "openai_compatible":
        base_url = settings.LLM_BASE_URL.rstrip("/")
    elif settings.LLM_BASE_URL:
        raise ProviderError("LLM_BASE_URL is reserved for the openai_compatible provider.")
    try:
        parsed = urlsplit(base_url)
        parsed.port  # Validate malformed/non-numeric ports before any network call.
    except ValueError:
        raise ProviderError("Set a valid LLM_BASE_URL.") from None
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if (
        not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or (parsed.scheme != "https" and not (parsed.scheme == "http" and local and settings.DEBUG))
    ):
        raise ProviderError("LLM_BASE_URL must use HTTPS; local HTTP is development-only.")
    model = settings.LLM_MODEL or provider.model
    if not model or len(model) > 200 or any(ord(c) < 32 for c in model):
        raise ProviderError("Set a valid LLM_MODEL identifier.")
    if not key and not (name == "openai_compatible" and local and settings.DEBUG):
        raise ProviderError(f"Set {provider.key_env} or LLM_API_KEY for the selected provider.")
    mode = settings.LLM_OUTPUT_MODE or provider.mode
    if mode not in {"json_schema", "json_object"} and not (name == "anthropic" and mode == "tool"):
        raise ProviderError(
            "LLM_OUTPUT_MODE must be json_schema or json_object (Anthropic uses tool)."
        )
    if name == "anthropic" and mode != "tool":
        raise ProviderError(
            "Anthropic uses its native structured tool response; leave LLM_OUTPUT_MODE empty."
        )
    return Configuration(
        name,
        provider,
        model,
        base_url,
        key,
        mode,
        settings.LLM_MAX_OUTPUT_TOKENS,
        settings.LLM_TIMEOUT_SECONDS,
    )
