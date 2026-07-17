# tests/evolution/test_feedback_bridge.py
"""编译器反馈桥单元测试（方案 C Phase 2）。"""
from app.evolution import CompilerFeedbackBridge


def _state(idea: str = "做一个咖啡馆", sops=None):
    return {
        "idea": idea,
        "sop": {"sops": sops or [{"id": "s1", "title": "开店流程"}]},
    }


def test_high_score_maps_to_thumbs_up():
    bridge = CompilerFeedbackBridge()
    ev = {"overall_score": 92, "is_passed": True, "suggestions": [], "improvement_points": 0}
    rec = bridge.record(ev, _state(), "sess-1")
    assert rec.feedback_type == "thumbs_up"
    assert rec.user_id == "compiler_evaluator"
    assert rec.trace_id == "sess-1"
    assert rec.query == "做一个咖啡馆"
    assert "SOP" in rec.answer


def test_medium_score_maps_to_comment_with_suggestions():
    bridge = CompilerFeedbackBridge()
    ev = {
        "overall_score": 70,
        "is_passed": True,
        "suggestions": ["方法论采用度不足：覆盖率低", "结构完整度不足：缺失段"],
        "improvement_points": 2,
    }
    rec = bridge.record(ev, _state(), "sess-2")
    assert rec.feedback_type == "comment"
    assert rec.comment is not None
    assert "方法论采用度不足" in rec.comment


def test_low_score_maps_to_thumbs_down_with_default_message():
    bridge = CompilerFeedbackBridge()
    ev = {"overall_score": 40, "is_passed": False, "suggestions": [], "improvement_points": 4}
    rec = bridge.record(ev, _state(), "sess-3")
    assert rec.feedback_type == "thumbs_down"
    assert rec.comment is not None
    assert "40" in rec.comment
    assert "不合格" in rec.comment


def test_recent_returns_dicts_in_descending_order():
    bridge = CompilerFeedbackBridge()
    for i, score in enumerate([90, 70, 50]):
        bridge.record({"overall_score": score, "is_passed": score >= 60, "suggestions": [], "improvement_points": 0}, _state(), f"sess-{i}")
    recent = bridge.recent(limit=10)
    assert len(recent) == 3
    assert recent[0]["trace_id"] == "sess-2"  # latest first


def test_stats_counts_by_type():
    bridge = CompilerFeedbackBridge()
    for i, score in enumerate([90, 85, 75, 50]):
        bridge.record({"overall_score": score, "is_passed": score >= 60, "suggestions": [], "improvement_points": 0}, _state(), f"sess-{i}")
    stats = bridge.stats()
    assert stats["total"] == 4
    assert stats["by_type"]["thumbs_up"] == 2
    assert stats["by_type"]["comment"] == 1
    assert stats["by_type"]["thumbs_down"] == 1
    assert abs(stats["positive_rate"] - 0.5) < 0.001


def test_falls_back_to_session_id_when_no_idea():
    bridge = CompilerFeedbackBridge()
    ev = {"overall_score": 90, "is_passed": True, "suggestions": [], "improvement_points": 0}
    rec = bridge.record(ev, {"sop": {}}, "fallback-sid")
    assert rec.query == "fallback-sid"


def test_truncate_answer_for_long_sop():
    bridge = CompilerFeedbackBridge()
    long_titles = [{"id": f"s{i}", "title": f"步骤{i}" * 20} for i in range(20)]
    ev = {"overall_score": 90, "is_passed": True, "suggestions": [], "improvement_points": 0}
    rec = bridge.record(ev, _state(sops=long_titles), "sess-long")
    assert len(rec.answer) <= 400
