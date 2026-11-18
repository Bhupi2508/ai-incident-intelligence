"""Anthropic Claude adapter (Messages API over HTTPS)."""
from .base import Provider, SYSTEM_PROMPT, build_user_prompt, http_json, parse_json_object
from ..errors import InvalidProviderResponse


class AnthropicProvider(Provider):
    name = "anthropic"
    label = "Anthropic Claude"
    URL = "https://api.anthropic.com/v1/messages"

    def is_configured(self):
        return bool(self.api_key() and self.model)

    def config_hint(self):
        return "Set ANTHROPIC_API_KEY (and optionally ANTHROPIC_MODEL)."

    def analyze(self, description, title=None, service=None, reported_severity=None):
        data = http_json(self, "POST", self.URL,
                         headers={"x-api-key": self.api_key(), "anthropic-version": "2023-06-01",
                                  "content-type": "application/json"},
                         json_body={"model": self.model, "max_tokens": 2000, "temperature": 0.2,
                                    "system": SYSTEM_PROMPT,
                                    "messages": [{"role": "user", "content": build_user_prompt(
                                        description, title, service, reported_severity)}]})
        try:
            text = "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")
        except (KeyError, TypeError, AttributeError):
            raise InvalidProviderResponse("Unexpected response shape from Anthropic.")
        return parse_json_object(text)
