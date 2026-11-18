"""OpenAI adapter (Chat Completions API over HTTPS, JSON mode)."""
from .base import Provider, SYSTEM_PROMPT, build_user_prompt, http_json, parse_json_object
from ..errors import InvalidProviderResponse


class OpenAIProvider(Provider):
    name = "openai"
    label = "OpenAI"
    URL = "https://api.openai.com/v1/chat/completions"

    def is_configured(self):
        return bool(self.api_key() and self.model)

    def config_hint(self):
        return "Set OPENAI_API_KEY (and optionally OPENAI_MODEL)."

    def analyze(self, description, title=None, service=None, reported_severity=None):
        data = http_json(self, "POST", self.URL,
                         headers={"Authorization": f"Bearer {self.api_key()}", "Content-Type": "application/json"},
                         json_body={"model": self.model,
                                    "response_format": {"type": "json_object"},
                                    "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                                                 {"role": "user", "content": build_user_prompt(
                                                     description, title, service, reported_severity)}]})
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise InvalidProviderResponse("Unexpected response shape from OpenAI.")
        return parse_json_object(text)
