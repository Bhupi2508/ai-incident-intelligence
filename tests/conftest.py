import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from incident_intel.app import create_app  # noqa: E402
from incident_intel.config import Settings  # noqa: E402

SECRET = "sk-test-SECRET-1234567890abcdef"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Tests must never pick up a developer's real credentials or .env."""
    for k in list(os.environ):
        if k.endswith(("_API_KEY", "_MODEL", "_MODEL_ID")) or k in {"DEFAULT_PROVIDER", "DATABASE_PATH", "HISTORY_ENABLED"}:
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr("incident_intel.app.load_dotenv", lambda *a, **k: None)


def make_settings(**kw):
    base = dict(database_path=":memory:", models=Settings.from_env().models, secrets={}, bedrock_region="")
    base.update(kw)
    return Settings.from_env(**base)


@pytest.fixture
def settings():
    return make_settings()


@pytest.fixture
def live_settings():
    return make_settings(secrets={"openai": SECRET, "gemini": SECRET, "anthropic": SECRET},
                         bedrock_region="us-east-1", models={**Settings.from_env().models, "bedrock": "test-model"})


@pytest.fixture
def client(settings):
    return create_app(settings).test_client()


@pytest.fixture
def live_client(live_settings):
    return create_app(live_settings).test_client()


GOOD = {
    "summary": "Checkout is failing.", "severity": "High", "severity_reasoning": "Many users affected.",
    "impact": {"business": "Lost sales", "operational": "Support load"},
    "possible_root_causes": [{"cause": "Gateway outage", "confidence": "medium", "evidence": "timeouts"}],
    "investigation_steps": ["Check gateway"], "resolution_steps": ["Roll back"],
    "suggested_priority": "P2", "next_actions": ["Page on-call"], "needs_human_escalation": True,
    "confidence": "medium",
}
DESC = "Users report the checkout page is slow and sometimes errors out since this morning."
