-- Menu Helper V1.1 PostgreSQL schema.
-- v1_1_menu_store.py applies this file and records the version. Existing rows
-- are never dropped or truncated by this script.

CREATE TABLE IF NOT EXISTS menu_schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS menu_stores (
    store_id UUID PRIMARY KEY,
    identity_key TEXT NOT NULL UNIQUE,
    restaurant_name TEXT,
    platform TEXT NOT NULL,
    platform_store_id TEXT,
    source_host TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS menu_sources (
    source_id UUID PRIMARY KEY,
    store_id UUID NOT NULL REFERENCES menu_stores(store_id),
    locator_key TEXT NOT NULL UNIQUE,
    source_key TEXT NOT NULL UNIQUE,
    platform TEXT NOT NULL,
    sales_channel TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    source_host TEXT NOT NULL,
    source_path TEXT NOT NULL,
    source_identity JSONB NOT NULL DEFAULT '{}'::jsonb,
    current_snapshot_id UUID,
    last_checked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS menu_snapshots (
    snapshot_id UUID PRIMARY KEY,
    source_id UUID NOT NULL REFERENCES menu_sources(source_id),
    version INTEGER NOT NULL CHECK (version > 0),
    previous_snapshot_id UUID REFERENCES menu_snapshots(snapshot_id),
    content_hash CHAR(64) NOT NULL,
    extraction_status TEXT NOT NULL CHECK (
        extraction_status IN ('success', 'partial')
    ),
    validation_status TEXT NOT NULL,
    extraction_method TEXT NOT NULL,
    extraction_version TEXT NOT NULL,
    menu_schema_version TEXT NOT NULL,
    common_menu JSONB NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_id, version)
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'menu_sources_current_snapshot_fk'
    ) THEN
        ALTER TABLE menu_sources
            ADD CONSTRAINT menu_sources_current_snapshot_fk
            FOREIGN KEY (current_snapshot_id)
            REFERENCES menu_snapshots(snapshot_id)
            DEFERRABLE INITIALLY DEFERRED;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS extraction_attempts (
    attempt_id UUID PRIMARY KEY,
    request_id TEXT NOT NULL,
    source_id UUID REFERENCES menu_sources(source_id),
    snapshot_id UUID REFERENCES menu_snapshots(snapshot_id),
    outcome TEXT NOT NULL CHECK (
        outcome IN ('success', 'partial', 'failure', 'reused')
    ),
    failure_stage TEXT,
    error_code TEXT,
    reused_snapshot BOOLEAN NOT NULL DEFAULT FALSE,
    diagnostics JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS source_artifacts (
    artifact_id UUID PRIMARY KEY,
    source_id UUID NOT NULL REFERENCES menu_sources(source_id),
    snapshot_id UUID REFERENCES menu_snapshots(snapshot_id),
    attempt_id UUID REFERENCES extraction_attempts(attempt_id),
    artifact_role TEXT NOT NULL,
    content_type TEXT,
    content_sha256 CHAR(64) NOT NULL,
    storage_kind TEXT NOT NULL CHECK (
        storage_kind IN ('postgres_gzip', 'external', 'omitted')
    ),
    content_encoding TEXT,
    original_bytes INTEGER NOT NULL CHECK (original_bytes >= 0),
    stored_bytes INTEGER NOT NULL CHECK (stored_bytes >= 0),
    payload BYTEA,
    storage_uri TEXT,
    safe_to_store BOOLEAN NOT NULL,
    omission_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_id, artifact_role, content_sha256)
);

CREATE TABLE IF NOT EXISTS menu_item_details (
    detail_id UUID PRIMARY KEY,
    snapshot_id UUID NOT NULL REFERENCES menu_snapshots(snapshot_id),
    source_product_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    item_detail JSONB NOT NULL,
    extraction_method TEXT NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (snapshot_id, source_product_id)
);

CREATE INDEX IF NOT EXISTS menu_snapshots_source_created_idx
    ON menu_snapshots(source_id, created_at DESC);
CREATE INDEX IF NOT EXISTS menu_snapshots_source_hash_idx
    ON menu_snapshots(source_id, content_hash);
CREATE INDEX IF NOT EXISTS extraction_attempts_request_idx
    ON extraction_attempts(request_id);
CREATE INDEX IF NOT EXISTS source_artifacts_snapshot_idx
    ON source_artifacts(snapshot_id);
CREATE INDEX IF NOT EXISTS menu_item_details_snapshot_idx
    ON menu_item_details(snapshot_id);

INSERT INTO menu_schema_migrations(version)
VALUES ('v1_1_001_menu_snapshots')
ON CONFLICT (version) DO NOTHING;

INSERT INTO menu_schema_migrations(version)
VALUES ('v1_1_002_snapshot_item_details')
ON CONFLICT (version) DO NOTHING;
