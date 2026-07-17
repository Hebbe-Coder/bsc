"""方法论检索桥接：为后续编译器 Agent 提供可注入、可单测的知识检索入口。

本模块不与数据库/向量库直接耦合，而是通过依赖注入的 KnowledgeService 取回
方法论文献分块，并将结果转换为「带溯源信息的引用列表 + 可读上下文块」，
二者形状与 app.knowledge.answer.build_context 保持一致，便于后续审计步骤统一消费。
"""
from __future__ import annotations

from typing import List, Optional


def derive_methodology_query(business_model: dict) -> str:
    """根据业务模型启发式构造检索查询字符串。

    提取领域/标题/行业字符串，并拼接前几个流程/工作流名称。
    始终返回非空字符串，保证检索不会拿到空查询（兜底为 name 或固定文案）。
    """
    business_model = business_model or {}
    parts: List[str] = []

    domain = (
        business_model.get("name")
        or business_model.get("title")
        or business_model.get("domain")
        or business_model.get("industry")
    )
    if domain:
        parts.append(str(domain))

    # 流程 / 工作流名称优先取 flows，其次 processes
    flows = business_model.get("flows") or business_model.get("processes") or []
    if isinstance(flows, list):
        for f in flows[:3]:
            name = f.get("name") if isinstance(f, dict) else f
            if name:
                parts.append(str(name))

    query = " ".join(parts).strip()
    return query or (business_model.get("name") or "business methodology")


class MethodologyBridge:
    """桥接方法论知识库与编译器 Agent。"""

    def __init__(self, service=None):
        # 可注入的检索服务；None 时惰性构建默认 KnowledgeService()
        self._service = service

    def _get_service(self):
        if self._service is None:
            from app.knowledge.service import KnowledgeService
            self._service = KnowledgeService()
        return self._service

    def retrieve(self, project_id: Optional[str], query: str, top_k: int = 5) -> dict:
        """检索方法论文献并返回 {context_block, citations}。

        - project_id 为空或检索无结果时返回 {"context_block": "", "citations": []}。
        - 否则生成可读的 context_block（逐条列出分块的索引、文档标题、章节、
          偏移与摘要），以及 shape 与 build_context 一致的 citations 列表。
        """
        # 空 project_id 直接短路，避免误跨项目边界
        if not project_id:
            return {"context_block": "", "citations": []}

        # 使用关键字参数调用，兼容真实 KnowledgeService 与 FakeService 的不同形参顺序
        chunks = self._get_service().retrieve(
            project_id=project_id, query=query, top_k=top_k
        )
        if not chunks:
            return {"context_block": "", "citations": []}

        citations: List[dict] = []
        lines: List[str] = []
        for i, ch in enumerate(chunks, start=1):
            snippet = (ch.get("content") or "")[:200]
            offset = ch.get("idx", 0)
            citations.append({
                "index": i,
                "chunk_id": ch.get("chunk_id"),
                "doc_title": ch.get("doc_title"),
                "section": ch.get("section"),
                "offset": offset,
                "score": ch.get("score", 0.0),
                "snippet": snippet,
            })
            doc_title = ch.get("doc_title") or ""
            section = ch.get("section") or ""
            lines.append(
                f"[{i}] 《{doc_title}》{section} (offset={offset}): {snippet}"
            )

        context_block = "\n".join(lines)
        return {"context_block": context_block, "citations": citations}


def validate_source_refs(generated_items: list, citations: list) -> dict:
    """校验每个生成项的 source_ref 是否指向已检索到的分块。

    Args:
        generated_items: 生成项列表，每项可携带 "source_ref": [chunk_id, ...]。
        citations: MethodologyBridge.retrieve 返回的引用列表，每项含 "chunk_id"。
    Returns:
        {
          "coverage": float,   # 0..1，拥有合法非空 source_ref 的项占比
          "total": int,
          "covered": int,      # 每个 source_ref 都属于已检索集合的项数
          "flagged": [str],    # 缺失/非法 source_ref 的项的可读标识
        }
    规则：
      - 合法 chunk_id 集合 = {c["chunk_id"] for c in citations}
      - 项被「覆盖」当且仅当其拥有非空 source_ref 且每个 id 均在合法集合中。
      - 无 source_ref 字段、source_ref 为 []，或任一 id 未知 -> 未覆盖 -> 追加到 flagged
        （标识取 item["id"]/item["name"]，否则回退为 f"item[{i}]"）。
    边界：
      - generated_items 为空 -> coverage=0.0, total=0, covered=0, flagged=[]。
      - citations 为空（未检索）-> 任何 source_ref 均未知均被标记；[] 亦被标记。
    """
    generated_items = generated_items or []
    valid_ids = {c.get("chunk_id") for c in (citations or [])}

    total = len(generated_items)
    covered = 0
    flagged: List[str] = []

    for i, item in enumerate(generated_items):
        item = item if isinstance(item, dict) else {}
        source_ref = item.get("source_ref")
        refs = source_ref if isinstance(source_ref, list) else []
        is_covered = bool(refs) and all(r in valid_ids for r in refs)
        if is_covered:
            covered += 1
        else:
            label = item.get("id") or item.get("name") or f"item[{i}]"
            flagged.append(str(label))

    coverage = covered / total if total else 0.0
    return {
        "coverage": coverage,
        "total": total,
        "covered": covered,
        "flagged": flagged,
    }
