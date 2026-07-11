import pytest
from app.agent.state import ProjectDraftRepository, ProjectDraft


def test_create_and_get():
    repo = ProjectDraftRepository()
    sid = "sess-001"
    d = ProjectDraft(session_id=sid, idea="社区老人上门助浴")
    repo.save(d)
    got = repo.get(sid)
    assert got is not None
    assert got.session_id == sid
    assert got.idea == "社区老人上门助浴"
    assert got.status == "idea"


def test_patch_node():
    repo = ProjectDraftRepository()
    sid = "sess-002"
    repo.save(ProjectDraft(session_id=sid, idea="x"))
    repo.patch(sid, "business_system.roles", [{"role": "助浴师", "responsibilities": ["安全"]}])
    got = repo.get(sid)
    assert got.business_system["roles"][0]["role"] == "助浴师"
