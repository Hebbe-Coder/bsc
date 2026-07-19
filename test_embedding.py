"""Embedding 连通性与向量检索效果测试脚本。

使用方法:
  1. 在 .env 中设置 SILICONFLOW_API_KEY=sk-xxx
  2. 设置 EMBEDDING_PROVIDER=siliconflow
  3. 运行: python test_embedding.py
"""
import sys
import os
import time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.config import settings
from app.knowledge.embeddings import get_embedding_provider, MockEmbeddingProvider


def test_embedding_connectivity():
    """测试 embedding 服务连通性"""
    print("=" * 60)
    print("Embedding 连通性测试")
    print("=" * 60)
    print(f"  Provider: {settings.EMBEDDING_PROVIDER}")
    print(f"  Model: {settings.SILICONFLOW_EMBEDDING_MODEL if settings.EMBEDDING_PROVIDER == 'siliconflow' else settings.EMBEDDING_MODEL}")
    print(f"  Base URL: {settings.SILICONFLOW_BASE_URL if settings.EMBEDDING_PROVIDER == 'siliconflow' else settings.EMBEDDING_BASE_URL}")
    api_key = settings.SILICONFLOW_API_KEY if settings.EMBEDDING_PROVIDER == 'siliconflow' else settings.EMBEDDING_API_KEY
    print(f"  API Key 配置: {'[OK]' if api_key else '[MISSING]'}")
    print()

    if settings.EMBEDDING_PROVIDER == "mock":
        print("  [!] 当前为 mock 模式，请在 .env 中配置 SILICONFLOW_API_KEY 并设置 EMBEDDING_PROVIDER=siliconflow")
        print("  跳过连通性测试，使用 mock 模式测试基本功能...")
        provider = MockEmbeddingProvider()
    else:
        try:
            provider = get_embedding_provider()
            print(f"  [OK] Provider 加载成功: {provider.name}")
        except Exception as e:
            print(f"  [FAIL] Provider 加载失败: {e}")
            return False

    print("\n[1/3] 测试基本 embedding 功能...")
    test_texts = [
        "内容安全违规有哪些类型？",
        "如何防止教师流失？",
        "咖啡烘焙有哪些阶段？",
    ]

    try:
        t0 = time.perf_counter()
        vectors = provider.embed(test_texts)
        elapsed = (time.perf_counter() - t0) * 1000

        print(f"  [OK] Embedding 成功")
        print(f"    文本数: {len(test_texts)}")
        print(f"    向量数: {len(vectors)}")
        print(f"    维度: {len(vectors[0])}")
        print(f"    耗时: {elapsed:.1f}ms")
    except Exception as e:
        print(f"  [FAIL] Embedding 失败: {e}")
        return False

    print("\n[2/3] 测试语义相似度...")
    query_vec = np.array(vectors[0])
    doc_vecs = [np.array(v) for v in vectors]

    for i, (text, vec) in enumerate(zip(test_texts, doc_vecs)):
        sim = float(np.dot(query_vec, vec) / (np.linalg.norm(query_vec) * np.linalg.norm(vec)))
        print(f"  '{test_texts[0]}' vs '{text}': {sim:.4f}")

    print("\n[3/3] 测试批量 embedding...")
    batch_texts = [f"测试文本 {i}" for i in range(20)]
    try:
        t0 = time.perf_counter()
        batch_vectors = provider.embed(batch_texts)
        elapsed = (time.perf_counter() - t0) * 1000
        print(f"  [OK] 批量 Embedding 成功")
        print(f"    文本数: {len(batch_texts)}")
        print(f"    向量数: {len(batch_vectors)}")
        print(f"    耗时: {elapsed:.1f}ms")
        print(f"    平均: {elapsed / len(batch_texts):.1f}ms/条")
    except Exception as e:
        print(f"  [FAIL] 批量 Embedding 失败: {e}")
        return False

    print("\n" + "=" * 60)
    print("Embedding 测试完成！")
    print("=" * 60)
    return True


def test_vector_search():
    """测试向量检索效果"""
    print("\n" + "=" * 60)
    print("向量检索效果测试")
    print("=" * 60)

    if settings.EMBEDDING_PROVIDER == "mock":
        print("  [!] mock 模式下向量检索非真实语义，跳过")
        return

    from app.knowledge.service import KnowledgeService

    service = KnowledgeService()
    project_id = "test-rag-project-001"

    queries = [
        ("内容安全违规有哪些类型？", "内容安全管理规范"),
        ("如何防止教师流失？", "师资管理办法"),
        ("咖啡烘焙有哪些阶段？", "咖啡烘焙工艺指南"),
    ]

    print(f"\n  测试项目: {project_id}")
    print(f"  Provider: {settings.EMBEDDING_PROVIDER}")
    print()

    for query, expected_doc in queries:
        print(f"  查询: '{query}'")
        print(f"  期望文档: {expected_doc}")

        chunks = service.retrieve(query, project_id=project_id, top_k=5)
        print(f"  检索结果: {len(chunks)} 条")

        if chunks:
            top_doc = chunks[0].get("doc_title", "")
            match = "[OK]" if expected_doc in top_doc else "[FAIL]"
            print(f"  Top-1: {top_doc} {match}")
            for i, c in enumerate(chunks[:3]):
                print(f"    [{i}] {c.get('doc_title', '')} - {c.get('section', '')}")
        else:
            print(f"  [FAIL] 无检索结果")
        print()

    print("=" * 60)
    print("向量检索效果测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    success = test_embedding_connectivity()
    if success:
        test_vector_search()
