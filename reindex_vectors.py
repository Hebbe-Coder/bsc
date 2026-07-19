"""重新索引向量脚本：切换 embedding 模型后重建所有文档的向量索引。

使用方法:
  1. 在 .env 中配置 SILICONFLOW_API_KEY 和 EMBEDDING_PROVIDER=siliconflow
  2. 运行: python reindex_vectors.py
  3. 脚本会自动清除旧向量并按新模型重建索引
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.config import settings
from app.knowledge.service import KnowledgeService
from app.knowledge.knowledge_domains import get_domain_registry


def reindex_all_vectors():
    print("=" * 60)
    print("重新索引向量")
    print("=" * 60)
    print(f"  Embedding Provider: {settings.EMBEDDING_PROVIDER}")
    if settings.EMBEDDING_PROVIDER == "siliconflow":
        print(f"  Model: {settings.SILICONFLOW_EMBEDDING_MODEL}")
        print(f"  API Key: {'[OK]' if settings.SILICONFLOW_API_KEY else '[MISSING]'}")
    elif settings.EMBEDDING_PROVIDER == "openai":
        print(f"  Model: {settings.EMBEDDING_MODEL}")
        print(f"  API Key: {'[OK]' if settings.EMBEDDING_API_KEY else '[MISSING]'}")
    else:
        print(f"  [!] mock 模式无需重新索引")
        return

    if settings.EMBEDDING_PROVIDER == "mock":
        print("\n  [!] 当前为 mock 模式，跳过重新索引")
        return

    service = KnowledgeService()
    registry = get_domain_registry()

    print("\n[1/4] 清除陈旧向量...")
    cleared = service.reindex_stale_vectors()
    print(f"  清除 {cleared} 条陈旧向量")

    print("\n[2/4] 获取所有文档...")
    docs_result = service.list_documents(limit=1000)
    docs = docs_result["documents"]
    total = docs_result["total"]
    print(f"  文档总数: {total}")

    if total == 0:
        print("  [!] 没有文档需要重新索引")
        return

    print("\n[3/4] 更新文档知识域...")
    domain_updated = 0
    for doc in docs:
        doc_id = doc["id"]
        title = doc.get("title", "")
        old_domain = doc.get("domain", "general")
        new_domain = registry.infer_from_doc_title(title)
        if old_domain != new_domain:
            service.repo._execute(
                "UPDATE knowledge_docs SET domain=? WHERE id=?",
                (new_domain, doc_id))
            domain_updated += 1
    service.repo._commit()
    print(f"  更新 {domain_updated} 个文档的 domain")

    print("\n[4/4] 重新索引文档...")
    success = 0
    failed = 0
    skipped = 0
    t0 = time.perf_counter()

    for i, doc in enumerate(docs):
        doc_id = doc["id"]
        title = doc.get("title", "")
        project_id = doc.get("project_id", "")

        try:
            chunks_rows = service.repo._execute(
                "SELECT id, content FROM knowledge_chunks WHERE doc_id=?",
                (doc_id,)).fetchall()

            if not chunks_rows:
                print(f"  [{i+1}/{total}] {title}: 无 chunk，跳过")
                skipped += 1
                continue

            chunk_records = [
                {"id": r["id"], "content": r["content"], "doc_id": doc_id}
                for r in chunks_rows
            ]

            service.backends["vector"].index(chunk_records)
            print(f"  [{i+1}/{total}] {title}: {len(chunk_records)} chunks [OK]")
            success += 1
        except Exception as e:
            print(f"  [{i+1}/{total}] {title}: [FAIL] {e}")
            failed += 1

    elapsed = time.perf_counter() - t0
    print(f"\n  重新索引完成:")
    print(f"    成功: {success}")
    print(f"    失败: {failed}")
    print(f"    跳过: {skipped}")
    print(f"    耗时: {elapsed:.1f}s")

    print("\n" + "=" * 60)
    print("重新索引向量完成！")
    print("=" * 60)


if __name__ == "__main__":
    reindex_all_vectors()
