"""Flask application factory. Serves the JSON API and the static frontend."""
import os

from dotenv import load_dotenv
from flask import Flask, jsonify, send_from_directory
from werkzeug.exceptions import HTTPException

from .analysis import AnalysisService
from .api import bp
from .config import Settings
from .errors import AppError
from .logging_utils import get_logger
from .storage import Storage

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
log = get_logger()


def create_app(settings=None):


    """Build the Flask app: settings, storage, API blueprint, error handlers and static frontend."""
    load_dotenv()
    settings = settings or Settings.from_env()
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024  # reject oversized bodies

    storage = Storage(settings.database_path) if settings.history_enabled else None
    app.extensions["settings"] = settings
    app.extensions["service"] = AnalysisService(settings, storage)
    app.register_blueprint(bp)

    @app.errorhandler(AppError)
    def handle_app_error(e):
        return jsonify({"ok": False, "error": {"code": e.code, "message": e.message}}), e.status

    @app.errorhandler(HTTPException)
    def handle_http_error(e):
        code = {413: "payload_too_large", 404: "not_found", 405: "method_not_allowed"}.get(e.code, "http_error")
        return jsonify({"ok": False, "error": {"code": code, "message": e.description}}), e.code

    @app.errorhandler(Exception)
    def handle_unexpected(e):
        """Catch-all: log the traceback server-side only; return a generic message to the client."""
        log.exception("unhandled error")  # stack trace stays in the server log, not in the response
        return jsonify({"ok": False, "error": {"code": "internal_error", "message": "Unexpected server error."}}), 500

    @app.get("/")
    def index():
        return send_from_directory(FRONTEND_DIR, "index.html")

    @app.get("/static/<path:name>")
    def static_files(name):
        return send_from_directory(FRONTEND_DIR, name)

    return app
