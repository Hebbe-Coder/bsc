"""Portable knowledge-store schema initialization."""

from __future__ import annotations

from typing import Any

from app.knowledge.growth_contracts import FAILURE_PATTERN_BY_CODE


_COMMON_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS knowledge_docs (
        id TEXT PRIMARY KEY, project_id TEXT, asset_id TEXT,
        title TEXT, source TEXT, created_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS knowledge_chunks (
        id TEXT PRIMARY KEY, doc_id TEXT, idx INTEGER,
        content TEXT, section TEXT, metadata_json TEXT)""",
    """CREATE TABLE IF NOT EXISTS knowledge_tfidf (
        chunk_id TEXT PRIMARY KEY, vector BLOB)""",
    """CREATE TABLE IF NOT EXISTS tfidf_model (
        id INTEGER PRIMARY KEY CHECK (id=1), vocab_json TEXT, idf_json TEXT)""",
    """CREATE TABLE IF NOT EXISTS knowledge_vectors (
        chunk_id TEXT PRIMARY KEY, model TEXT, dim INTEGER, vector BLOB)""",
    """CREATE TABLE IF NOT EXISTS project_members (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, user_id TEXT NOT NULL,
        role TEXT NOT NULL, joined_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS knowledge_projects (
        id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL DEFAULT 'default',
        name TEXT NOT NULL, created_at TEXT NOT NULL,
        metadata TEXT DEFAULT '{}', rerank_config TEXT DEFAULT '{}')""",
    """CREATE TABLE IF NOT EXISTS project_keys (
        key_hash TEXT PRIMARY KEY, project_id TEXT NOT NULL, role TEXT NOT NULL,
        label TEXT, created_at TEXT NOT NULL,
        FOREIGN KEY(project_id) REFERENCES knowledge_projects(id))""",
]


# Schema initialization is invoked by API, Worker, and Beat processes. PostgreSQL
# serializes ordinary DML correctly, but concurrent ``CREATE INDEX IF NOT EXISTS``
# statements can still deadlock while bootstrap migrations are running. A stable,
# session-scoped advisory lock keeps the whole migration sequence single-flight,
# including helpers that may need their own transaction boundary in the future.
_POSTGRES_SCHEMA_ADVISORY_LOCK = 7_485_216_203
_POSTGRES_SCHEMA_READY_ATTRIBUTE = "_bsc_knowledge_schema_ready"


_WIKI_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS knowledge_vaults (
        project_id TEXT PRIMARY KEY, vault_path TEXT NOT NULL, status TEXT NOT NULL,
        configured_by TEXT DEFAULT '', metadata_json TEXT DEFAULT '{}',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS knowledge_sources (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, source_type TEXT NOT NULL,
        origin TEXT DEFAULT '', vault_path TEXT DEFAULT '', content_hash TEXT NOT NULL,
        raw_content TEXT NOT NULL DEFAULT '',
        trust_level TEXT NOT NULL DEFAULT 'untrusted', status TEXT NOT NULL,
        metadata_json TEXT DEFAULT '{}', supersedes_id TEXT,
        captured_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS knowledge_source_capture_attempts (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, source_type TEXT NOT NULL,
        origin TEXT DEFAULT '', content_hash TEXT DEFAULT '', run_id TEXT DEFAULT '',
        source_id TEXT DEFAULT '', outcome TEXT NOT NULL, policy_json TEXT NOT NULL DEFAULT '{}',
        projection_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS knowledge_horizon_import_claims (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, horizon_run_id TEXT NOT NULL,
        horizon_stage TEXT NOT NULL, horizon_item_id TEXT NOT NULL, content_hash TEXT NOT NULL,
        capture_run_id TEXT DEFAULT '', status TEXT NOT NULL, source_id TEXT DEFAULT '',
        lease_expires_at TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        UNIQUE(project_id,horizon_run_id,horizon_stage,horizon_item_id))""",
    """CREATE TABLE IF NOT EXISTS knowledge_wiki_pages (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, path TEXT NOT NULL,
        title TEXT DEFAULT '', page_kind TEXT DEFAULT 'general', content_hash TEXT DEFAULT '',
        version INTEGER NOT NULL DEFAULT 1, metadata_json TEXT DEFAULT '{}',
        status TEXT NOT NULL DEFAULT 'published', published_at TEXT,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        UNIQUE(project_id, path))""",
    """CREATE TABLE IF NOT EXISTS knowledge_wiki_page_revisions (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, wiki_page_id TEXT NOT NULL,
        version INTEGER NOT NULL, content_hash TEXT NOT NULL, content TEXT NOT NULL,
        proposal_id TEXT DEFAULT '', created_at TEXT NOT NULL,
        UNIQUE(wiki_page_id, version))""",
    """CREATE TABLE IF NOT EXISTS knowledge_proposals (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, base_revision TEXT DEFAULT '',
        source_ids_json TEXT DEFAULT '[]', operations_json TEXT NOT NULL DEFAULT '[]',
        rationale TEXT DEFAULT '', status TEXT NOT NULL, eval_summary_json TEXT DEFAULT '{}',
        manual INTEGER NOT NULL DEFAULT 0, actor_id TEXT DEFAULT '',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS knowledge_proposal_operations (
        id TEXT PRIMARY KEY, proposal_id TEXT NOT NULL, project_id TEXT NOT NULL,
        operation_index INTEGER NOT NULL, operation_type TEXT NOT NULL, target_path TEXT NOT NULL,
        destination_path TEXT DEFAULT '', expected_content_hash TEXT DEFAULT '', content TEXT DEFAULT '',
        source_ids_json TEXT DEFAULT '[]', UNIQUE(proposal_id, operation_index))""",
    """CREATE TABLE IF NOT EXISTS knowledge_citations (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, wiki_page_id TEXT NOT NULL,
        source_id TEXT NOT NULL, anchor TEXT DEFAULT '', claim_text TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS knowledge_runs (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, run_type TEXT NOT NULL,
        trigger TEXT NOT NULL, status TEXT NOT NULL, actor_id TEXT DEFAULT '',
        input_refs_json TEXT DEFAULT '{}', output_refs_json TEXT DEFAULT '{}', error TEXT DEFAULT '',
        retry_of TEXT, started_at TEXT, completed_at TEXT,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS knowledge_run_events (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, run_id TEXT NOT NULL,
        sequence INTEGER NOT NULL, event_type TEXT NOT NULL,
        payload_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
        UNIQUE(run_id, sequence))""",
    """CREATE TABLE IF NOT EXISTS knowledge_schedules (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, job_type TEXT NOT NULL,
        cron TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 0, timezone TEXT NOT NULL,
        last_run_at TEXT, next_run_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS knowledge_schedule_claims (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, job_type TEXT NOT NULL,
        idempotency_key TEXT NOT NULL, run_id TEXT NOT NULL, created_at TEXT NOT NULL,
        UNIQUE(project_id, job_type, idempotency_key))""",
    """CREATE TABLE IF NOT EXISTS knowledge_distillations (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, week TEXT NOT NULL,
        knowledge_path TEXT NOT NULL, content_path TEXT NOT NULL, context_path TEXT NOT NULL,
        source_cutoff TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
        UNIQUE(project_id, week, source_cutoff))""",
    """CREATE TABLE IF NOT EXISTS knowledge_graph_edges (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, from_id TEXT NOT NULL,
        to_id TEXT NOT NULL, edge_type TEXT NOT NULL, metadata_json TEXT DEFAULT '{}',
        revision TEXT DEFAULT '', created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS knowledge_eval_runs (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, proposal_id TEXT,
        wiki_revision TEXT DEFAULT '', status TEXT NOT NULL, summary_json TEXT DEFAULT '{}',
        created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS knowledge_eval_cases (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, case_id TEXT NOT NULL,
        case_type TEXT NOT NULL, expected_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        UNIQUE(project_id, case_id))""",
    """CREATE TABLE IF NOT EXISTS knowledge_project_profiles (
        project_id TEXT PRIMARY KEY, revision INTEGER NOT NULL DEFAULT 1,
        profile_json TEXT NOT NULL DEFAULT '{}', actor_id TEXT DEFAULT '',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS knowledge_project_profile_revisions (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, revision INTEGER NOT NULL,
        profile_json TEXT NOT NULL DEFAULT '{}', actor_id TEXT DEFAULT '',
        created_at TEXT NOT NULL, UNIQUE(project_id, revision))""",
    """CREATE TABLE IF NOT EXISTS knowledge_source_triage (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, source_id TEXT NOT NULL,
        profile_revision INTEGER NOT NULL, relevance INTEGER NOT NULL,
        value_score INTEGER NOT NULL, freshness INTEGER NOT NULL,
        outputability INTEGER NOT NULL, connectedness INTEGER NOT NULL,
        priority INTEGER NOT NULL, reliability_pass INTEGER NOT NULL,
        disposition TEXT NOT NULL, reasons_json TEXT NOT NULL DEFAULT '[]',
        evaluator_revision TEXT NOT NULL DEFAULT '', evaluator_status TEXT NOT NULL DEFAULT 'completed',
        created_at TEXT NOT NULL,
        UNIQUE(project_id, source_id, profile_revision, evaluator_revision))""",
    """CREATE TABLE IF NOT EXISTS knowledge_candidates (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, source_id TEXT NOT NULL,
        source_content_hash TEXT NOT NULL, extraction_run_id TEXT NOT NULL,
        candidate_type TEXT NOT NULL, title TEXT NOT NULL, claim TEXT NOT NULL,
        explanation TEXT NOT NULL DEFAULT '', evidence_json TEXT NOT NULL DEFAULT '[]',
        fingerprint TEXT NOT NULL, status TEXT NOT NULL, reviewer_id TEXT NOT NULL DEFAULT '',
        review_note TEXT NOT NULL DEFAULT '', reviewed_at TEXT, metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        UNIQUE(project_id, fingerprint))""",
    """CREATE TABLE IF NOT EXISTS knowledge_methods (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, slug TEXT NOT NULL,
        name TEXT NOT NULL, applicability_json TEXT NOT NULL DEFAULT '[]',
        exclusions_json TEXT NOT NULL DEFAULT '[]', status TEXT NOT NULL,
        active_revision_id TEXT DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        UNIQUE(project_id, slug))""",
    """CREATE TABLE IF NOT EXISTS knowledge_method_revisions (
        id TEXT PRIMARY KEY, method_id TEXT NOT NULL, project_id TEXT NOT NULL,
        version INTEGER NOT NULL, body TEXT NOT NULL, manifest_json TEXT NOT NULL DEFAULT '{}',
        eval_summary_json TEXT NOT NULL DEFAULT '{}', status TEXT NOT NULL, created_at TEXT NOT NULL,
        UNIQUE(method_id, version))""",
    """CREATE TABLE IF NOT EXISTS knowledge_method_proposals (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, method_id TEXT DEFAULT '',
        operation TEXT NOT NULL, body TEXT NOT NULL, manifest_json TEXT NOT NULL DEFAULT '{}',
        source_output_ids_json TEXT NOT NULL DEFAULT '[]', rationale TEXT DEFAULT '',
        status TEXT NOT NULL, package_audit_json TEXT NOT NULL DEFAULT '{}', eval_summary_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS knowledge_method_evolution_runs (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, method_id TEXT NOT NULL,
        baseline_revision_id TEXT NOT NULL, mutation_dimension TEXT NOT NULL,
        rationale TEXT NOT NULL, supporting_output_ids_json TEXT NOT NULL DEFAULT '[]',
        candidate_proposal_id TEXT NOT NULL, input_fingerprint TEXT NOT NULL,
        evaluation_summary_json TEXT NOT NULL DEFAULT '{}', decision TEXT NOT NULL,
        rollback_revision_id TEXT NOT NULL, status TEXT NOT NULL,
        idempotency_key TEXT NOT NULL, actor_id TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        UNIQUE(project_id, idempotency_key))""",
    """CREATE TABLE IF NOT EXISTS knowledge_outputs (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, kind TEXT NOT NULL, title TEXT DEFAULT '',
        mime_type TEXT NOT NULL DEFAULT 'text/markdown', content_hash TEXT NOT NULL,
        vault_path TEXT NOT NULL, run_id TEXT DEFAULT '', method_revision_id TEXT DEFAULT '',
        context_revision TEXT DEFAULT '', source_refs_json TEXT NOT NULL DEFAULT '[]',
        page_refs_json TEXT NOT NULL DEFAULT '[]', idempotency_key TEXT NOT NULL,
        status TEXT NOT NULL, quality_json TEXT NOT NULL DEFAULT '{}', metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        UNIQUE(project_id, idempotency_key))""",
    """CREATE TABLE IF NOT EXISTS knowledge_output_evaluations (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, output_id TEXT NOT NULL,
        groundedness REAL NOT NULL, task_fit REAL NOT NULL, usefulness REAL NOT NULL,
        coherence REAL NOT NULL, format_quality REAL NOT NULL, quality INTEGER NOT NULL,
        status TEXT NOT NULL, evaluator_revision TEXT NOT NULL, findings_json TEXT NOT NULL DEFAULT '[]',
        latency_ms INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
        UNIQUE(project_id, output_id, evaluator_revision))""",
    """CREATE TABLE IF NOT EXISTS knowledge_output_feedback (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, output_id TEXT NOT NULL,
        feedback_type TEXT NOT NULL, actor_id TEXT DEFAULT '', rating INTEGER,
        correction TEXT DEFAULT '', comment TEXT DEFAULT '', status TEXT NOT NULL,
        processed_at TEXT, processed_ref TEXT DEFAULT '', created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS knowledge_growth_distillations (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, period TEXT NOT NULL,
        kind TEXT NOT NULL, input_hash TEXT NOT NULL, paths_json TEXT NOT NULL DEFAULT '[]',
        manifest_json TEXT NOT NULL DEFAULT '{}', status TEXT NOT NULL,
        created_at TEXT NOT NULL, UNIQUE(project_id,kind,period,input_hash))""",
    """CREATE TABLE IF NOT EXISTS knowledge_failure_records (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, code TEXT NOT NULL,
        diagnostic_pattern TEXT NOT NULL DEFAULT '',
        secondary_diagnostic_patterns_json TEXT NOT NULL DEFAULT '[]',
        severity TEXT NOT NULL, summary TEXT NOT NULL, run_id TEXT DEFAULT '',
        event_sequence INTEGER, evidence_refs_json TEXT NOT NULL DEFAULT '[]',
        root_cause TEXT DEFAULT '', minimal_structural_fix TEXT DEFAULT '', retryable INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL, resolution_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS knowledge_media_assets (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, source_id TEXT NOT NULL,
        mime_type TEXT NOT NULL, byte_hash TEXT NOT NULL, byte_size INTEGER NOT NULL,
        storage_ref TEXT NOT NULL, rights TEXT NOT NULL DEFAULT 'unknown',
        access_state TEXT NOT NULL DEFAULT 'available', metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        UNIQUE(project_id,source_id,byte_hash,storage_ref))""",
    """CREATE TABLE IF NOT EXISTS knowledge_extraction_artifacts (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, source_id TEXT NOT NULL,
        asset_id TEXT NOT NULL, extractor TEXT NOT NULL, extractor_revision TEXT NOT NULL,
        input_hash TEXT NOT NULL, content_hash TEXT NOT NULL DEFAULT '', content TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL, error TEXT NOT NULL DEFAULT '', metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        UNIQUE(project_id,source_id,asset_id,extractor,extractor_revision,input_hash))""",
    """CREATE TABLE IF NOT EXISTS knowledge_table_artifacts (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, source_id TEXT NOT NULL,
        extraction_id TEXT NOT NULL, schema_json TEXT NOT NULL DEFAULT '[]', row_count INTEGER NOT NULL,
        units_json TEXT NOT NULL DEFAULT '{}', content_hash TEXT NOT NULL, status TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
        UNIQUE(project_id,extraction_id,content_hash))""",
    """CREATE TABLE IF NOT EXISTS knowledge_reference_links (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, source_id TEXT NOT NULL,
        target_type TEXT NOT NULL, target_id TEXT NOT NULL, anchor_type TEXT NOT NULL,
        anchor TEXT NOT NULL DEFAULT '', relation TEXT NOT NULL, resolution_state TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
        UNIQUE(project_id,target_type,target_id,source_id,anchor_type,anchor,relation))""",
    """CREATE TABLE IF NOT EXISTS knowledge_information_source_registry (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, name TEXT NOT NULL,
        connector_type TEXT NOT NULL, feed_url TEXT NOT NULL, channel_id TEXT NOT NULL DEFAULT '',
        topics_json TEXT NOT NULL DEFAULT '[]', languages_json TEXT NOT NULL DEFAULT '[]',
        freshness_hours INTEGER NOT NULL, retention_days INTEGER NOT NULL,
        authority_tier TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
        availability TEXT NOT NULL, unavailable_reason TEXT NOT NULL DEFAULT '',
        metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        UNIQUE(project_id,connector_type,feed_url))""",
    """CREATE TABLE IF NOT EXISTS knowledge_signal_batches (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, batch_id TEXT NOT NULL,
        execution_id TEXT NOT NULL, schema_version TEXT NOT NULL, connector_type TEXT NOT NULL,
        workflow_id TEXT NOT NULL DEFAULT '', collected_at TEXT NOT NULL DEFAULT '',
        payload_hash TEXT NOT NULL, run_id TEXT NOT NULL, status TEXT NOT NULL,
        output_refs_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        UNIQUE(project_id,batch_id), UNIQUE(project_id,execution_id))""",
    """CREATE TABLE IF NOT EXISTS knowledge_signal_receipts (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, batch_id TEXT NOT NULL,
        item_key TEXT NOT NULL, registry_id TEXT NOT NULL, external_id TEXT NOT NULL DEFAULT '',
        canonical_url TEXT NOT NULL DEFAULT '', source_id TEXT NOT NULL DEFAULT '',
        disposition TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '', metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL, UNIQUE(project_id,batch_id,item_key))""",
    """CREATE TABLE IF NOT EXISTS knowledge_signal_derivatives (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, source_id TEXT NOT NULL,
        kind TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL DEFAULT '',
        revision TEXT NOT NULL DEFAULT '', input_hash TEXT NOT NULL, content_hash TEXT NOT NULL,
        content TEXT NOT NULL, metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
        UNIQUE(project_id,source_id,kind,provider,model,revision,input_hash,content_hash))""",
    """CREATE TABLE IF NOT EXISTS knowledge_release_evidence (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, evidence_id TEXT NOT NULL,
        revision INTEGER NOT NULL, state TEXT NOT NULL, proof_class TEXT NOT NULL,
        observed_at TEXT NOT NULL DEFAULT '', durable_ids_json TEXT NOT NULL DEFAULT '[]',
        detail_code TEXT NOT NULL DEFAULT '', recorded_by TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        UNIQUE(project_id,evidence_id,revision))""",
]


def ensure_schema(repo: Any) -> None:
    backend = repo._get_connection()
    dialect = getattr(backend, "dialect", "sqlite")
    if dialect == "postgresql" and getattr(backend, _POSTGRES_SCHEMA_READY_ATTRIBUTE, False):
        return
    postgres_lock_acquired = False
    try:
        if dialect == "postgresql":
            repo._execute("SELECT pg_advisory_lock(?)", (_POSTGRES_SCHEMA_ADVISORY_LOCK,))
            postgres_lock_acquired = True
        elif dialect == "sqlite":
            # Hold one write transaction for schema inspection and legacy-table
            # rebuilds. Individual migration helpers must not begin or commit
            # their own transaction inside this boundary.
            repo._execute("BEGIN IMMEDIATE")
        _ensure_schema_unlocked(repo, dialect)
        repo._commit()
        if dialect == "postgresql":
            setattr(backend, _POSTGRES_SCHEMA_READY_ATTRIBUTE, True)
    except Exception:
        backend.rollback()
        raise
    finally:
        if dialect == "postgresql" and postgres_lock_acquired:
            repo._execute("SELECT pg_advisory_unlock(?)", (_POSTGRES_SCHEMA_ADVISORY_LOCK,))
            repo._commit()


def _ensure_schema_unlocked(repo: Any, dialect: str) -> None:
    for sql in _COMMON_SCHEMA:
        repo._execute(sql)
    for sql in _WIKI_SCHEMA:
        repo._execute(sql)
    if dialect == "postgresql":
        repo._execute(
            """CREATE TABLE IF NOT EXISTS knowledge_benchmarks (
                id BIGSERIAL PRIMARY KEY, project_id TEXT,
                query TEXT NOT NULL, expected_chunk_ids TEXT DEFAULT '[]',
                notes TEXT, created_at TEXT NOT NULL)"""
        )
        repo._execute(
            """CREATE TABLE IF NOT EXISTS knowledge_fts (
                content TEXT, doc_id TEXT, chunk_id TEXT PRIMARY KEY)"""
        )
    else:
        repo._execute(
            """CREATE TABLE IF NOT EXISTS knowledge_benchmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT,
                query TEXT NOT NULL, expected_chunk_ids TEXT DEFAULT '[]',
                notes TEXT, created_at TEXT NOT NULL)"""
        )
        try:
            repo._execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5("
                "content, doc_id UNINDEXED, chunk_id UNINDEXED, tokenize='trigram')"
            )
        except Exception:
            pass

    _ensure_columns(
        repo,
        "knowledge_projects",
        ("ALTER TABLE knowledge_projects ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'default'",),
    )
    repo._execute(
        "UPDATE knowledge_projects SET tenant_id='default' "
        "WHERE tenant_id IS NULL OR tenant_id=''"
    )
    _ensure_columns(
        repo,
        "knowledge_docs",
        (
            "ALTER TABLE knowledge_docs ADD COLUMN doc_format TEXT",
            "ALTER TABLE knowledge_docs ADD COLUMN content_hash TEXT",
            "ALTER TABLE knowledge_docs ADD COLUMN version INTEGER DEFAULT 1",
            "ALTER TABLE knowledge_docs ADD COLUMN domain TEXT DEFAULT 'general'",
            "ALTER TABLE knowledge_docs ADD COLUMN access_level TEXT DEFAULT 'public'",
        ),
    )
    _ensure_columns(
        repo,
        "knowledge_chunks",
        ("ALTER TABLE knowledge_chunks ADD COLUMN access_level TEXT DEFAULT 'public'",),
    )
    _ensure_columns(
        repo,
        "knowledge_sources",
        ("ALTER TABLE knowledge_sources ADD COLUMN raw_content TEXT NOT NULL DEFAULT ''",),
    )
    _ensure_columns(
        repo,
        "knowledge_failure_records",
        (
            "ALTER TABLE knowledge_failure_records ADD COLUMN diagnostic_pattern TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE knowledge_failure_records ADD COLUMN secondary_diagnostic_patterns_json TEXT NOT NULL DEFAULT '[]'",
            "ALTER TABLE knowledge_failure_records ADD COLUMN minimal_structural_fix TEXT NOT NULL DEFAULT ''",
        ),
    )
    _ensure_columns(
        repo,
        "knowledge_method_proposals",
        ("ALTER TABLE knowledge_method_proposals ADD COLUMN package_audit_json TEXT NOT NULL DEFAULT '{}'",),
    )
    _backfill_failure_patterns(repo)
    _ensure_columns(
        repo,
        "knowledge_source_triage",
        (
            "ALTER TABLE knowledge_source_triage ADD COLUMN evaluator_revision TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE knowledge_source_triage ADD COLUMN evaluator_status TEXT NOT NULL DEFAULT 'completed'",
        ),
    )
    _ensure_triage_evaluator_identity(repo)
    for idx_sql in (
        "CREATE INDEX IF NOT EXISTS idx_kprojects_tenant_created ON knowledge_projects(tenant_id,created_at)",
        "CREATE INDEX IF NOT EXISTS idx_pm_project_user ON project_members(project_id, user_id)",
        "CREATE INDEX IF NOT EXISTS idx_kdocs_project ON knowledge_docs(project_id)",
        "CREATE INDEX IF NOT EXISTS idx_kdocs_domain ON knowledge_docs(domain)",
        "CREATE INDEX IF NOT EXISTS idx_kdocs_access ON knowledge_docs(access_level)",
        "CREATE INDEX IF NOT EXISTS idx_chunks_doc ON knowledge_chunks(doc_id)",
        "CREATE INDEX IF NOT EXISTS idx_chunks_access ON knowledge_chunks(access_level)",
        "CREATE INDEX IF NOT EXISTS idx_kw_sources_project_status ON knowledge_sources(project_id,status,captured_at)",
        "CREATE INDEX IF NOT EXISTS idx_kw_sources_project_hash ON knowledge_sources(project_id,content_hash)",
        "CREATE INDEX IF NOT EXISTS idx_kw_capture_attempts_project_created ON knowledge_source_capture_attempts(project_id,created_at)",
        "CREATE INDEX IF NOT EXISTS idx_kw_capture_attempts_project_run ON knowledge_source_capture_attempts(project_id,run_id,created_at)",
        "CREATE INDEX IF NOT EXISTS idx_kw_capture_attempts_project_source ON knowledge_source_capture_attempts(project_id,source_id,created_at)",
        "CREATE INDEX IF NOT EXISTS idx_kw_horizon_claims_project_status ON knowledge_horizon_import_claims(project_id,status,lease_expires_at)",
        "CREATE INDEX IF NOT EXISTS idx_kw_horizon_claims_capture_run ON knowledge_horizon_import_claims(project_id,capture_run_id,updated_at)",
        "CREATE INDEX IF NOT EXISTS idx_kw_pages_project_path ON knowledge_wiki_pages(project_id,path)",
        "CREATE INDEX IF NOT EXISTS idx_kw_page_revisions_page_version ON knowledge_wiki_page_revisions(wiki_page_id,version)",
        "CREATE INDEX IF NOT EXISTS idx_kw_proposals_project_status ON knowledge_proposals(project_id,status,created_at)",
        "CREATE INDEX IF NOT EXISTS idx_kw_runs_project_created ON knowledge_runs(project_id,created_at)",
        "CREATE INDEX IF NOT EXISTS idx_kw_run_events_project_run_sequence ON knowledge_run_events(project_id,run_id,sequence)",
        "CREATE INDEX IF NOT EXISTS idx_kw_schedules_project_job ON knowledge_schedules(project_id,job_type)",
        "CREATE INDEX IF NOT EXISTS idx_kw_graph_project_type ON knowledge_graph_edges(project_id,edge_type)",
        "CREATE INDEX IF NOT EXISTS idx_kw_eval_cases_project ON knowledge_eval_cases(project_id,case_type)",
        "CREATE INDEX IF NOT EXISTS idx_kw_profiles_revision ON knowledge_project_profiles(project_id,revision)",
        "CREATE INDEX IF NOT EXISTS idx_kw_triage_project_score ON knowledge_source_triage(project_id,priority,created_at)",
        "CREATE INDEX IF NOT EXISTS idx_kw_candidates_project_status ON knowledge_candidates(project_id,status,created_at)",
        "CREATE INDEX IF NOT EXISTS idx_kw_candidates_project_source ON knowledge_candidates(project_id,source_id,created_at)",
        "CREATE INDEX IF NOT EXISTS idx_kw_candidates_project_run ON knowledge_candidates(project_id,extraction_run_id,created_at)",
        "CREATE INDEX IF NOT EXISTS idx_kw_methods_project_status ON knowledge_methods(project_id,status)",
        "CREATE INDEX IF NOT EXISTS idx_kw_method_revisions_project ON knowledge_method_revisions(project_id,method_id,version)",
        "CREATE INDEX IF NOT EXISTS idx_kw_method_proposals_project ON knowledge_method_proposals(project_id,status,created_at)",
        "CREATE INDEX IF NOT EXISTS idx_kw_method_evolution_project ON knowledge_method_evolution_runs(project_id,method_id,created_at)",
        "CREATE INDEX IF NOT EXISTS idx_kw_method_evolution_proposal ON knowledge_method_evolution_runs(project_id,candidate_proposal_id)",
        "CREATE INDEX IF NOT EXISTS idx_kw_outputs_project_status ON knowledge_outputs(project_id,status,created_at)",
        "CREATE INDEX IF NOT EXISTS idx_kw_output_hash ON knowledge_outputs(project_id,content_hash)",
        "CREATE INDEX IF NOT EXISTS idx_kw_evaluations_output ON knowledge_output_evaluations(project_id,output_id,created_at)",
        "CREATE INDEX IF NOT EXISTS idx_kw_feedback_output ON knowledge_output_feedback(project_id,output_id,created_at)",
        "CREATE INDEX IF NOT EXISTS idx_kw_growth_distillations_project ON knowledge_growth_distillations(project_id,kind,period)",
        "CREATE INDEX IF NOT EXISTS idx_kw_failures_project_status ON knowledge_failure_records(project_id,status,created_at)",
        "CREATE INDEX IF NOT EXISTS idx_kw_failures_project_run ON knowledge_failure_records(project_id,run_id,event_sequence)",
        "CREATE INDEX IF NOT EXISTS idx_kw_failures_project_pattern ON knowledge_failure_records(project_id,diagnostic_pattern,created_at)",
        "CREATE INDEX IF NOT EXISTS idx_kw_lineage_edge ON knowledge_graph_edges(project_id,from_id,to_id,edge_type)",
        "CREATE INDEX IF NOT EXISTS idx_kw_media_project_source ON knowledge_media_assets(project_id,source_id,created_at)",
        "CREATE INDEX IF NOT EXISTS idx_kw_media_project_hash ON knowledge_media_assets(project_id,byte_hash)",
        "CREATE INDEX IF NOT EXISTS idx_kw_extract_project_source ON knowledge_extraction_artifacts(project_id,source_id,created_at)",
        "CREATE INDEX IF NOT EXISTS idx_kw_extract_project_asset ON knowledge_extraction_artifacts(project_id,asset_id,created_at)",
        "CREATE INDEX IF NOT EXISTS idx_kw_tables_project_extract ON knowledge_table_artifacts(project_id,extraction_id,created_at)",
        "CREATE INDEX IF NOT EXISTS idx_kw_references_project_source ON knowledge_reference_links(project_id,source_id,created_at)",
        "CREATE INDEX IF NOT EXISTS idx_kw_references_project_target ON knowledge_reference_links(project_id,target_type,target_id)",
        "CREATE INDEX IF NOT EXISTS idx_kw_intelligence_registry_project ON knowledge_information_source_registry(project_id,enabled,availability)",
        "CREATE INDEX IF NOT EXISTS idx_kw_signal_batches_project_created ON knowledge_signal_batches(project_id,created_at)",
        "CREATE INDEX IF NOT EXISTS idx_kw_signal_batches_project_run ON knowledge_signal_batches(project_id,run_id)",
        "CREATE INDEX IF NOT EXISTS idx_kw_signal_receipts_project_created ON knowledge_signal_receipts(project_id,created_at)",
        "CREATE INDEX IF NOT EXISTS idx_kw_signal_receipts_project_source ON knowledge_signal_receipts(project_id,source_id)",
        "CREATE INDEX IF NOT EXISTS idx_kw_signal_derivatives_project_source ON knowledge_signal_derivatives(project_id,source_id,created_at)",
        "CREATE INDEX IF NOT EXISTS idx_kw_release_evidence_project_current ON knowledge_release_evidence(project_id,evidence_id,revision)",
    ):
        repo._execute(idx_sql)


def _backfill_failure_patterns(repo: Any) -> None:
    """Give legacy diagnostic records the same stable P01-P12 primary pattern."""
    for code, pattern in FAILURE_PATTERN_BY_CODE.items():
        repo._execute(
            "UPDATE knowledge_failure_records SET diagnostic_pattern=? "
            "WHERE code=? AND (diagnostic_pattern IS NULL OR diagnostic_pattern='')",
            (pattern.value, code.value),
        )


def _ensure_columns(repo: Any, table: str, statements: tuple[str, ...]) -> None:
    backend = repo._get_connection()
    dialect = getattr(backend, "dialect", "sqlite")
    if dialect == "postgresql":
        rows = repo._execute(
            """SELECT column_name FROM information_schema.columns
               WHERE table_schema = current_schema() AND table_name = ?""",
            (table,),
        ).fetchall()
        existing = {row["column_name"] for row in rows}
    else:
        rows = repo._execute(f"PRAGMA table_info({table})").fetchall()
        existing = {row[1] for row in rows}
    for statement in statements:
        column = statement.split(" ADD COLUMN ", 1)[1].split(" ", 1)[0]
        if column not in existing:
            repo._execute(statement)


def _ensure_triage_evaluator_identity(repo: Any) -> None:
    """Keep old triage rows while allowing a new scoring policy to re-evaluate."""
    backend = repo._get_connection()
    dialect = getattr(backend, "dialect", "sqlite")
    expected = ("project_id", "source_id", "profile_revision", "evaluator_revision")
    if dialect == "postgresql":
        rows = repo._execute(
            "SELECT conname, pg_get_constraintdef(oid) AS definition "
            "FROM pg_constraint "
            "WHERE conrelid = 'knowledge_source_triage'::regclass AND contype = 'u'"
        ).fetchall()
        existing = [
            (str(row["conname"]), str(row["definition"]).replace(" ", "").lower())
            for row in rows
        ]
        if any(definition == "unique(project_id,source_id,profile_revision,evaluator_revision)" for _, definition in existing):
            return
        for name, definition in existing:
            if definition == "unique(project_id,source_id,profile_revision)":
                repo._execute(
                    'ALTER TABLE knowledge_source_triage DROP CONSTRAINT "'
                    + name.replace('"', '""')
                    + '"'
                )
        repo._execute(
            "ALTER TABLE knowledge_source_triage "
            "ADD CONSTRAINT knowledge_source_triage_project_source_profile_evaluator_key "
            "UNIQUE(project_id,source_id,profile_revision,evaluator_revision)"
        )
        return

    index_rows = repo._execute("PRAGMA index_list(knowledge_source_triage)").fetchall()
    for index in index_rows:
        if not int(index[2]):
            continue
        name = str(index[1])
        columns = tuple(str(column[2]) for column in repo._execute(f"PRAGMA index_info({name})").fetchall())
        if columns == expected:
            return
    repo._execute("ALTER TABLE knowledge_source_triage RENAME TO knowledge_source_triage_legacy_identity")
    repo._execute(
        """CREATE TABLE knowledge_source_triage (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL, source_id TEXT NOT NULL,
            profile_revision INTEGER NOT NULL, relevance INTEGER NOT NULL,
            value_score INTEGER NOT NULL, freshness INTEGER NOT NULL,
            outputability INTEGER NOT NULL, connectedness INTEGER NOT NULL,
            priority INTEGER NOT NULL, reliability_pass INTEGER NOT NULL,
            disposition TEXT NOT NULL, reasons_json TEXT NOT NULL DEFAULT '[]',
            evaluator_revision TEXT NOT NULL DEFAULT '', evaluator_status TEXT NOT NULL DEFAULT 'completed',
            created_at TEXT NOT NULL,
            UNIQUE(project_id, source_id, profile_revision, evaluator_revision))"""
    )
    repo._execute(
        "INSERT INTO knowledge_source_triage "
        "(id,project_id,source_id,profile_revision,relevance,value_score,freshness,outputability,connectedness,priority,reliability_pass,disposition,reasons_json,evaluator_revision,evaluator_status,created_at) "
        "SELECT id,project_id,source_id,profile_revision,relevance,value_score,freshness,outputability,connectedness,priority,reliability_pass,disposition,reasons_json,evaluator_revision,evaluator_status,created_at "
        "FROM knowledge_source_triage_legacy_identity"
    )
    repo._execute("DROP TABLE knowledge_source_triage_legacy_identity")
