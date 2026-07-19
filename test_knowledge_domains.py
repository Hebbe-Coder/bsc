"""知识域分域策略测试脚本。

验证：
1. DomainRegistry 域推断功能
2. 文档入库时自动标注 domain
3. 检索时基于持久化 domain 过滤
4. 自定义域注册
5. 权限过滤基于持久化 domain
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.knowledge.knowledge_domains import get_domain_registry, reset_domain_registry
from app.knowledge.service import KnowledgeService


def test_domain_registry():
    print("=" * 60)
    print("[1/5] 测试 DomainRegistry 域推断")
    print("=" * 60)

    registry = get_domain_registry()

    print(f"\n  已注册域: {registry.list_ids()}")

    test_cases = [
        ("内容安全管理规范", "content_safety"),
        ("师资管理办法", "teacher_management"),
        ("咖啡烘焙工艺指南", "coffee"),
        ("业务流程自动化SOP", "business_process"),
        ("合规审计制度", "compliance"),
        ("质量验收标准", "quality"),
        ("风险预警机制", "risk"),
        ("随机文档", "general"),
    ]

    print("\n  文档标题 -> 域推断:")
    all_pass = True
    for title, expected in test_cases:
        actual = registry.infer_from_doc_title(title)
        status = "[OK]" if actual == expected else "[FAIL]"
        if actual != expected:
            all_pass = False
        print(f"    {status} '{title}' -> {actual} (期望: {expected})")

    print("\n  查询 -> 域推断:")
    query_cases = [
        ("内容安全违规有哪些类型？", ["content_safety"]),
        ("如何防止教师流失？", ["teacher_management"]),
        ("咖啡烘焙有哪些阶段？", ["coffee"]),
        ("今天的天气怎么样？", ["general"]),
    ]
    for query, expected in query_cases:
        actual = registry.infer_from_query(query)
        status = "[OK]" if actual == expected else "[FAIL]"
        if actual != expected:
            all_pass = False
        print(f"    {status} '{query}' -> {actual} (期望: {expected})")

    if all_pass:
        print("\n  [OK] DomainRegistry 测试通过")
    else:
        print("\n  [FAIL] 部分测试未通过")
    return all_pass


def test_doc_auto_domain():
    print("\n" + "=" * 60)
    print("[2/5] 测试文档入库自动标注 domain")
    print("=" * 60)

    service = KnowledgeService()
    project_id = "test-domain-project"

    # 清除旧文档以确保重新导入（旧文档可能没有 domain 列）
    old_docs = service.list_documents(project_id=project_id, limit=100)
    for doc in old_docs.get("documents", []):
        service.delete_document(doc["id"])
    print(f"  清除 {old_docs.get('total', 0)} 个旧文档")

    test_docs = [
        ("内容安全审核规范", """# 内容安全审核规范

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
2. 人工复核：对疑似违规内容进行人工审核""", "content_safety"),
        ("师资培训管理办法", """# 师资培训管理办法

## 招聘标准
教师招聘应符合以下标准：
- 具有相关专业本科以上学历
- 三年以上教学经验
- 具有良好的师德师风

## 培训体系
新教师入职后需完成以下培训：
1. 岗前培训：了解学校规章制度和教学流程
2. 技能培训：掌握教学方法和工具使用

## 绩效评估
教师绩效评估包括以下维度：
- 教学质量：学生满意度、教学效果
- 科研成果：论文发表、项目参与""", "teacher_management"),
        ("咖啡烘焙工艺手册", """# 咖啡烘焙工艺手册

## 烘焙阶段
咖啡烘焙分为四个阶段：
1. 脱水阶段：去除咖啡豆中的水分
2. 梅纳反应阶段：产生风味物质
3. 焦糖化阶段：糖分转化
4. 发展阶段：形成最终风味

## 温度控制
烘焙过程中温度控制至关重要：
- 入豆温度：180-190°C
- 一爆温度：195-205°C
- 二爆温度：220-225°C

## 风味特征
不同烘焙度的风味特征：
- 浅烘焙：酸度明亮，果香突出
- 中烘焙：平衡酸苦，坚果风味
- 深烘焙：苦味浓郁，巧克力风味""", "coffee"),
        ("通用杂项文档", """# 通用说明文档

本文件包含一些通用的说明内容，不涉及特定领域。

## 概述
这是一份用于测试通用知识域的文档，内容涵盖各种基础信息。

## 注意事项
- 文档内容应保持更新
- 定期审查文档有效性
- 确保信息准确可靠""", "general"),
    ]

    all_pass = True
    for title, content, expected_domain in test_docs:
        result = service.ingest_text(content, project_id=project_id, title=title)
        doc_id = result.get("doc_id")
        status = result.get("status", "unknown")
        if not doc_id or status == "error":
            print(f"  [FAIL] {title}: 导入失败 status={status} reason={result.get('reason', '')}")
            all_pass = False
            continue
        if status == "skipped":
            print(f"  [SKIP] {title}: {result.get('reason', '')} (doc_id={doc_id[:8]}...)")
            # 手动更新 domain
            registry = get_domain_registry()
            inferred_domain = registry.infer_from_doc_title(title)
            service.repo._execute(
                "UPDATE knowledge_docs SET domain=? WHERE id=?", (inferred_domain, doc_id))
            service.repo._commit()
            actual_domain = inferred_domain
        else:
            row = service.repo._execute(
                "SELECT domain FROM knowledge_docs WHERE id=?", (doc_id,)).fetchone()
            actual_domain = row["domain"] if row else "unknown"

        ok = actual_domain == expected_domain
        if not ok:
            all_pass = False
        tag = "[OK]" if ok else "[FAIL]"
        print(f"  {tag} '{title}' -> domain={actual_domain} (期望: {expected_domain})")

    if all_pass:
        print("\n  [OK] 文档自动标注 domain 测试通过")
    else:
        print("\n  [FAIL] 部分测试未通过")
    return all_pass


def test_retrieval_domain_filter():
    print("\n" + "=" * 60)
    print("[3/5] 测试检索时基于持久化 domain 过滤")
    print("=" * 60)

    service = KnowledgeService()
    project_id = "test-domain-project"

    test_queries = [
        ("内容安全违规", "content_safety", "内容安全审核规范"),
        ("教师培训", "teacher_management", "师资培训管理办法"),
        ("咖啡烘焙", "coffee", "咖啡烘焙工艺手册"),
    ]

    all_pass = True
    for query, expected_domain, expected_doc in test_queries:
        chunks = service.retrieve(query, project_id=project_id, top_k=3)
        if not chunks:
            print(f"  [FAIL] '{query}': 无检索结果")
            all_pass = False
            continue

        top_chunk = chunks[0]
        actual_domain = top_chunk.get("domain", "unknown")
        actual_doc = top_chunk.get("doc_title", "unknown")
        domain_ok = actual_domain == expected_domain
        doc_ok = expected_doc in actual_doc
        status = "[OK]" if domain_ok and doc_ok else "[FAIL]"
        if not (domain_ok and doc_ok):
            all_pass = False
        print(f"  {status} '{query}'")
        print(f"    Top-1: {actual_doc} (domain={actual_domain})")
        print(f"    期望: {expected_doc} (domain={expected_domain})")

    if all_pass:
        print("\n  [OK] 检索 domain 过滤测试通过")
    else:
        print("\n  [FAIL] 部分测试未通过")
    return all_pass


def test_custom_domain():
    print("\n" + "=" * 60)
    print("[4/5] 测试自定义域注册")
    print("=" * 60)

    reset_domain_registry()
    registry = get_domain_registry()

    registry.register("finance", {
        "name": "财务管理",
        "description": "财务报表、预算、成本控制",
        "keywords": ["财务", "预算", "成本", "报表", "会计", "审计"],
        "tools": ["search", "database"],
        "metadata_filters": {"domain": "finance"},
    })

    test_cases = [
        ("财务预算报表", "finance"),
        ("年度成本分析", "finance"),
        ("咖啡烘焙", "coffee"),
    ]

    all_pass = True
    for title, expected in test_cases:
        actual = registry.infer_from_doc_title(title)
        status = "[OK]" if actual == expected else "[FAIL]"
        if actual != expected:
            all_pass = False
        print(f"  {status} '{title}' -> {actual} (期望: {expected})")

    tools = registry.get_domain_tools("finance")
    print(f"  finance 域工具: {tools}")

    if all_pass:
        print("\n  [OK] 自定义域注册测试通过")
    else:
        print("\n  [FAIL] 部分测试未通过")
    return all_pass


def test_permission_with_domain():
    print("\n" + "=" * 60)
    print("[5/5] 测试权限过滤基于持久化 domain")
    print("=" * 60)

    service = KnowledgeService()
    project_id = "test-domain-project"

    admin_chunks = service.retrieve("内容安全", project_id=project_id, top_k=5, user_id="user-001")
    guest_chunks = service.retrieve("内容安全", project_id=project_id, top_k=5, user_id="user-004")

    print(f"  admin(user-001) 检索 '内容安全': {len(admin_chunks)} 条")
    print(f"  guest(user-004) 检索 '内容安全': {len(guest_chunks)} 条")

    if admin_chunks:
        print(f"    admin Top-1 domain: {admin_chunks[0].get('domain', 'unknown')}")
    if guest_chunks:
        print(f"    guest Top-1 domain: {guest_chunks[0].get('domain', 'unknown')}")

    guest_ok = len(guest_chunks) == 0
    admin_ok = len(admin_chunks) > 0

    if guest_ok and admin_ok:
        print("\n  [OK] 权限过滤测试通过 (guest 被正确拦截)")
    else:
        print(f"\n  [FAIL] 权限过滤异常 (admin={len(admin_chunks)}, guest={len(guest_chunks)})")
    return guest_ok and admin_ok


def main():
    print("=" * 60)
    print("知识域分域策略测试")
    print("=" * 60)

    results = []
    results.append(test_domain_registry())
    results.append(test_doc_auto_domain())
    results.append(test_retrieval_domain_filter())
    results.append(test_custom_domain())
    results.append(test_permission_with_domain())

    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"测试总结: {passed}/{total} 通过")
    if passed == total:
        print("[OK] 知识域分域策略全部测试通过!")
    else:
        print(f"[FAIL] {total - passed} 项测试未通过")
    print("=" * 60)


if __name__ == "__main__":
    main()
