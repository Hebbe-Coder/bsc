import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.knowledge.service import KnowledgeService
from app.knowledge.answer import RAGAnswerGenerator
from app.knowledge.query_rewrite import get_query_rewriter
from app.knowledge.self_rag import get_self_rag
from app.knowledge.agent_router import get_agent_router

def test_real_llm_rag():
    print("=" * 60)
    print("RAG 端到端测试（真实 LLM 模式 - DeepSeek）")
    print("=" * 60)

    print("\n[1/4] 初始化知识服务并导入测试文档...")
    service = KnowledgeService()
    project_id = "test-rag-project-001"
    
    test_docs = [
        {
            "title": "内容安全管理规范",
            "content": """# 内容安全管理规范

## 违规定义
内容违规包括但不限于以下情形：
- 涉及色情、暴力、恐怖主义的内容
- 虚假信息、谣言传播
- 侵犯他人隐私的内容

## 处罚机制
违规内容的处罚分为三个等级：
- 轻度违规：警告并删除内容
- 中度违规：限制发布权限7天
- 重度违规：永久封禁账号

## 审核流程
所有用户生成内容必须经过以下审核流程：
1. 自动审核：通过AI模型进行初步筛选
2. 人工复核：对疑似违规内容进行人工审核""",
        },
        {
            "title": "师资管理办法",
            "content": """# 师资管理办法

## 流失预警
当出现以下情况时启动流失预警：
- 连续三个月绩效评估低于及格线
- 教师主动提出离职意向
- 被其他机构挖角的迹象

## 绩效评估
教师绩效评估包括以下维度：
- 教学质量：学生满意度、教学效果
- 科研成果：论文发表、项目参与
- 师德师风：职业操守

## 培训体系
新教师入职后需完成以下培训：
1. 岗前培训：了解学校规章制度和教学流程
2. 技能培训：掌握教学方法和工具使用""",
        },
    ]
    
    for doc in test_docs:
        try:
            service.upsert_document(project_id, doc["title"], doc["content"])
            print(f"  - 导入文档: {doc['title']}")
        except Exception as e:
            print(f"  - 文档已存在: {doc['title']}")
    
    print(f"  ✓ 知识服务初始化完成")

    print("\n[2/4] 测试 Query Rewrite（真实 LLM）...")
    rewriter = get_query_rewriter(mock=False, provider="deepseek")
    queries = [
        "内容安全违规有哪些类型？",
        "如何防止教师流失？",
        "咖啡烘焙有哪些阶段？",
    ]
    for query in queries:
        result = rewriter.rewrite(query)
        print(f"  - 原问题: '{query}'")
        print(f"    意图: {result.get('intent', 'unknown')}")
        print(f"    改写查询: {result.get('rewritten_query', query)}")
        print(f"    扩展查询: {result.get('expanded_queries', [])}")
        print(f"    来自 LLM: {result.get('from_llm', False)}")
        print()
    print("  ✓ Query Rewrite 测试完成")

    print("\n[3/4] 测试 Self-RAG（真实 LLM）...")
    self_rag = get_self_rag(provider="deepseek", service=service)
    query = "内容安全违规有哪些类型？"
    
    print(f"  - 先测试检索是否正常...")
    chunks = service.retrieve(query, project_id=project_id, top_k=5)
    print(f"    检索结果数: {len(chunks)}")
    for i, c in enumerate(chunks):
        print(f"      [{i}] {c.get('doc_title', '')} - {c.get('section', '')}")
    
    result = self_rag.retrieve_with_self_rag(query, project_id, top_k=5)
    print(f"  - 查询: '{query}'")
    print(f"    重试次数: {result['retries']}")
    print(f"    成功: {result['success']}")
    print(f"    最终结果数: {len(result['final_chunks'])}")
    for attempt in result["history"]:
        print(f"    - 尝试 {attempt['attempt']}: decision={attempt['decision']}, confidence={attempt['confidence']}, reason={attempt.get('reason', '')}")
    print("  ✓ Self-RAG 测试完成")

    print("\n[4/4] 测试 RAG 答案生成（真实 LLM）...")
    generator = RAGAnswerGenerator(provider="deepseek", service=service)
    
    test_queries = [
        "内容安全违规有哪些类型？",
        "如何防止教师流失？",
    ]
    
    for query in test_queries:
        print(f"\n  - 问题: '{query}'")
        try:
            result = generator.answer(query, project_id=project_id, top_k=5, enable_rewrite=True)
            print(f"    答案: {result['answer'][:300]}...")
            print(f"    引用数: {len(result.get('citations', []))}")
            if "metrics" in result:
                print(f"    引用率: {result['metrics'].get('citation_rate', 0) * 100:.1f}%")
            print(f"    状态: {'正常' if not result.get('degraded') else '降级'}")
        except Exception as e:
            print(f"    错误: {e}")
    
    print("\n  ✓ RAG 答案生成测试完成")

    print("\n" + "=" * 60)
    print("RAG 端到端测试（真实 LLM 模式）全部完成！")
    print("=" * 60)

if __name__ == "__main__":
    test_real_llm_rag()
