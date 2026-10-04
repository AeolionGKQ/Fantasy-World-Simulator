"""Explicit phase-two SQLite migrations."""

import hashlib


MIGRATIONS = (
    (1, """
CREATE TABLE content_revisions (
    id TEXT PRIMARY KEY,
    manifest_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE content_revision_documents (
    revision_id TEXT NOT NULL REFERENCES content_revisions(id) ON DELETE RESTRICT,
    document_id TEXT NOT NULL,
    category TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    source_path TEXT NOT NULL,
    raw_bytes BLOB NOT NULL,
    text_content TEXT NOT NULL,
    raw_sha256 TEXT NOT NULL,
    text_sha256 TEXT NOT NULL,
    encoding TEXT NOT NULL,
    has_bom INTEGER NOT NULL,
    newline_style TEXT NOT NULL,
    byte_count INTEGER NOT NULL,
    character_count INTEGER NOT NULL,
    line_count INTEGER NOT NULL,
    PRIMARY KEY(revision_id, document_id),
    UNIQUE(revision_id, category, ordinal)
);
CREATE TABLE story_states (
    save_id TEXT PRIMARY KEY REFERENCES saves(id) ON DELETE CASCADE,
    state_version INTEGER NOT NULL,
    current_turn_id TEXT,
    content_revision_id TEXT NOT NULL REFERENCES content_revisions(id) ON DELETE RESTRICT,
    state_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE location_nodes (
    save_id TEXT NOT NULL REFERENCES saves(id) ON DELETE CASCADE,
    id TEXT NOT NULL,
    name TEXT NOT NULL,
    location_type TEXT NOT NULL,
    parent_id TEXT,
    region_id TEXT NOT NULL,
    description TEXT NOT NULL,
    canonical INTEGER NOT NULL,
    created_turn_version_id TEXT,
    PRIMARY KEY(save_id, id)
);
CREATE TABLE narrative_jobs (
    id TEXT PRIMARY KEY,
    save_id TEXT NOT NULL REFERENCES saves(id) ON DELETE CASCADE,
    request_id TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL,
    job_type TEXT NOT NULL,
    source_state_version INTEGER NOT NULL,
    target_turn_id TEXT,
    status TEXT NOT NULL,
    input_json TEXT NOT NULL,
    context_manifest_json TEXT,
    result_json TEXT,
    error_code TEXT,
    error_message TEXT,
    retryable INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(save_id, request_id)
);
CREATE UNIQUE INDEX one_active_narrative_job_per_save
ON narrative_jobs(save_id)
WHERE status IN ('queued','running','cancel_requested');
CREATE TABLE turns (
    id TEXT PRIMARY KEY,
    save_id TEXT NOT NULL REFERENCES saves(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    current_version_id TEXT,
    action_type TEXT NOT NULL,
    action_json TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    summary TEXT NOT NULL,
    options_json TEXT NOT NULL,
    changes_json TEXT NOT NULL,
    state_version_before INTEGER NOT NULL,
    state_version_after INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(save_id, sequence)
);
CREATE TABLE turn_versions (
    id TEXT PRIMARY KEY,
    turn_id TEXT NOT NULL REFERENCES turns(id) ON DELETE CASCADE,
    save_id TEXT NOT NULL REFERENCES saves(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    raw_response_json TEXT NOT NULL,
    proposals_json TEXT NOT NULL,
    authoritative_changes_json TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    content_revision_id TEXT NOT NULL REFERENCES content_revisions(id) ON DELETE RESTRICT,
    model TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(turn_id, version_number)
);
CREATE TABLE turn_snapshots (
    turn_id TEXT PRIMARY KEY REFERENCES turns(id) ON DELETE CASCADE,
    save_id TEXT NOT NULL REFERENCES saves(id) ON DELETE CASCADE,
    snapshot_schema_version TEXT NOT NULL,
    state_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE effect_receipts (
    id TEXT PRIMARY KEY,
    save_id TEXT NOT NULL REFERENCES saves(id) ON DELETE CASCADE,
    turn_id TEXT NOT NULL REFERENCES turns(id) ON DELETE CASCADE,
    turn_version_id TEXT NOT NULL REFERENCES turn_versions(id) ON DELETE CASCADE,
    effect_key TEXT NOT NULL,
    effect_kind TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('active','revoked')),
    created_at TEXT NOT NULL,
    UNIQUE(save_id, turn_version_id, effect_key)
);
CREATE TABLE journals (
    turn_id TEXT PRIMARY KEY REFERENCES turns(id) ON DELETE CASCADE,
    save_id TEXT NOT NULL REFERENCES saves(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    location_id TEXT NOT NULL,
    time_label TEXT NOT NULL,
    changes_json TEXT NOT NULL,
    fallback_used INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(save_id, sequence)
);
CREATE TABLE memories (
    id TEXT PRIMARY KEY,
    save_id TEXT NOT NULL REFERENCES saves(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK(status IN ('active','resolved','superseded')),
    kind TEXT NOT NULL,
    summary TEXT NOT NULL,
    importance INTEGER NOT NULL,
    people_json TEXT NOT NULL,
    locations_json TEXT NOT NULL,
    keywords_json TEXT NOT NULL,
    facts_json TEXT NOT NULL,
    unresolved_json TEXT NOT NULL,
    superseded_by TEXT,
    source_turn_id TEXT NOT NULL,
    source_turn_version_id TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE memory_sources (
    memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    turn_version_id TEXT NOT NULL REFERENCES turn_versions(id) ON DELETE CASCADE,
    PRIMARY KEY(memory_id, turn_version_id)
);
CREATE TABLE story_arcs (
    id TEXT PRIMARY KEY,
    save_id TEXT NOT NULL REFERENCES saves(id) ON DELETE CASCADE,
    level INTEGER NOT NULL,
    start_sequence INTEGER NOT NULL,
    end_sequence INTEGER NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    key_events_json TEXT NOT NULL,
    unresolved_json TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('current','superseded')),
    job_id TEXT NOT NULL UNIQUE REFERENCES narrative_jobs(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    UNIQUE(save_id, level, start_sequence, end_sequence, source_hash)
);
CREATE TABLE story_arc_sources (
    arc_id TEXT NOT NULL REFERENCES story_arcs(id) ON DELETE CASCADE,
    turn_id TEXT NOT NULL REFERENCES turns(id) ON DELETE CASCADE,
    turn_version_id TEXT NOT NULL REFERENCES turn_versions(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    PRIMARY KEY(arc_id, ordinal),
    UNIQUE(arc_id, turn_id)
);
CREATE TABLE story_arc_parent_sources (
    arc_id TEXT NOT NULL REFERENCES story_arcs(id) ON DELETE CASCADE,
    parent_arc_id TEXT NOT NULL REFERENCES story_arcs(id) ON DELETE RESTRICT,
    ordinal INTEGER NOT NULL,
    PRIMARY KEY(arc_id, ordinal),
    UNIQUE(arc_id, parent_arc_id)
);
CREATE TABLE context_policies (
    id TEXT PRIMARY KEY,
    save_id TEXT NOT NULL REFERENCES saves(id) ON DELETE CASCADE,
    policy_type TEXT NOT NULL,
    source_json TEXT NOT NULL,
    replacement_arc_id TEXT NOT NULL REFERENCES story_arcs(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL
);
CREATE TABLE reputation_change_history (
    id TEXT PRIMARY KEY,
    save_id TEXT NOT NULL REFERENCES saves(id) ON DELETE CASCADE,
    turn_version_id TEXT NOT NULL REFERENCES turn_versions(id) ON DELETE CASCADE,
    reputation_key TEXT NOT NULL,
    old_value INTEGER NOT NULL,
    new_value INTEGER NOT NULL,
    public_reason TEXT NOT NULL,
    accepted INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
"""),
    (2, """
DROP INDEX IF EXISTS one_active_narrative_job_per_save;
CREATE UNIQUE INDEX one_active_state_job_per_save
ON narrative_jobs(save_id)
WHERE status IN ('queued','running','cancel_requested')
AND job_type IN ('opening','turn','intervene','reshape');
CREATE UNIQUE INDEX one_active_arc_job_per_save
ON narrative_jobs(save_id)
WHERE status IN ('queued','running','cancel_requested')
AND job_type IN ('turns_to_arc','arcs_to_arc');
"""),
    (3, """
CREATE TABLE trusted_content_revisions (
    revision_id TEXT PRIMARY KEY REFERENCES content_revisions(id) ON DELETE CASCADE,
    trust_kind TEXT NOT NULL CHECK(trust_kind IN ('builtin','user')),
    trusted_at TEXT NOT NULL
);
CREATE TABLE pending_imports (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE,
    revision_id TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    payload_json BLOB NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending','imported','expired')),
    trust_request_id TEXT,
    result_json TEXT,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE INDEX pending_import_expiry ON pending_imports(status,expires_at);
"""),
    (4, """
CREATE TABLE response_format_capabilities (
    endpoint TEXT NOT NULL,
    model TEXT NOT NULL,
    config_version TEXT NOT NULL,
    capability TEXT NOT NULL CHECK (capability IN ('supported','unsupported','unknown')),
    strategy TEXT,
    last_failure TEXT,
    probed_at TEXT NOT NULL,
    PRIMARY KEY(endpoint, model, config_version)
);
UPDATE settings
SET model_json=json_set(model_json, '$.structured_output', json('false'))
WHERE COALESCE(json_extract(model_json, '$.base_url'), '')=''
  AND COALESCE(json_extract(model_json, '$.model'), '')=''
  AND (json_type(model_json, '$.structured_output') IS NULL
       OR json_extract(model_json, '$.structured_output')=1);
"""),
    (5, """
UPDATE settings
SET model_json=json_set(model_json, '$.max_concurrency', 2)
WHERE revision=0
  AND COALESCE(json_extract(model_json, '$.base_url'), '')=''
  AND COALESCE(json_extract(model_json, '$.model'), '')=''
  AND (json_type(model_json, '$.max_concurrency') IS NULL
       OR json_extract(model_json, '$.max_concurrency')=1);
"""),
    (6, """
UPDATE settings
SET narration_json=json_set(narration_json, '$.player_address', 'second_person')
WHERE json_type(narration_json, '$.player_address') IS NULL;
UPDATE saves
SET preferences_json=json_set(preferences_json, '$.player_address', 'second_person')
WHERE json_type(preferences_json, '$.player_address') IS NULL;
UPDATE story_states
SET state_json=json_set(state_json, '$.narration.player_address', 'second_person')
WHERE json_type(state_json, '$.narration.player_address') IS NULL;
UPDATE turn_snapshots
SET state_json=json_set(state_json, '$.state.narration.player_address', 'second_person')
WHERE json_type(state_json, '$.state.narration.player_address') IS NULL;
"""),
    (7, """
UPDATE saves
SET preferences_json=(SELECT narration_json FROM settings WHERE id=1),
    revision=revision+1
WHERE EXISTS (SELECT 1 FROM settings WHERE id=1)
  AND COALESCE(json_extract(preferences_json, '$.player_address'), 'second_person')='second_person'
  AND json_extract((SELECT narration_json FROM settings WHERE id=1), '$.player_address')<>'second_person';
UPDATE story_states
SET state_json=json_set(
    state_json,
    '$.narration',
    json((SELECT preferences_json FROM saves WHERE saves.id=story_states.save_id))
)
WHERE EXISTS (SELECT 1 FROM saves WHERE saves.id=story_states.save_id);
"""),
    (8, """
DELETE FROM memories WHERE status<>'active';
"""),
    (9, """
DELETE FROM story_arc_parent_sources;
DELETE FROM mutation_requests;
DELETE FROM pending_imports;
DELETE FROM confirmation_requests;
DELETE FROM narrative_jobs;
DELETE FROM turns;
DROP TABLE IF EXISTS location_nodes;
CREATE TABLE location_nodes (
    save_id TEXT NOT NULL REFERENCES saves(id) ON DELETE CASCADE,
    id TEXT NOT NULL,
    name TEXT NOT NULL,
    location_type TEXT NOT NULL,
    scope TEXT NOT NULL CHECK(scope IN ('world','region','place')),
    parent_id TEXT,
    region_id TEXT NOT NULL,
    jurisdiction_id TEXT,
    description TEXT NOT NULL,
    canonical INTEGER NOT NULL,
    created_turn_version_id TEXT,
    PRIMARY KEY(save_id, id)
);
DELETE FROM story_states;
DELETE FROM characters;
DELETE FROM candidates;
DELETE FROM generation_jobs;
UPDATE saves SET phase='draft', revision=revision+1, updated_at=CURRENT_TIMESTAMP;
UPDATE drafts SET current_step=1, revision=revision+1, updated_at=CURRENT_TIMESTAMP;
"""),
    (10, """
ALTER TABLE turn_versions ADD COLUMN action_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE turn_versions ADD COLUMN generated_ids_json TEXT NOT NULL DEFAULT '[]';
"""),
)


def apply_migrations(connection, now):
    connection.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            checksum TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
    """)
    applied = {row["version"]: row["checksum"] for row in connection.execute(
        "SELECT version,checksum FROM schema_migrations").fetchall()}
    for version, sql in MIGRATIONS:
        checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
        if version in applied:
            if applied[version] != checksum:
                raise RuntimeError(f"migration {version} checksum mismatch")
            continue
        safe_now = now.replace("'", "''")
        connection.executescript(
            "BEGIN IMMEDIATE;\n" + sql +
            f"\nINSERT INTO schema_migrations(version,checksum,applied_at) VALUES({version},'{checksum}','{safe_now}');\n"
            "COMMIT;"
        )
