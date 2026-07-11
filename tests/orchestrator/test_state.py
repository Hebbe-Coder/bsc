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
