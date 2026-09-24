-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Incidents table
CREATE TABLE IF NOT EXISTS incidents (
    id TEXT PRIMARY KEY,
    fingerprint TEXT NOT NULL,
    severity TEXT NOT NULL,
    status TEXT NOT NULL,
    service TEXT NOT NULL,
    opened_at TIMESTAMPTZ NOT NULL,
    acked_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,
    summary TEXT,
    root_cause_hypothesis TEXT
);

-- Alerts table
CREATE TABLE IF NOT EXISTS alerts (
    id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    raw_payload JSONB NOT NULL,
    received_at TIMESTAMPTZ NOT NULL
);

-- Runbooks table
CREATE TABLE IF NOT EXISTS runbooks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    service TEXT NOT NULL,
    tags TEXT[] NOT NULL DEFAULT '{}',
    source_url TEXT,
    last_verified_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    owner TEXT NOT NULL
);

-- Runbook Chunks table with Dual Representation (Dense Vector + Sparse FTS)
CREATE TABLE IF NOT EXISTS runbook_chunks (
    id TEXT PRIMARY KEY,
    runbook_id TEXT NOT NULL REFERENCES runbooks(id) ON DELETE CASCADE,
    heading_path TEXT[] NOT NULL DEFAULT '{}',
    content TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    embedding VECTOR(768),
    fts TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
);

-- Approvals table
CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    call_id TEXT,
    command TEXT NOT NULL,
    tier TEXT NOT NULL,
    runbook_chunk_id TEXT REFERENCES runbook_chunks(id) ON DELETE SET NULL,
    transcript_span TEXT,
    approved_by TEXT NOT NULL,
    approved_at TIMESTAMPTZ NOT NULL,
    signature TEXT
);

-- Audit Log table
CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    incident_id TEXT REFERENCES incidents(id) ON DELETE SET NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}',
    at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_alerts_incident_id ON alerts(incident_id);
CREATE INDEX IF NOT EXISTS idx_runbook_chunks_runbook_id ON runbook_chunks(runbook_id);
CREATE INDEX IF NOT EXISTS idx_approvals_incident_id ON approvals(incident_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_incident_id ON audit_log(incident_id);

-- Hybrid Search Indexes: GIN for sparse BM25-like search, HNSW for dense cosine similarity
CREATE INDEX IF NOT EXISTS idx_runbook_chunks_fts ON runbook_chunks USING gin(fts);
CREATE INDEX IF NOT EXISTS idx_runbook_chunks_embedding ON runbook_chunks USING hnsw(embedding vector_cosine_ops);
