"""HTTP API. All responses use one envelope: {"ok": true, "data": ...} or {"ok": false, "error": {...}}."""
import json
import os

from flask import Blueprint, current_app, jsonify, request

from . import __version__
from .errors import NotFoundError, ValidationError
from .providers import describe_providers

bp = Blueprint("api", __name__, url_prefix="/api")
SAMPLES_PATH = os.path.join(os.path.dirname(__file__), "samples.json")


def ok(data, status=200):


    """Wrap data in the success envelope."""
    return jsonify({"ok": True, "data": data}), status


@bp.get("/health")
def health():
    """Liveness check and non-sensitive runtime info."""
    s = current_app.extensions["settings"]
    return ok({"status": "ok", "version": __version__, "history_enabled": s.history_enabled,
               "default_provider": s.default_provider})


@bp.get("/providers")
def providers():
    """List providers and whether each is configured. Never includes keys."""
    s = current_app.extensions["settings"]
    return ok({"default": s.default_provider, "providers": describe_providers(s)})


@bp.get("/samples")
def samples():
    """Bundled, synthetic sample incidents for the UI."""
    with open(SAMPLES_PATH, encoding="utf-8") as f:
        return ok(json.load(f))


@bp.post("/analyze")
def analyze():
    """Analyze an incident. Uses DEFAULT_PROVIDER when the request names no provider."""
    payload = request.get_json(silent=True)
    if payload is None:
        raise ValidationError("Request body must be valid JSON.")
    if isinstance(payload, dict):
        payload.setdefault("provider", current_app.extensions["settings"].default_provider)
    return ok(current_app.extensions["service"].analyze(payload), 201)


def _storage():
    s = current_app.extensions["service"].storage
    if s is None:
        raise NotFoundError("Incident history is disabled (HISTORY_ENABLED=false).", code="history_disabled")
    return s


@bp.get("/incidents")
def list_incidents():
    """Saved analyses, newest first (summary fields only)."""
    return ok(_storage().list())


@bp.get("/incidents/<incident_id>")
def get_incident(incident_id):
    """One saved incident with its full analysis."""
    item = _storage().get(incident_id)
    if not item:
        raise NotFoundError("Incident not found.")
    return ok(item)


@bp.delete("/incidents/<incident_id>")
def delete_incident(incident_id):
    """Delete one saved incident and its analysis."""
    if not _storage().delete(incident_id):
        raise NotFoundError("Incident not found.")
    return ok({"deleted": incident_id})


@bp.delete("/incidents")
def clear_incidents():
    """Delete all saved history."""
    return ok({"deleted": _storage().clear()})
