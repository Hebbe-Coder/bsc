"""三级权限模型测试脚本（知识域 -> 文档 -> 章节）。

测试场景：
1. 域级别权限：不同角色能访问的知识域
2. 文档级别权限：同域内不同文档的访问限制
3. 章节级别权限：同文档内不同章节的访问限制
4. 权限向下收敛：子级不能比父级更宽松
5. 检索时权限过滤：用户只能检索到有权限的内容
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.knowledge.permission import (
    PermissionManager, MockPermissionManager,
    ACCESS_LEVELS, ACCESS_LEVEL_ROLES, DEFAULT_DOMAIN_ACCESS,
    _compare_access_level, _restrict_access_level,
)
from app.knowledge.service import KnowledgeService


def test_access_level_hierarchy():
    print("=" * 60)
    print("[1/6] 测试访问级别层级")
    print("=" * 60)

    print(f"\n  访问级别（从松到严）:")
    sorted_levels = sorted(ACCESS_LEVELS.items(), key=lambda x: x[1])
    for level, val in sorted_levels:
        roles = ACCESS_LEVEL_ROLES[level]
        print(f"    {level:15s} (值={val}) - 角色: {roles}")

    # 测试比较函数
    test_cases = [
        ("public", "private", -1),
        ("private", "public", 1),
        ("internal", "internal", 0),
        ("confidential", "private", 1),
    ]
    print(f"\n  访问级别比较:")
    all_pass = True
    for a, b, expected in test_cases:
        actual = _compare_access_level(a, b)
        ok = actual == expected
        if not ok:
            all_pass = False
        tag = "[OK]" if ok else "[FAIL]"
        print(f"    {tag} {a} vs {b}: {actual} (期望: {expected})")

    # 测试向下收敛
    restrict_cases = [
        ("private", "public", "private"),    # 文档比域宽松，被域收敛
        ("internal", "private", "private"),  # 文档比域严格，保留文档
        ("public", "internal", "internal"),  # 章节比文档宽松，被文档收敛
    ]
    print(f"\n  权限向下收敛:")
    for parent, child, expected in restrict_cases:
        actual = _restrict_access_level(parent, child)
        ok = actual == expected
        if not ok:
            all_pass = False
        tag = "[OK]" if ok else "[FAIL]"
        print(f"    {tag} parent={parent}, child={child} -> effective={expected}")

    tag = "[OK]" if all_pass else "[FAIL]"
    print(f"\n  {tag} 访问级别层级测试 {'通过' if all_pass else '未通过'}")
    return all_pass


def test_domain_level_permission():
    print("\n" + "=" * 60)
    print("[2/6] 测试域级别权限")
    print("=" * 60)

    pm = MockPermissionManager()

    # 4个角色 x 8个域 = 32种组合
    test_matrix = {
        "user-001 (admin)":   {"content_safety": True,  "teacher_management": True,  "coffee": True},
        "user-002 (editor)":  {"content_safety": True,  "teacher_management": True,  "coffee": True},
        "user-003 (viewer)":  {"content_safety": False, "teacher_management": True,  "coffee": True},
        "user-004 (guest)":   {"content_safety": False, "teacher_management": False, "coffee": True},
    }

    all_pass = True
    print(f"\n  {'用户':20s} | content_safety(private) | teacher_management(internal) | coffee(public)")
    print("  " + "-" * 80)
    for user_label, domains in test_matrix.items():
        user_id = user_label.split(" ")[0]
        results = []
        for domain, expected in domains.items():
            actual = pm.can_access_domain(user_id, domain)
            ok = actual == expected
            if not ok:
                all_pass = False
            results.append("[OK]" if ok else "[FAIL]")
        print(f"  {user_label:20s} | {results[0]:^22s} | {results[1]:^26s} | {results[2]:^12s}")

    # 测试 list_allowed_domains
    print(f"\n  用户可访问的域:")
    for user_id, role in [("user-001", "admin"), ("user-003", "viewer"), ("user-004", "guest")]:
        allowed = pm.list_allowed_domains(user_id)
        print(f"    {user_id} ({role}): {len(allowed)} 个域 - {allowed}")

    tag = "[OK]" if all_pass else "[FAIL]"
    print(f"\n  {tag} 域级别权限测试 {'通过' if all_pass else '未通过'}")
    return all_pass


def test_doc_level_permission():
    print("\n" + "=" * 60)
    print("[3/6] 测试文档级别权限")
    print("=" * 60)

    pm = MockPermissionManager()

    # 同域内不同文档设置不同访问级别
    test_cases = [
        # (user_id, domain, doc_access, expected)
        ("user-001", "coffee", "confidential", True),   # admin 可以看 confidential
        ("user-002", "coffee", "confidential", False),  # editor 不能看 confidential
        ("user-002", "coffee", "private", True),        # editor 可以看 private
        ("user-003", "coffee", "internal", True),       # viewer 可以看 internal
        ("user-003", "coffee", "private", False),       # viewer 不能看 private
        ("user-004", "coffee", "public", True),         # guest 可以看 public
        ("user-004", "coffee", "internal", False),      # guest 不能看 internal
        # 测试向下收敛：在 private 域内的 public 文档，实际有效级别应该是 private
        ("user-003", "content_safety", "public", False),  # 域=private，文档=public -> 收敛到 private，viewer 不能访问
        ("user-002", "content_safety", "public", True),   # editor 可以访问 private 级别
    ]

    all_pass = True
    for user_id, domain, doc_access, expected in test_cases:
        actual = pm.can_access_document(user_id, domain, doc_access)
        effective = pm.effective_doc_access_level(domain, doc_access)
        ok = actual == expected
        if not ok:
            all_pass = False
        tag = "[OK]" if ok else "[FAIL]"
        print(f"  {tag} {user_id:10s} domain={domain:18s} doc_access={doc_access:12s} -> effective={effective:12s}, access={actual}")

    tag = "[OK]" if all_pass else "[FAIL]"
    print(f"\n  {tag} 文档级别权限测试 {'通过' if all_pass else '未通过'}")
    return all_pass


def test_chunk_level_permission():
    print("\n" + "=" * 60)
    print("[4/6] 测试章节级别权限")
    print("=" * 60)

    pm = MockPermissionManager()

    test_cases = [
        # (user_id, domain, doc_access, chunk_access, expected)
        ("user-001", "coffee", "public", "confidential", True),    # admin 可以看 confidential 章节
        ("user-002", "coffee", "public", "confidential", False),   # editor 不能看 confidential 章节
        ("user-002", "coffee", "public", "private", True),         # editor 可以看 private 章节
        ("user-003", "coffee", "internal", "internal", True),      # viewer 可以看 internal 章节
        ("user-003", "coffee", "internal", "private", False),      # viewer 不能看 private 章节
        # 三级向下收敛：域=public, 文档=internal, 章节=public -> 收敛到 internal
        ("user-004", "coffee", "internal", "public", False),       # guest 不能看（章节被文档收敛到 internal）
        ("user-003", "coffee", "internal", "public", True),        # viewer 可以看
        # 三级收敛：域=private, 文档=public, 章节=public -> 收敛到 private
        ("user-003", "content_safety", "public", "public", False), # viewer 不能看（被域收敛到 private）
    ]

    all_pass = True
    for user_id, domain, doc_access, chunk_access, expected in test_cases:
        actual = pm.can_access_chunk(user_id, domain, doc_access, chunk_access)
        effective = pm.effective_chunk_access_level(domain, doc_access, chunk_access)
        ok = actual == expected
        if not ok:
            all_pass = False
        tag = "[OK]" if ok else "[FAIL]"
        print(f"  {tag} {user_id:10s} domain={domain:18s} doc={doc_access:10s} chunk={chunk_access:10s} -> eff={effective:10s}, access={actual}")

    tag = "[OK]" if all_pass else "[FAIL]"
    print(f"\n  {tag} 章节级别权限测试 {'通过' if all_pass else '未通过'}")
    return all_pass


def test_retrieval_permission_filter():
    print("\n" + "=" * 60)
    print("[5/6] 测试检索时权限过滤")
    print("=" * 60)

    service = KnowledgeService()
    project_id = "test-perm-project"

    # 清除旧文档
    old_docs = service.list_documents(project_id=project_id, limit=100)
    for doc in old_docs.get("documents", []):
        service.delete_document(doc["id"])

    # 导入3篇不同访问级别的文档（咖啡域，public域）
    docs = [
        ("公开咖啡指南", """# 公开咖啡指南
## 基础知识
咖啡是一种流行饮品。
## 饮用建议
每日适量饮用有益健康。""", "public"),
        ("内部咖啡配方", """# 内部咖啡配方
## 招牌拿铁
我们的招牌拿铁配方如下。
## 特调美式
特调美式的制作方法。""", "internal"),
        ("机密咖啡秘方", """# 机密咖啡秘方
## 核心配方
以下是核心机密配方。
## 独特工艺
独特的烘焙工艺。""", "confidential"),
    ]

    for title, content, access in docs:
        result = service.ingest_text(content, project_id=project_id, title=title, doc_access=access)
        print(f"  导入: {title} (access={access}) -> {result.get('status')}")

    print(f"\n  不同角色检索 '咖啡配方' 的结果数:")
    test_users = [
        ("user-001", "admin"),
        ("user-002", "editor"),
        ("user-003", "viewer"),
        ("user-004", "guest"),
    ]

    all_pass = True
    for user_id, role in test_users:
        chunks = service.retrieve("咖啡", project_id=project_id, top_k=20, user_id=user_id)
        doc_titles = list(set(c.get("doc_title", "") for c in chunks))
        print(f"    {user_id} ({role:8s}): {len(chunks)} chunks, {len(doc_titles)} docs - {doc_titles}")

    # 验证：admin 看到3篇，editor看到2篇，viewer看到2篇，guest看到1篇
    expected_counts = {"user-001": 3, "user-002": 2, "user-003": 2, "user-004": 1}
    print(f"\n  验证文档数:")
    for user_id, role in test_users:
        chunks = service.retrieve("咖啡", project_id=project_id, top_k=20, user_id=user_id)
        doc_titles = set(c.get("doc_title", "") for c in chunks)
        expected = expected_counts[user_id]
        actual = len(doc_titles)
        ok = actual == expected
        if not ok:
            all_pass = False
        tag = "[OK]" if ok else "[FAIL]"
        print(f"    {tag} {user_id} ({role}): {actual} docs (期望 {expected})")

    tag = "[OK]" if all_pass else "[FAIL]"
    print(f"\n  {tag} 检索权限过滤测试 {'通过' if all_pass else '未通过'}")
    return all_pass


def test_chunk_section_permission():
    print("\n" + "=" * 60)
    print("[6/6] 测试章节级精细权限")
    print("=" * 60)

    service = KnowledgeService()
    project_id = "test-chunk-perm"

    # 清除旧文档
    old_docs = service.list_documents(project_id=project_id, limit=100)
    for doc in old_docs.get("documents", []):
        service.delete_document(doc["id"])

    # 同一篇文档，不同章节不同权限
    doc_content = """# 员工手册
## 公司介绍
欢迎加入我们公司。
## 薪酬福利
员工薪酬福利如下。
## 核心机密
以下是公司核心机密信息。"""

    chunk_access_map = {
        "公司介绍": "public",
        "薪酬福利": "internal",
        "核心机密": "confidential",
    }

    result = service.ingest_text(doc_content, project_id=project_id,
                                  title="员工手册", doc_access="public",
                                  chunk_access_map=chunk_access_map)
    print(f"  导入: 员工手册 (doc_access=public)")
    print(f"  章节权限: {chunk_access_map}")
    print(f"  结果: {result.get('status')}")

    test_users = [
        ("user-001", "admin"),
        ("user-002", "editor"),
        ("user-003", "viewer"),
        ("user-004", "guest"),
    ]

    all_pass = True
    print(f"\n  不同角色检索 '员工手册' 的章节数:")
    for user_id, role in test_users:
        chunks = service.retrieve("员工", project_id=project_id, top_k=20, user_id=user_id)
        sections = list(set(c.get("section", "") for c in chunks))
        print(f"    {user_id} ({role:8s}): {len(chunks)} chunks, 章节: {sections}")

    # 验证
    expected_sections = {
        "user-001": {"公司介绍", "薪酬福利", "核心机密"},  # admin 全部
        "user-002": {"公司介绍", "薪酬福利"},            # editor 看不到 confidential
        "user-003": {"公司介绍", "薪酬福利"},            # viewer 看不到 confidential
        "user-004": {"公司介绍"},                         # guest 只看 public
    }
    print(f"\n  验证章节权限:")
    for user_id, role in test_users:
        chunks = service.retrieve("员工", project_id=project_id, top_k=20, user_id=user_id)
        sections = set(c.get("section", "") for c in chunks)
        expected = expected_sections[user_id]
        ok = sections == expected
        if not ok:
            all_pass = False
        tag = "[OK]" if ok else "[FAIL]"
        print(f"    {tag} {user_id} ({role}): {sections} (期望: {expected})")

    tag = "[OK]" if all_pass else "[FAIL]"
    print(f"\n  {tag} 章节精细权限测试 {'通过' if all_pass else '未通过'}")
    return all_pass


def main():
    print("=" * 60)
    print("三级权限模型测试（知识域 -> 文档 -> 章节）")
    print("=" * 60)

    results = []
    results.append(test_access_level_hierarchy())
    results.append(test_domain_level_permission())
    results.append(test_doc_level_permission())
    results.append(test_chunk_level_permission())
    results.append(test_retrieval_permission_filter())
    results.append(test_chunk_section_permission())

    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"测试总结: {passed}/{total} 通过")
    if passed == total:
        print("[OK] 三级权限模型全部测试通过!")
    else:
        print(f"[FAIL] {total - passed} 项测试未通过")
    print("=" * 60)


if __name__ == "__main__":
    main()
