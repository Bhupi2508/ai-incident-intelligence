import sqlite3

from incident_intel.storage import Storage


def test_migrations_apply_once_and_are_idempotent(tmp_path):
    path = str(tmp_path / "t.db")
    first = Storage(path)
    assert first.migrate() == []                        # already applied by __init__
    Storage(path)                                       # reopen: no error, no re-run
    con = sqlite3.connect(path)
    assert [r[0] for r in con.execute("SELECT version FROM schema_migrations")] == ["001_init.sql"]
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"incidents", "analyses", "schema_migrations"} <= tables


def test_schema_has_no_credential_columns(tmp_path):
    con = sqlite3.connect(str(tmp_path / "t.db")); Storage(str(tmp_path / "t.db"))
    cols = {r[1] for r in con.execute("PRAGMA table_info(analyses)")} | {r[1] for r in con.execute("PRAGMA table_info(incidents)")}
    assert not any("key" in c or "secret" in c or "token" in c for c in cols)


def test_cascade_delete(tmp_path):
    s = Storage(str(tmp_path / "t.db"))
    s.save({"id": "a", "description": "d" * 20, "created_at": "t"},
           {"id": "x", "provider": "demo", "model": "m", "simulated": True, "severity": "Low",
            "suggested_priority": "P4", "result": {"summary": "s"}, "created_at": "t"})
    assert s.get("a")["summary"] == "s"
    assert s.delete("a") and s.get("a") is None
    assert sqlite3.connect(s.path).execute("SELECT COUNT(*) FROM analyses").fetchone()[0] == 0


def test_seed_populates_demo_incidents(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "seed.db"))
    monkeypatch.setattr("incident_intel.seed.load_dotenv", lambda *a, **k: None)
    from incident_intel import seed
    seed.main()
    items = Storage(str(tmp_path / "seed.db")).list()
    assert len(items) == 5 and all(i["simulated"] for i in items)
