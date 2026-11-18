"""Configuration, read from environment variables (optionally a local .env file).

API keys live only here, server-side. They are never returned by the API or logged.
"""
import os
from dataclasses import dataclass, field

# Default model per provider. Override with the *_MODEL variables - model names change often,
# so verify availability in your own account.
DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "gemini": "gemini-2.0-flash",
    "anthropic": "claude-sonnet-5-5",
    "bedrock": "",  # no sensible global default: model/inference-profile IDs are account/region specific
}


def _bool(name, default):
    raw = os.getenv(name)
    return default if raw is None else raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Immutable runtime configuration. Secrets are held here only and excluded from repr()."""
    default_provider: str = "demo"
    database_path: str = "data/incidents.db"
    history_enabled: bool = True
    request_timeout: float = 45.0
    max_description_chars: int = 5000
    min_description_chars: int = 15
    models: dict = field(default_factory=dict)
    secrets: dict = field(default_factory=dict)  # provider -> api key (never exposed)
    bedrock_region: str = ""

    @classmethod
    def from_env(cls, **overrides):
        """Build Settings from environment variables; keyword overrides win (used by tests)."""
        models = {p: os.getenv(f"{p.upper()}_MODEL", d).strip() for p, d in DEFAULT_MODELS.items()}
        secrets = {
            "openai": os.getenv("OPENAI_API_KEY", "").strip(),
            "gemini": os.getenv("GEMINI_API_KEY", "").strip(),
            "anthropic": os.getenv("ANTHROPIC_API_KEY", "").strip(),
        }
        values = dict(
            default_provider=os.getenv("DEFAULT_PROVIDER", "demo").strip().lower() or "demo",
            database_path=os.getenv("DATABASE_PATH", "data/incidents.db"),
            history_enabled=_bool("HISTORY_ENABLED", True),
            request_timeout=float(os.getenv("PROVIDER_TIMEOUT_SECONDS", "45")),
            models=models,
            secrets=secrets,
            bedrock_region=(os.getenv("BEDROCK_REGION") or os.getenv("AWS_DEFAULT_REGION") or "").strip(),
        )
        values.update(overrides)
        return cls(**values)

    def __repr__(self):  # keep secrets out of any accidental log/print
        return f"Settings(default_provider={self.default_provider!r}, database_path={self.database_path!r})"
