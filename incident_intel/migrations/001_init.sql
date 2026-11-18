-- Incidents submitted for analysis, and the analysis produced for each.
-- No credentials are ever stored. Provider/model are metadata only.
CREATE TABLE incidents (
    id                TEXT PRIMARY KEY,
    title             TEXT,
    description       TEXT NOT NULL,
    service           TEXT,
    reported_severity TEXT CHECK (reported_severity IN ('Critical','High','Medium','Low')),
    created_at        TEXT NOT NULL
);

CREATE TABLE analyses (
    id                TEXT PRIMARY KEY,
    incident_id       TEXT NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    provider          TEXT NOT NULL,
    model             TEXT NOT NULL,
    simulated         INTEGER NOT NULL CHECK (simulated IN (0,1)),
    severity          TEXT NOT NULL CHECK (severity IN ('Critical','High','Medium','Low')),
    suggested_priority TEXT NOT NULL,
    result_json       TEXT NOT NULL,
    latency_ms        INTEGER,
    created_at        TEXT NOT NULL
);

CREATE INDEX idx_analyses_incident ON analyses(incident_id);
CREATE INDEX idx_incidents_created ON incidents(created_at DESC);
