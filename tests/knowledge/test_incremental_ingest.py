import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from app.knowledge.service import KnowledgeService


def _svc():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return KnowledgeService(db_path=f.name)


def test_idempotent_skip_when_hash_unchanged():
    svc = _svc()
    r1 = svc.ingest_text("内容安全 平台 过滤 违规", source="s1.txt", doc_format="txt")
    r2 = svc.ingest_text("内容安全 平台 过滤 违规", source="s1.txt", doc_format="txt")
    assert r1["status"] == "ingested" and r2["status"] == "skipped"
    assert r1["doc_id"] == r2["doc_id"]


def test_idempotent_update_bumps_version_and_replaces_chunks():
    svc = _svc()
    r1 = svc.ingest_text("旧版本 内容 A", source="s2.txt", doc_format="txt", project_id="p1")
    r2 = svc.ingest_text("新版本 内容 B 完全不同", source="s2.txt", doc_format="txt", project_id="p1")
    assert r1["status"] == "ingested" and r2["status"] == "updated"
    assert r2["version"] == 2
    hit_new = svc.retrieve("新版本", top_k=3, project_id="p1")
    assert any("新版本" in (c.get("content") or "") for c in hit_new)


def test_explicit_doc_id_takes_precedence():
    svc = _svc()
    r1 = svc.ingest_text("显式 id 文档", doc_id="DOC-X", source="", doc_format="txt")
    r2 = svc.ingest_text("显式 id 文档", doc_id="DOC-X", doc_format="txt")
    assert r1["doc_id"] == "DOC-X" == r2["doc_id"]
    assert r2["status"] == "skipped"


def test_update_with_no_chunk_content_preserves_old_doc():
    """回归保护：re-ingest 同一 doc_id 但新内容切不出 chunk（如纯标题）时，
    不得删除旧文档（先校验 chunk 再执行破坏性删除）。"""
    svc = _svc()
    r1 = svc.ingest_text("原始 有效 内容 用于 检索 命中", doc_id="DOC-KEEP", doc_format="txt", project_id="p1")
    assert r1["status"] == "ingested"
    # 纯标题 → chunk_text 返回 [] → 应 skipped/no_chunks 且旧文档仍在
    r2 = svc.ingest_text("# 仅标题\n## 副标题", doc_id="DOC-KEEP", doc_format="md", project_id="p1")
    assert r2["status"] == "skipped" and r2["reason"] == "no_chunks"
    # 旧内容仍可检索到，未被静默删除
    hits = svc.retrieve("原始 内容", top_k=3, project_id="p1")
    assert any("原始" in (c.get("content") or "") for c in hits)
