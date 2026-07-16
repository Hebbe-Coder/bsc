from app.agent.state import ProjectDraftRepository, ProjectDraft, SEGMENTS


def test_risk_in_segments():
    assert "risk" in SEGMENTS


def test_risk_roundtrip():
    repo = ProjectDraftRepository()
    sid = "sess-risk"
    repo.save(ProjectDraft(session_id=sid, idea="x",
                            risk={"overall_score": "low", "gate": {"decision": "pass"}}))
    got = repo.get(sid)
    assert got.risk["overall_score"] == "low"
    assert got.risk["gate"]["decision"] == "pass"
