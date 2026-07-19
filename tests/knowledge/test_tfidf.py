import sys
import os
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from app.repositories.knowledge_repository import KnowledgeRepository
from app.knowledge.schema import ensure_schema
from app.knowledge.backends.tfidf import TfidfBackend

def _tmp_repo():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    repo = KnowledgeRepository(db_path=f.name)
    ensure_schema(repo)
    return repo

def test_tfidf_backend_cosine():
    repo = _tmp_repo()
    tb = TfidfBackend(repo)
    recs = [
        {"id": "a", "content": "内容安全平台 违规信息 过滤 审核", "doc_id": "d1"},
        {"id": "b", "content": "咖啡 烘焙 风味 产地", "doc_id": "d2"},
    ]
    for r in recs:
        repo._execute(
            "INSERT INTO knowledge_chunks (id, doc_id, idx, content, section, metadata_json) VALUES (?,?,?,?,?,?)",
            (r["id"], r["doc_id"], 0, r["content"], "", "{}"))
    repo._commit()
    tb.index(recs)
    res = tb.search("内容安全 审核")
    assert res and res[0] == "a"

def test_tfidf_idf_rare_higher():
    # 稀有词（仅 1 篇出现）idf 应高于常见词（2 篇都出现）
    repo = _tmp_repo()
    tb = TfidfBackend(repo)
    recs = [
        {"id": "x", "content": "苹果 苹果 苹果 苹果 内容 审核", "doc_id": "d1"},
        {"id": "y", "content": "苹果 麒麟 梼杌", "doc_id": "d2"},
    ]
    for r in recs:
        repo._execute(
            "INSERT INTO knowledge_chunks (id, doc_id, idx, content, section, metadata_json) VALUES (?,?,?,?,?,?)",
            (r["id"], r["doc_id"], 0, r["content"], "", "{}"))
    repo._commit()
    tb.index(recs)
    vocab, idf = tb._load_model()
    # PLAN TYPO FIX: the original plan asserted idf["獬豸"] but "獬豸" is NOT in the
    # corpus (would KeyError). "麒麟" appears only in doc y (df=1) → rare; "苹果"
    # appears in both docs (df=2) → common. We assert rare > common, preserving intent.
    assert idf["麒麟"] > idf["苹果"]
