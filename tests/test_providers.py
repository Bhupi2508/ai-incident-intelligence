import json

import pytest
import requests

from incident_intel.errors import (InvalidCredentials, InvalidProviderResponse, ModelUnavailable,
                                   ProviderUnavailable, RateLimited)
from incident_intel.providers import get_provider
from incident_intel.providers.base import parse_json_object
from tests.conftest import DESC, GOOD, SECRET


class FakeResp:
    def __init__(self, status=200, body=None, text=None):
        self.status_code, self.ok = status, status < 400
        self._body, self._text = body, text

    def json(self):
        if self._text is not None:
            raise ValueError("not json")
        return self._body


def patch_http(monkeypatch, resp):
    calls = []
    def fake(method, url, headers=None, json=None, timeout=None):
        calls.append({"url": url, "headers": headers, "json": json})
        if isinstance(resp, Exception):
            raise resp
        return resp
    monkeypatch.setattr(requests, "request", fake)
    return calls


# provider -> (response body wrapping GOOD, header that must carry the key)
SHAPES = {
    "openai": ({"choices": [{"message": {"content": json.dumps(GOOD)}}]}, "Authorization"),
    "anthropic": ({"content": [{"type": "text", "text": json.dumps(GOOD)}]}, "x-api-key"),
    "gemini": ({"candidates": [{"content": {"parts": [{"text": json.dumps(GOOD)}]}}]}, "x-goog-api-key"),
}


@pytest.mark.parametrize("name", SHAPES)
def test_http_provider_success_and_key_only_in_header(name, live_settings, monkeypatch):
    body, header = SHAPES[name]
    calls = patch_http(monkeypatch, FakeResp(200, body))
    out = get_provider(name, live_settings).analyze(DESC, title="T")
    assert out["severity"] == "High"
    call = calls[0]
    assert SECRET in call["headers"][header]
    assert SECRET not in call["url"] and SECRET not in json.dumps(call["json"])
    assert DESC in json.dumps(call["json"])


@pytest.mark.parametrize("name", SHAPES)
@pytest.mark.parametrize("status,exc", [(401, InvalidCredentials), (403, InvalidCredentials), (429, RateLimited),
                                        (404, ModelUnavailable), (400, ModelUnavailable), (503, ProviderUnavailable)])
def test_http_error_mapping(name, status, exc, live_settings, monkeypatch):
    patch_http(monkeypatch, FakeResp(status, {"error": {"message": f"bad key {SECRET}"}}))
    with pytest.raises(exc) as e:
        get_provider(name, live_settings).analyze(DESC)
    assert SECRET not in e.value.message          # provider error text is redacted


@pytest.mark.parametrize("err,exc", [(requests.Timeout(), ProviderUnavailable),
                                     (requests.ConnectionError("x"), ProviderUnavailable)])
def test_network_failures(err, exc, live_settings, monkeypatch):
    patch_http(monkeypatch, err)
    with pytest.raises(exc):
        get_provider("openai", live_settings).analyze(DESC)


def test_unexpected_shapes(live_settings, monkeypatch):
    patch_http(monkeypatch, FakeResp(200, {"weird": 1}))
    with pytest.raises(InvalidProviderResponse):
        get_provider("openai", live_settings).analyze(DESC)
    patch_http(monkeypatch, FakeResp(200, text="<html>"))
    with pytest.raises(InvalidProviderResponse):
        get_provider("anthropic", live_settings).analyze(DESC)


def test_parse_json_object_variants():
    assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_object('Here you go: {"a": 1} hope it helps') == {"a": 1}
    for bad in ("", "no json", "[1,2]", "{broken"):
        with pytest.raises(InvalidProviderResponse):
            parse_json_object(bad)


def test_model_is_configurable(live_settings):
    from incident_intel.config import Settings
    s = Settings.from_env(models={**live_settings.models, "openai": "my-model"}, secrets=live_settings.secrets)
    assert get_provider("openai", s).model == "my-model"


# ---- end-to-end through the API with a mocked provider reply ----
def test_live_provider_result_is_validated_and_rules_raise_severity(live_client, monkeypatch):
    low_ball = {**GOOD, "severity": "Low", "suggested_priority": "P4", "needs_human_escalation": False}
    patch_http(monkeypatch, FakeResp(200, {"choices": [{"message": {"content": json.dumps(low_ball)}}]}))
    r = live_client.post("/api/analyze", json={"description": "Payment failure: customers cannot pay.", "provider": "openai"})
    d = r.get_json()["data"]
    assert r.status_code == 201 and d["simulated"] is False and "notice" not in d
    assert d["result"]["severity"] == "Critical" and d["result"]["suggested_priority"] == "P1"
    assert d["severity_signals"]["model"] == "Low" and d["severity_signals"]["final"] == "Critical"
    assert "raised from Low to Critical" in d["result"]["severity_reasoning"]
    assert d["escalation"]["should_escalate"] is True


def test_rules_never_lower_a_models_severity(live_client, monkeypatch):
    crit = {**GOOD, "severity": "Critical"}
    patch_http(monkeypatch, FakeResp(200, {"choices": [{"message": {"content": json.dumps(crit)}}]}))
    r = live_client.post("/api/analyze", json={"description": "Minor typo reported, but impact unknown.", "provider": "openai"})
    assert r.get_json()["data"]["result"]["severity"] == "Critical"


def test_invalid_model_output_is_a_clear_error_not_demo(live_client, monkeypatch):
    bad = {**GOOD, "severity": "Apocalyptic"}
    patch_http(monkeypatch, FakeResp(200, {"choices": [{"message": {"content": json.dumps(bad)}}]}))
    r = live_client.post("/api/analyze", json={"description": DESC, "provider": "openai"})
    assert r.status_code == 502 and r.get_json()["error"]["code"] == "invalid_provider_response"
    assert live_client.get("/api/incidents").get_json()["data"] == []


@pytest.mark.parametrize("status,code,http", [(401, "invalid_credentials", 502), (429, "rate_limited", 429),
                                               (404, "model_unavailable", 502), (500, "provider_unavailable", 503)])
def test_provider_failures_surface_through_api(live_client, monkeypatch, status, code, http):
    patch_http(monkeypatch, FakeResp(status, {"error": {"message": "nope"}}))
    r = live_client.post("/api/analyze", json={"description": DESC, "provider": "anthropic"})
    assert r.status_code == http and r.get_json()["error"]["code"] == code


# ---- Bedrock (boto3 client mocked) ----
class FakeClientError(Exception):
    def __init__(self, code):
        self.response = {"Error": {"Code": code}}


def fake_boto(monkeypatch, *, result=None, error=None):
    import sys, types
    class Client:
        def converse(self, **kw):
            Client.kwargs = kw
            if error:
                raise error
            return {"output": {"message": {"content": [{"text": json.dumps(result)}]}}}
    boto3 = types.ModuleType("boto3")
    boto3.client = lambda *a, **k: Client()
    botocore = types.ModuleType("botocore"); cfg = types.ModuleType("botocore.config")
    cfg.Config = lambda **k: None
    monkeypatch.setitem(sys.modules, "boto3", boto3)
    monkeypatch.setitem(sys.modules, "botocore", botocore)
    monkeypatch.setitem(sys.modules, "botocore.config", cfg)
    return Client


def test_bedrock_success(live_settings, monkeypatch):
    Client = fake_boto(monkeypatch, result=GOOD)
    assert get_provider("bedrock", live_settings).analyze(DESC)["severity"] == "High"
    assert Client.kwargs["modelId"] == "test-model"


@pytest.mark.parametrize("code,exc", [("AccessDeniedException", InvalidCredentials), ("ThrottlingException", RateLimited),
                                      ("ValidationException", ModelUnavailable), ("ServiceUnavailableException", ProviderUnavailable)])
def test_bedrock_error_mapping(code, exc, live_settings, monkeypatch):
    fake_boto(monkeypatch, error=FakeClientError(code))
    with pytest.raises(exc):
        get_provider("bedrock", live_settings).analyze(DESC)


def test_bedrock_needs_model_and_region(settings):
    from incident_intel.errors import ProviderNotConfigured
    with pytest.raises(ProviderNotConfigured):
        get_provider("bedrock", settings)
