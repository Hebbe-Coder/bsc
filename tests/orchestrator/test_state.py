# tests/orchestrator/test_state.py
import pytest
from app.agent.state import ProjectDraftRepository, ProjectDraft, SEGMENTS
from app.orchestrator.contracts import EventType, JobStatus, OrchestratorEvent


def test_create_and_get_six_segments():
    repo = ProjectDraftRepository()
    sid = "sess-6seg"
    d = ProjectDraft(session_id=sid, idea="内容审核中心")
    repo.save(d)
    got = repo.get(sid)
    assert got is not None
    assert got.idea == "内容审核中心"
    for seg in SEGMENTS:
        assert isinstance(getattr(got, seg), (dict, list))


def test_patch_segment():
    repo = ProjectDraftRepository()
    sid = "sess-patch"
    repo.save(ProjectDraft(session_id=sid, idea="x"))
    repo.patch(sid, "project", {"name": "审核中心"})
    got = repo.get(sid)
    assert got.project == {"name": "审核中心"}
    assert got.status == "queued"


def test_patch_unknown_segment_raises():
    repo = ProjectDraftRepository()
    sid = "sess-bad"
    repo.save(ProjectDraft(session_id=sid, idea="x"))
    with pytest.raises(ValueError):
        repo.patch(sid, "nope", {})


def test_requirements_stays_list_on_roundtrip():
    repo = ProjectDraftRepository()
    sid = "sess-req-list"
    repo.save(ProjectDraft(session_id=sid, idea="y", requirements=[{"id": "r1", "text": "登录"}]))
    got = repo.get(sid)
    assert isinstance(got.requirements, list)
    assert got.requirements[0]["id"] == "r1"


def test_empty_requirements_roundtrip_stays_list():
    repo = ProjectDraftRepository()
    sid = "sess-req-empty"
    repo.save(ProjectDraft(session_id=sid, idea="z", requirements=[]))
    got = repo.get(sid)
    assert isinstance(got.requirements, list)
    assert got.requirements == []


def test_get_unknown_returns_none():
    repo = ProjectDraftRepository()
    assert repo.get("does-not-exist") is None


def test_multiple_repo_instances_preserve_data():
    repo1 = ProjectDraftRepository()
    repo1.save(ProjectDraft(session_id="shared", idea="keepme"))
    repo2 = ProjectDraftRepository()  # constructing a 2nd repo MUST NOT wipe data
    assert repo2.get("shared") is not None
    assert repo2.get("shared").idea == "keepme"


def test_transition_updates_existing_status(draft_repo):
    draft = ProjectDraft(session_id="life-1", idea="x", status="queued")
    draft_repo.save(draft)

    updated = draft_repo.transition("life-1", JobStatus.RUNNING)

    assert updated.status == "running"
    assert draft_repo.get("life-1").status == "running"


def test_terminal_status_cannot_transition(draft_repo):
    draft = ProjectDraft(session_id="life-2", idea="x", status="completed")
    draft_repo.save(draft)

    with pytest.raises(ValueError, match="terminal"):
        draft_repo.transition("life-2", JobStatus.RUNNING)


def test_terminal_projection_cannot_be_overwritten_or_patched(draft_repo):
    draft_repo.save(ProjectDraft(
        session_id="life-frozen",
        idea="x",
        status="completed",
        business_model={"version": 1},
    ))

    with pytest.raises(ValueError, match="terminal"):
        draft_repo.save(ProjectDraft(
            session_id="life-frozen",
            idea="x",
            status="completed",
            business_model={"version": 2},
        ))
    with pytest.raises(ValueError, match="terminal"):
        draft_repo.patch("life-frozen", "business_model", {"version": 2})


def test_save_replays_identical_terminal_projection_idempotently(draft_repo):
    draft = ProjectDraft(
        session_id="life-idempotent",
        idea="x",
        status="completed",
        business_model={"version": 1},
    )
    draft_repo.save(draft)
    replay = ProjectDraft(
        session_id="life-idempotent",
        idea="x",
        status="completed",
        business_model={"version": 1},
    )

    draft_repo.save(replay)

    assert draft_repo.get("life-idempotent").business_model == {"version": 1}


def test_save_cannot_overwrite_terminal_status(draft_repo):
    draft_repo.save(ProjectDraft(
        session_id="life-3",
        idea="x",
        status="completed",
    ))

    with pytest.raises(ValueError, match="terminal"):
        draft_repo.save(ProjectDraft(
            session_id="life-3",
            idea="x",
            status="running",
        ))


def test_transition_unknown_session_raises(draft_repo):
    with pytest.raises(KeyError, match="missing"):
        draft_repo.transition("missing", JobStatus.FAILED)


def test_schema_migration_adds_columns_without_losing_existing_draft(tmp_path):
    import sqlite3

    connection = sqlite3.connect(str(tmp_path / "legacy-drafts.db"))
    connection.row_factory = sqlite3.Row
    connection.execute(
        """CREATE TABLE agent_project_drafts (
            session_id TEXT PRIMARY KEY,
            idea TEXT,
            legacy_note TEXT
        )"""
    )
    connection.execute(
        "INSERT INTO agent_project_drafts (session_id, idea, legacy_note) VALUES (?, ?, ?)",
        ("legacy-1", "preserve this draft", "do not drop"),
    )
    connection.commit()

    repo = ProjectDraftRepository(connection=connection)

    draft = repo.get("legacy-1")
    columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(agent_project_drafts)").fetchall()
    }
    note = connection.execute(
        "SELECT legacy_note FROM agent_project_drafts WHERE session_id=?",
        ("legacy-1",),
    ).fetchone()[0]
    connection.close()

    assert draft is not None
    assert draft.idea == "preserve this draft"
    assert draft.status == "queued"
    assert draft.completed_at is None
    assert set(SEGMENTS).issubset(columns)
    assert {
        "status",
        "current_stage",
        "error_code",
        "error_message",
        "event_seq",
        "created_at",
        "completed_at",
    }.issubset(columns)
    assert note == "do not drop"


def test_schema_migration_rejects_tables_without_session_primary_key(tmp_path):
    import sqlite3

    connection = sqlite3.connect(str(tmp_path / "unsafe-drafts.db"))
    connection.execute("CREATE TABLE agent_project_drafts (idea TEXT)")
    connection.execute("INSERT INTO agent_project_drafts (idea) VALUES ('keep me')")
    connection.commit()

    with pytest.raises(RuntimeError, match="session_id primary key"):
        ProjectDraftRepository(connection=connection)

    row = connection.execute("SELECT idea FROM agent_project_drafts").fetchone()
    connection.close()

    assert row[0] == "keep me"


def test_task_projection_tracks_event_and_terminal_metadata(draft_repo):
    draft_repo.save(ProjectDraft(
        session_id="projection-1",
        idea="x",
        status=JobStatus.RUNNING.value,
    ))
    draft_repo.record_event(OrchestratorEvent(
        session_id="projection-1",
        seq=3,
        type=EventType.STAGE_STARTED,
        stage="architect",
        status="running",
    ))
    draft_repo.transition("projection-1", JobStatus.FAILED,
                          error_code="pipeline_failed",
                          error_message="Pipeline failed")

    draft = draft_repo.get("projection-1")

    assert draft.current_stage == "architect"
    assert draft.event_seq == 3
    assert draft.error_code == "pipeline_failed"
    assert draft.error_message == "Pipeline failed"
    assert draft.created_at
    assert draft.completed_at


def test_terminal_event_preserves_the_last_non_terminal_stage(draft_repo):
    draft_repo.save(ProjectDraft(
        session_id="terminal-event-stage",
        idea="x",
        status=JobStatus.RUNNING.value,
        current_stage="architect",
    ))

    draft_repo.record_event(OrchestratorEvent(
        session_id="terminal-event-stage",
        seq=2,
        type=EventType.PIPELINE_FAILED,
        stage="pipeline",
        status=JobStatus.FAILED.value,
        terminal=True,
    ))

    draft = draft_repo.get("terminal-event-stage")

    assert draft.current_stage == "architect"
    assert draft.event_seq == 2
