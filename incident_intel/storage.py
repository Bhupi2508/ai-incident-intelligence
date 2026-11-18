"""SQLite persistence with simple versioned SQL migrations (migrations/NNN_name.sql)."""
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "migrations")


def utc_now():


    """Current UTC time as an ISO-8601 string ending in Z."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class Storage:


    """SQLite access. Uses one short-lived connection per call (or a shared one for :memory:)."""
    def __init__(self, path):
        self.path = path
        if path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self._memory_conn = sqlite3.connect(":memory:", check_same_thread=False) if path == ":memory:" else None
        self.migrate()

    @contextmanager
    def _conn(self):
        conn = self._memory_conn or sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            if conn is not self._memory_conn:
                conn.close()

    def migrate(self):
        """Apply pending migrations in filename order. Returns the list applied."""
        files = sorted(f for f in os.listdir(MIGRATIONS_DIR) if re.match(r"^\d+_.+\.sql$", f))
        applied_now = []
        with self._conn() as c:
            c.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
            done = {r["version"] for r in c.execute("SELECT version FROM schema_migrations")}
            for f in files:
                if f in done:
                    continue
                with open(os.path.join(MIGRATIONS_DIR, f), encoding="utf-8") as fh:
                    c.executescript(fh.read())
                c.execute("INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)", (f, utc_now()))
                applied_now.append(f)
        return applied_now

    def save(self, incident, analysis):

        """Insert an incident and its analysis in one transaction."""
        with self._conn() as c:
            c.execute("INSERT INTO incidents(id,title,description,service,reported_severity,created_at) "
                      "VALUES (?,?,?,?,?,?)",
                      (incident["id"], incident.get("title"), incident["description"], incident.get("service"),
                       incident.get("reported_severity"), incident["created_at"]))
            c.execute("INSERT INTO analyses(id,incident_id,provider,model,simulated,severity,suggested_priority,"
                      "result_json,latency_ms,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (analysis["id"], incident["id"], analysis["provider"], analysis["model"],
                       int(analysis["simulated"]), analysis["severity"], analysis["suggested_priority"],
                       json.dumps(analysis["result"]), analysis.get("latency_ms"), analysis["created_at"]))

    _SELECT = ("SELECT i.id, i.title, i.description, i.service, i.reported_severity, i.created_at AS incident_created_at, "
               "a.id AS analysis_id, a.provider, a.model, a.simulated, a.severity, a.suggested_priority, "
               "a.result_json, a.latency_ms, a.created_at AS analysis_created_at "
               "FROM incidents i JOIN analyses a ON a.incident_id = i.id ")

    @staticmethod
    def _row(r, full=True):
        d = {"id": r["id"], "title": r["title"], "service": r["service"],
             "reported_severity": r["reported_severity"], "created_at": r["incident_created_at"],
             "provider": r["provider"], "model": r["model"], "simulated": bool(r["simulated"]),
             "severity": r["severity"], "suggested_priority": r["suggested_priority"],
             "summary": json.loads(r["result_json"]).get("summary", "")}
        if full:
            d.update(description=r["description"], latency_ms=r["latency_ms"],
                     analysis_id=r["analysis_id"], result=json.loads(r["result_json"]))
        return d

    def list(self, limit=50):

        """Newest-first summaries."""
        with self._conn() as c:
            rows = c.execute(self._SELECT + "ORDER BY i.created_at DESC, i.rowid DESC LIMIT ?", (limit,)).fetchall()
        return [self._row(r, full=False) for r in rows]

    def get(self, incident_id):

        """Full record or None."""
        with self._conn() as c:
            r = c.execute(self._SELECT + "WHERE i.id = ?", (incident_id,)).fetchone()
        return self._row(r) if r else None

    def delete(self, incident_id):

        """Delete one incident (analysis cascades). Returns True if it existed."""
        with self._conn() as c:
            return c.execute("DELETE FROM incidents WHERE id = ?", (incident_id,)).rowcount > 0

    def clear(self):

        """Delete everything; returns the number of incidents removed."""
        with self._conn() as c:
            return c.execute("DELETE FROM incidents").rowcount
