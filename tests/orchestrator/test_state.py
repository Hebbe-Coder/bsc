# tests/orchestrator/test_state.py
import pytest
from app.agent.state import ProjectDraftRepository, ProjectDraft, SEGMENTS


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
    assert got.status == "edited:project"


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
