import logging

from tests.conftest import DESC, SECRET


def analyze(client, **kw):
    return client.post("/api/analyze", json={"description": DESC, **kw})


def test_health_and_frontend(client):
    assert client.get("/api/health").get_json()["data"]["status"] == "ok"
    page = client.get("/")
    assert page.status_code == 200 and b"AI Incident Intelligence" in page.data
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/../README.md").status_code == 404


def test_demo_is_default_and_needs_no_credentials(client):
    r = analyze(client)
    body = r.get_json()
    assert r.status_code == 201 and body["ok"] is True
    d = body["data"]
    assert d["provider"] == "demo" and d["simulated"] is True and "SIMULATED" in d["notice"]
    assert d["result"]["severity"] in {"Critical", "High", "Medium", "Low"}
    assert d["escalation"]["route_to"]


def test_example_incident_from_readme(client):
    d = analyze(client, description=(
        "Payment processing is failing for multiple customers. Transactions are timing out, and several "
        "customers have reported duplicate payment attempts. The issue started approximately 15 minutes ago.")
    ).get_json()["data"]
    assert d["result"]["severity"] == "Critical" and d["result"]["suggested_priority"] == "P1"
    assert d["escalation"]["should_escalate"] is True


def test_providers_list_reports_state_without_secrets(live_client, client):
    demo_only = {p["id"]: p for p in client.get("/api/providers").get_json()["data"]["providers"]}
    assert demo_only["demo"]["configured"] and not demo_only["openai"]["configured"]
    raw = live_client.get("/api/providers").data
    assert SECRET.encode() not in raw
    live = {p["id"]: p for p in live_client.get("/api/providers").get_json()["data"]["providers"]}
    assert all(live[x]["configured"] for x in ("openai", "gemini", "anthropic", "bedrock"))


def test_unconfigured_provider_is_an_error_not_a_demo_fallback(client):
    r = analyze(client, provider="openai")
    assert r.status_code == 400
    err = r.get_json()["error"]
    assert err["code"] == "provider_not_configured" and "OPENAI_API_KEY" in err["message"]
    assert client.get("/api/incidents").get_json()["data"] == []     # nothing saved


def test_unknown_provider(client):
    r = analyze(client, provider="skynet")
    assert r.status_code == 400 and r.get_json()["error"]["code"] == "validation_error"


def test_input_validation(client):
    assert client.post("/api/analyze", data="nope", content_type="text/plain").status_code == 400
    assert client.post("/api/analyze", json=[1]).status_code == 400
    assert client.post("/api/analyze", json={}).status_code == 400
    assert client.post("/api/analyze", json={"description": "too short"}).status_code == 400
    assert analyze(client, description="x" * 5001).status_code == 400
    assert analyze(client, reported_severity="Catastrophic").status_code == 400
    assert analyze(client, title="t" * 121).status_code == 400
    assert analyze(client, description=123).status_code == 400
    big = client.post("/api/analyze", json={"description": "x" * 70000})
    assert big.status_code == 413 and big.get_json()["ok"] is False


def test_consistent_error_envelope_and_no_stack_traces(client):
    r = client.get("/api/nope")
    assert r.status_code == 404 and set(r.get_json()) == {"ok", "error"}
    r = client.get("/api/incidents/doesnotexist")
    assert r.status_code == 404 and r.get_json()["error"]["code"] == "not_found"


def test_history_lifecycle(client):
    a = analyze(client, title="Checkout slow", reported_severity="High").get_json()["data"]
    listing = client.get("/api/incidents").get_json()["data"]
    assert [i["id"] for i in listing] == [a["id"]] and listing[0]["title"] == "Checkout slow"
    one = client.get(f"/api/incidents/{a['id']}").get_json()["data"]
    assert one["description"] == DESC and one["result"]["severity_signals"]["reported"] == "High"
    assert client.delete(f"/api/incidents/{a['id']}").status_code == 200
    assert client.delete(f"/api/incidents/{a['id']}").status_code == 404
    analyze(client); analyze(client)
    assert client.delete("/api/incidents").get_json()["data"]["deleted"] == 2


def test_history_can_be_disabled():
    from incident_intel.app import create_app
    from tests.conftest import make_settings
    c = create_app(make_settings(history_enabled=False)).test_client()
    assert analyze(c).status_code == 201
    r = c.get("/api/incidents")
    assert r.status_code == 404 and r.get_json()["error"]["code"] == "history_disabled"


def test_secrets_never_appear_in_logs(live_client, caplog, monkeypatch):
    import requests
    def boom(*a, **k):
        raise requests.ConnectionError(f"failed contacting host with key {SECRET}")
    monkeypatch.setattr(requests, "request", boom)
    with caplog.at_level(logging.DEBUG):
        r = analyze(live_client, provider="openai")
    assert r.status_code == 503
    assert SECRET not in r.get_data(as_text=True) and SECRET not in caplog.text
