"""Google Gemini adapter (generateContent REST API, JSON response mode)."""
from urllib.parse import quote

from .base import Provider, SYSTEM_PROMPT, build_user_prompt, http_json, parse_json_object
from ..errors import InvalidProviderResponse


class GeminiProvider(Provider):
    name = "gemini"
    label = "Google Gemini"
    BASE = "https://generativelanguage.googleapis.com/v1beta/models/"

    def is_configured(self):
        return bool(self.api_key() and self.model)

    def config_hint(self):
        return "Set GEMINI_API_KEY (and optionally GEMINI_MODEL)."

    def analyze(self, description, title=None, service=None, reported_severity=None):
        url = f"{self.BASE}{quote(self.model, safe='')}:generateContent"
        data = http_json(self, "POST", url,
                         headers={"x-goog-api-key": self.api_key(), "Content-Type": "application/json"},
                         json_body={"systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                                    "contents": [{"role": "user", "parts": [{"text": build_user_prompt(
                                        description, title, service, reported_severity)}]}],
                                    "generationConfig": {"responseMimeType": "application/json",
                                                         "temperature": 0.2}})
        try:
            text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError, TypeError, AttributeError):
            raise InvalidProviderResponse("Unexpected or blocked response from Gemini.")
        return parse_json_object(text)
