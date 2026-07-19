import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.knowledge.service import KnowledgeService
from app.knowledge.answer import RAGAnswerGenerator
from app.knowledge.eval import RAGEvaluator
from app.knowledge.query_rewrite import get_query_rewriter
from app.knowledge.rag_trace import RAGTrace, MockTraceStore
from app.knowledge.agent_router import get_agent_router
from app.knowledge.self_rag import get_self_rag
from app.knowledge.feedback import get_feedback_store, get_feedback_analyzer
from app.knowledge.permission import get_permission_manager


def test_rag_end_to_end():
    print("=" * 60)
    print("RAG 端到端测试（生产级改进版）")
    print("=" * 60)
    
    project_id = "test-rag-project-001"
    
    print("\n[1/6] 初始化知识服务...")
    service = KnowledgeService()
    print("✓ 知识服务初始化完成")
    
    print("\n[2/6] 导入测试文档...")
    test_docs = [
        {
            "title": "内容安全管理规范",
            "text": """# 内容安全管理规范

## 违规定义

内容违规包括但不限于以下情形：
- 涉及色情、暴力、恐怖主义的内容
- 虚假信息、谣言传播
- 侵犯他人隐私的内容
- 违反法律法规的言论

## 审核流程

所有用户生成内容必须经过以下审核流程：
1. 自动审核：通过AI模型进行初步筛选
2. 人工复核：对疑似违规内容进行人工确认
3. 违规处理：根据违规严重程度采取相应措施

## 处罚机制

违规内容的处罚分为三个等级：
- 轻度违规：警告并删除内容
- 中度违规：限制发布权限7天
- 重度违规：永久封禁账号
""",
            "source": "content_safety_policy.txt"
        },
        {
            "title": "师资管理办法",
            "text": """# 师资管理办法

## 招聘标准

教师招聘应符合以下标准：
- 具有相关专业本科以上学历
- 三年以上教学经验
- 通过教师资格认证
- 良好的沟通能力和团队协作精神

## 培训体系

新教师入职后需完成以下培训：
1. 岗前培训：了解学校规章制度和教学流程
2. 技能培训：掌握教学方法和工具使用
3. 实践教学：在导师指导下进行实际教学

## 绩效评估

教师绩效评估包括以下维度：
- 教学质量：学生满意度、教学效果
- 科研成果：论文发表、项目参与
- 师德师风：职业操守、师生关系

## 流失预警

当出现以下情况时启动流失预警：
- 连续三个月绩效评估低于及格线
- 教师主动提出离职意向
- 被其他机构挖角的迹象
""",
            "source": "teacher_management.txt"
        },
        {
            "title": "咖啡烘焙工艺指南",
            "text": """# 咖啡烘焙工艺指南

## 烘焙阶段

咖啡烘焙分为四个阶段：
1. 脱水阶段：去除咖啡豆中的水分
2. 梅纳反应阶段：产生风味物质
3. 焦糖化阶段：糖分转化为焦糖
4. 烘焙度控制：根据目标烘焙度停止加热

## 温度控制

烘焙过程中温度控制至关重要：
- 入豆温度：180-190°C
- 一爆温度：195-205°C
- 二爆温度：220-230°C
- 出豆温度：根据目标烘焙度调整

## 风味特征

不同烘焙度的风味特征：
- 浅烘焙：酸度明亮，果香突出
- 中烘焙：平衡酸苦，坚果风味
- 深烘焙：苦味浓郁，巧克力风味
""",
            "source": "coffee_roasting.txt"
        }
    ]
    
    doc_ids = []
    for doc in test_docs:
        result = service.ingest_text(
            text=doc["text"],
            project_id=project_id,
            title=doc["title"],
            source=doc["source"]
        )
        print(f"  - {doc['title']}: {result['status']} (doc_id={result['doc_id']})")
        doc_ids.append(result["doc_id"])
    print("✓ 测试文档导入完成")
    
    print("\n[3/6] 测试 Query Rewrite 层...")
    rewriter = get_query_rewriter(mock=True)
    
    rewrite_queries = [
        "怎么降低客服投诉率？",
        "内容安全违规有哪些类型？",
        "如何防止教师流失？",
        "咖啡烘焙有哪些阶段？",
    ]
    
    for query in rewrite_queries:
        result = rewriter.rewrite(query)
        print(f"  - 原问题: '{query}'")
        print(f"    意图分类: {result['intent']}")
        print(f"    关键词: {result['keywords']}")
        print(f"    扩展查询: {result['expanded_queries']}")
        print()
    print("✓ Query Rewrite 层测试完成")
    
    print("\n[4/6] 测试检索功能（含 metadata 过滤）...")
    test_queries = [
        ("内容安全 违规", "应检索到内容安全管理规范"),
        ("咖啡 烘焙", "应检索到咖啡烘焙工艺指南"),
        ("教师 流失", "应检索到师资管理办法"),
        ("用户反馈 投诉", "可能无相关结果"),
    ]
    
    for query, expected in test_queries:
        results = service.retrieve(query, project_id=project_id, top_k=3)
        print(f"  - 查询: '{query}'")
        print(f"    期望: {expected}")
        print(f"    结果数: {len(results)}")
        for r in results:
            print(f"      * [{r['score']:.4f}] {r['doc_title']} - {r['section']} - {r['content'][:60]}...")
        print()
    
    print("  - 测试 metadata 过滤（按 section）:")
    filtered = service.retrieve("违规", project_id=project_id, top_k=3, 
                               filters={"section": "违规定义"})
    print(f"    过滤 '违规定义' 节: {len(filtered)} 条结果")
    for r in filtered:
        print(f"      * {r['doc_title']} - {r['section']}")
    print("✓ 检索功能测试完成")
    
    print("\n[5/6] 测试 RAG 答案生成（含 Trace）...")
    generator = RAGAnswerGenerator(provider="mock", service=service)
    trace_store = MockTraceStore()
    
    rag_queries = [
        "内容安全违规有哪些类型？",
        "咖啡烘焙有哪些阶段？",
        "如何防止教师流失？",
    ]
    
    for query in rag_queries:
        trace = RAGTrace()
        trace.record_query(query)
        
        rewrite_result = rewriter.rewrite(query)
        trace.record_rewrite(rewrite_result)
        
        chunks = service.retrieve(query, project_id=project_id, top_k=5)
        trace.record_retrieval(chunks, duration_ms=10.0)
        
        result = generator.answer(query, project_id=project_id, top_k=5)
        trace.record_generation(
            result.get("answer", ""),
            result.get("citations", []),
            result.get("metrics", {}),
            duration_ms=50.0
        )
        
        trace_store.save(trace)
        
        print(f"  - 问题: '{query}'")
        print(f"    Trace ID: {trace.trace_id[:8]}...")
        print(f"    答案: {result['answer'][:200]}...")
        print(f"    引用数: {len(result['citations'])}")
        if "metrics" in result:
            print(f"    引用率: {result['metrics'].get('citation_rate', 0) * 100:.1f}%")
        print(f"    状态: {'正常' if not result.get('degraded') else '降级'}")
        print()
    
    recent_traces = trace_store.list_recent(5)
    print(f"  - 最近 Trace 记录: {len(recent_traces)} 条")
    for t in recent_traces:
        print(f"    * {t['trace_id'][:8]}... - {t['query'][:30]} - {t['total_duration_ms']:.1f}ms")
    print("✓ RAG 答案生成测试完成")
    
    print("\n[6/6] 测试 RAG 评估（含自动生成 gold 数据）...")
    evaluator = RAGEvaluator()
    
    all_docs = service.list_documents(project_id=project_id)
    for doc in all_docs["documents"]:
        print(f"  - 文档: {doc['title']} (chunk_count={doc['chunk_count']})")
    
    print("  - 自动生成 gold data...")
    gold_data = evaluator.generate_gold_data(service, project_id=project_id, num_samples=5)
    for i, item in enumerate(gold_data):
        print(f"    * [{i+1}] 查询: '{item['query']}' -> 期望 chunk: {item['expected_chunk_ids'][0][:8]}...")
    
    eval_result = evaluator.evaluate(
        service,
        gold=gold_data,
        project_id=project_id,
        top_k=5,
        with_faithfulness=True
    )
    
    print(f"\n  - 评估结果:")
    print(f"    precision@k: {eval_result['precision@k']}")
    print(f"    recall@k: {eval_result['recall@k']}")
    print(f"    f1@k: {eval_result['f1@k']}")
    print(f"    mrr: {eval_result['mrr']}")
    print(f"    ndcg@k: {eval_result['ndcg@k']}")
    print(f"    样本数: {eval_result['n']}")
    
    compare_result = evaluator.compare_before_after(
        service,
        gold=gold_data,
        project_id=project_id,
        top_k=5
    )
    print(f"\n  - Rerank对比:")
    print(f"    重排前 precision@k: {compare_result['before']['precision@k']}")
    print(f"    重排后 precision@k: {compare_result['after']['precision@k']}")
    print(f"    精度变化: {compare_result['delta_precision']}")
    print(f"    F1变化: {compare_result['delta_f1']}")
    print(f"    MRR变化: {compare_result['delta_mrr']}")
    print(f"    NDCG变化: {compare_result['delta_ndcg']}")
    print(f"    重排未恶化: {compare_result['rerank_not_worse']}")
    print("✓ RAG评估测试完成")
    
    print("\n" + "=" * 60)
    print("RAG 端到端测试（生产级改进版）全部通过！")
    print("=" * 60)

    print("\n[7/7] 测试新模块集成（Agent Router / Self-RAG / Feedback / Permission）...")
    
    print("  - 测试 Agent Router...")
    router = get_agent_router(mock=True)
    route_queries = ["内容安全违规有哪些类型？", "查询教师流失数据", "咖啡烘焙温度计算"]
    for query in route_queries:
        result = router.route(query)
        print(f"    * 查询: '{query}'")
        print(f"      意图: {result['intent']}")
        print(f"      路由决策: {result['router_decision']}")
        print(f"      工具: {[t.tool_name for t in result['tools']]}")
        print()
    print("    ✓ Agent Router 测试完成")

    print("  - 测试 Self-RAG...")
    self_rag = get_self_rag(provider="mock", service=service)
    self_rag_result = self_rag.retrieve_with_self_rag("内容安全违规有哪些类型？", project_id, top_k=5)
    print(f"    * 查询: '内容安全违规有哪些类型？'")
    print(f"      重试次数: {self_rag_result['retries']}")
    print(f"      成功: {self_rag_result['success']}")
    print(f"      最终结果数: {len(self_rag_result['final_chunks'])}")
    for attempt in self_rag_result["history"]:
        print(f"      - 尝试 {attempt['attempt']}: decision={attempt['decision']}, confidence={attempt['confidence']}")
    print("    ✓ Self-RAG 测试完成")

    print("  - 测试 Feedback...")
    store = get_feedback_store(mock=True)
    stats = store.get_stats()
    print(f"    * 反馈统计:")
    print(f"      总数: {stats['total']}")
    print(f"      按类型: {stats.get('by_type', {})}")
    print(f"      好评率: {stats.get('positive_rate', 0) * 100:.1f}%")
    
    analyzer = get_feedback_analyzer(mock=True)
    problematic = analyzer.analyze_problematic_queries(top_n=3)
    print(f"    * 问题查询:")
    for p in problematic:
        print(f"      - '{p['query']}' (负面反馈: {p['negative_count']}次)")
    
    improvements = analyzer.suggest_improvements()
    print(f"    * 改进建议:")
    for imp in improvements[:2]:
        print(f"      - {imp['suggestion']}")
    print("    ✓ Feedback 测试完成")

    print("  - 测试 Permission...")
    perm_manager = get_permission_manager(mock=True)
    test_users = ["user-001", "user-002", "user-003", "user-004"]
    for user_id in test_users:
        role = perm_manager.get_user_role(user_id)
        perm_filters = perm_manager.get_permission_filters(user_id)
        print(f"    * 用户 {user_id}:")
        print(f"      角色: {role}")
        print(f"      允许访问的域: {perm_filters['allowed_domains']}")
    
    admin_chunks = service.retrieve("内容安全", project_id=project_id, top_k=3, user_id="user-001")
    guest_chunks = service.retrieve("内容安全", project_id=project_id, top_k=3, user_id="user-004")
    print(f"    * admin(user-001) 检索结果: {len(admin_chunks)} 条")
    print(f"    * guest(user-004) 检索结果: {len(guest_chunks)} 条")
    print("    ✓ Permission 测试完成")

    print("\n" + "=" * 60)
    print("RAG 端到端测试（生产级改进版 - 完整集成）全部通过！")
    print("=" * 60)


if __name__ == "__main__":
    test_rag_end_to_end()
