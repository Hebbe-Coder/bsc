# app/evolution/feedback_bridge.py
"""
方案 C Phase 2：把编译器评测结果接进现有 FeedbackStore 自进化闭环。

复用 app.knowledge.feedback.FeedbackStore（in-memory）+ FeedbackAnalyzer：
- 评测高分（overall >= 80） → thumbs_up（高质量产物）
- 评测中等（60 <= overall < 80） → comment（带改进建议）
- 评测低分（overall < 60） → thumbs_down（质量警告 + 改进点）

数据落进 FeedbackStore 后可被 FeedbackAnalyzer.analyze_problematic_queries 识别
"问题产物"并给出改进建议，构成"越用越聪明"的闭环。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.knowledge.feedback import FeedbackRecord, FeedbackStore

_SCORE_HIGH = 80
_SCORE_LOW = 60
_ANSWER_MAX_CHARS = 400


def _truncate_answer(state: dict) -> str:
    """取 state 的 SOP 标题摘要作为反馈 answer。"""
    sop = state.get("sop") or {}
    sops = sop.get("sops") or []
    if not sops:
        return ""
    titles = [str(s.get("title") or s.get("id") or "") for s in sops[:5]]
    return "SOP: " + " · ".join(t for t in titles if t)


def _map_score_to_feedback(overall: int) -> str:
    if overall >= _SCORE_HIGH:
        return "thumbs_up"
    if overall >= _SCORE_LOW:
        return "comment"
    return "thumbs_down"


class CompilerFeedbackBridge:
    """把编译器评测结果（QualityReport dict）写入 FeedbackStore。"""

    def __init__(self, store: Optional[FeedbackStore] = None):
        self.store = store or FeedbackStore()

    def record(self, evaluation: dict, state: dict, session_id: str) -> FeedbackRecord:
        # Dashboard reads can happen repeatedly as a browser reconnects. A
        # compiler evaluation is one immutable observation per completed run,
        # so a repeated read must not amplify it into synthetic feedback.
        for existing in self.store.get_by_trace_id(session_id):
            if existing.user_id == "compiler_evaluator":
                return existing

        evaluation = evaluation or {}
        overall = int(evaluation.get("overall_score") or 0)
        passed = bool(evaluation.get("is_passed"))
        suggestions = list(evaluation.get("suggestions") or [])
        fb_type = _map_score_to_feedback(overall)
        if fb_type == "thumbs_down" and not suggestions:
            comment_text = f"评分 {overall}（不合格），改进点 {evaluation.get('improvement_points', 0)}"
        elif passed and not suggestions:
            comment_text = f"评分 {overall}（合格）"
        else:
            comment_text = "\n".join(suggestions) if suggestions else None
        query = (
            (state.get("idea") or "").strip()
            or (state.get("project") or {}).get("name")
            or session_id
        )
        answer = _truncate_answer(state)[:_ANSWER_MAX_CHARS] or f"evaluation_score={overall}"
        return self.store.add_feedback(
            trace_id=session_id,
            user_id="compiler_evaluator",
            feedback_type=fb_type,
            query=query,
            answer=answer,
            comment=comment_text,
        )

    def recent(self, limit: int = 5) -> List[Dict[str, Any]]:
        records = self.store.get_recent(limit=limit)
        return [
            {
                "trace_id": r.trace_id,
                "user_id": r.user_id,
                "feedback_type": r.feedback_type,
                "query": r.query,
                "answer": r.answer,
                "comment": r.comment,
                "timestamp": r.timestamp,
                "processed": r.processed,
            }
            for r in records
        ]

    def stats(self) -> Dict[str, Any]:
        return self.store.get_stats()


_default_bridge: Optional[CompilerFeedbackBridge] = None


def get_default_bridge() -> CompilerFeedbackBridge:
    global _default_bridge
    if _default_bridge is None:
        _default_bridge = CompilerFeedbackBridge()
    return _default_bridge
