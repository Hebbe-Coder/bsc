"""用户反馈闭环：记录用户对 RAG 答案的反馈，用于后续优化。

生产级 RAG 的核心组件：
- 收集用户反馈：点赞/点踩/修正/评论
- 分析反馈数据：识别低质量答案、常见问题
- 自动触发优化：更新索引、调整检索策略、优化prompt
- 反馈统计报告：跟踪改进效果
"""
from __future__ import annotations
import logging
import time
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

FEEDBACK_TYPES = {
    "thumbs_up": {"name": "点赞", "description": "答案有用"},
    "thumbs_down": {"name": "点踩", "description": "答案无用或不准确"},
    "correction": {"name": "修正", "description": "提供正确答案"},
    "comment": {"name": "评论", "description": "附加评论"},
}


class FeedbackRecord:
    def __init__(self, trace_id: str, user_id: str, feedback_type: str,
                 query: str, answer: str, correction: Optional[str] = None,
                 comment: Optional[str] = None):
        self.trace_id = trace_id
        self.user_id = user_id
        self.feedback_type = feedback_type
        self.query = query
        self.answer = answer
        self.correction = correction
        self.comment = comment
        self.timestamp = time.time()
        self.processed = False


class FeedbackStore:
    def __init__(self):
        self._records: List[FeedbackRecord] = []

    def add_feedback(self, trace_id: str, user_id: str, feedback_type: str,
                     query: str, answer: str, correction: Optional[str] = None,
                     comment: Optional[str] = None):
        record = FeedbackRecord(trace_id, user_id, feedback_type, query, answer,
                               correction, comment)
        self._records.append(record)
        logger.info("反馈记录: trace_id=%s, user_id=%s, type=%s", trace_id, user_id, feedback_type)
        return record

    def get_recent(self, limit: int = 100) -> List[FeedbackRecord]:
        return sorted(self._records, key=lambda r: r.timestamp, reverse=True)[:limit]

    def get_by_trace_id(self, trace_id: str) -> List[FeedbackRecord]:
        return [r for r in self._records if r.trace_id == trace_id]

    def get_by_user_id(self, user_id: str) -> List[FeedbackRecord]:
        return [r for r in self._records if r.user_id == user_id]

    def get_negative_feedback(self, limit: int = 50) -> List[FeedbackRecord]:
        return sorted(
            [r for r in self._records if r.feedback_type == "thumbs_down" or r.feedback_type == "correction"],
            key=lambda r: r.timestamp, reverse=True)[:limit]

    def get_stats(self) -> Dict:
        total = len(self._records)
        if total == 0:
            return {"total": 0}

        by_type = {}
        for ft in FEEDBACK_TYPES:
            by_type[ft] = sum(1 for r in self._records if r.feedback_type == ft)

        by_user = {}
        for r in self._records:
            by_user[r.user_id] = by_user.get(r.user_id, 0) + 1

        return {
            "total": total,
            "by_type": by_type,
            "by_user": by_user,
            "positive_rate": (by_type.get("thumbs_up", 0) / total) if total > 0 else 0.0,
        }


class MockFeedbackStore(FeedbackStore):
    def __init__(self):
        super().__init__()
        self._records = [
            FeedbackRecord("trace-001", "user-001", "thumbs_up", "内容安全违规有哪些类型？", "答案1"),
            FeedbackRecord("trace-002", "user-002", "thumbs_down", "咖啡烘焙有哪些阶段？", "答案2"),
            FeedbackRecord("trace-003", "user-003", "correction", "如何防止教师流失？", "答案3", "正确答案：完善培训体系"),
            FeedbackRecord("trace-004", "user-001", "thumbs_up", "违规处罚有哪些等级？", "答案4"),
            FeedbackRecord("trace-005", "user-004", "comment", "咖啡烘焙温度控制？", "答案5", comment="信息不够详细"),
        ]


class FeedbackAnalyzer:
    def __init__(self, store: FeedbackStore):
        self.store = store

    def analyze_problematic_queries(self, top_n: int = 10) -> List[Dict]:
        negative = self.store.get_negative_feedback()
        if not negative:
            return []

        query_stats = {}
        for record in negative:
            if record.query not in query_stats:
                query_stats[record.query] = {"count": 0, "corrections": [], "comments": []}
            query_stats[record.query]["count"] += 1
            if record.correction:
                query_stats[record.query]["corrections"].append(record.correction)
            if record.comment:
                query_stats[record.query]["comments"].append(record.comment)

        sorted_queries = sorted(query_stats.items(), key=lambda x: x[1]["count"], reverse=True)[:top_n]

        return [
            {
                "query": q,
                "negative_count": stats["count"],
                "corrections": stats["corrections"],
                "comments": stats["comments"],
            }
            for q, stats in sorted_queries
        ]

    def suggest_improvements(self) -> List[Dict]:
        problematic = self.analyze_problematic_queries(top_n=5)
        improvements = []

        for item in problematic:
            improvements.append({
                "query": item["query"],
                "issue": "频繁收到负面反馈",
                "suggestion": f"优化查询改写策略，增加更多同义词扩展，或补充相关文档",
                "negative_count": item["negative_count"],
                "corrections": item["corrections"][:3],
            })

        return improvements


def get_feedback_store(mock: bool = True) -> FeedbackStore:
    if mock:
        return MockFeedbackStore()
    return FeedbackStore()


def get_feedback_analyzer(mock: bool = True) -> FeedbackAnalyzer:
    store = get_feedback_store(mock=mock)
    return FeedbackAnalyzer(store)
