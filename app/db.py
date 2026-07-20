"""数据库访问模块 - 兼容层

注意：此模块已被废弃，新代码应使用Repository模式：
- app.repositories.ProjectRepository
- app.repositories.KnowledgeRepository
- app.repositories.GraphRepository

此模块仅作为兼容层保留，供现有代码逐步迁移使用。
"""
import json
import uuid
import time
from app.core.database import get_database_backend

_connection = None


def get_db():
    """获取数据库连接（兼容旧代码）"""
    global _connection
    if _connection is None:
        _connection = get_database_backend()
        _connection.connect()
    return _connection


def init_db():
    """初始化数据库（兼容旧代码，使用新的数据库抽象层）"""
    from app.core.database import init_database
    init_database()


def _row(r): return dict(r) if r else {}
def _row_to_dict(r): return dict(r) if r else {}


def create_project(name, description="", domain="general", metadata=None):
    """创建项目（委托给ProjectRepository）"""
    from app.repositories import ProjectRepository
    return ProjectRepository().create_project(name, description, domain, metadata)


def get_project(pid):
    """获取项目（委托给ProjectRepository）"""
    from app.repositories import ProjectRepository
    return ProjectRepository().get_project(pid)


def list_projects(status=None, domain=None):
    """列出项目（委托给ProjectRepository）"""
    from app.repositories import ProjectRepository
    return ProjectRepository().list_projects(status, domain)


def update_project(pid, **fields):
    """更新项目（委托给ProjectRepository）"""
    from app.repositories import ProjectRepository
    return ProjectRepository().update_project(pid, **fields)


def delete_project(pid):
    """删除项目（委托给ProjectRepository）"""
    from app.repositories import ProjectRepository
    return ProjectRepository().delete_project(pid)


def save_asset(project_id, asset_type, data, label="", source_prd="", version=1):
    """保存资产（委托给ProjectRepository）"""
    from app.repositories import ProjectRepository
    return ProjectRepository().save_asset(project_id, asset_type, data, label, source_prd, version)


def get_asset(aid):
    """获取资产（委托给ProjectRepository）"""
    from app.repositories import ProjectRepository
    return ProjectRepository().get_asset(aid)


def list_assets(project_id, asset_type=None):
    """列出资产（委托给ProjectRepository）"""
    from app.repositories import ProjectRepository
    return ProjectRepository().list_assets(project_id, asset_type)


def index_knowledge(project_id, asset_id, entries):
    """索引知识（委托给KnowledgeRepository）"""
    from app.repositories import KnowledgeRepository
    KnowledgeRepository().index_knowledge(project_id, asset_id, entries)


def search_knowledge(query="", category=None, project_id=None, limit=20):
    """搜索知识（委托给KnowledgeRepository）"""
    from app.repositories import KnowledgeRepository
    return KnowledgeRepository().search_knowledge(query, category, project_id, limit)


def get_knowledge_stats():
    """获取知识统计（委托给KnowledgeRepository）"""
    from app.repositories import KnowledgeRepository
    return KnowledgeRepository().get_knowledge_stats()


def save_document(project_id, doc_type, filename, content, original_name="", tags=None, user_id="system"):
    """保存文档（委托给ProjectRepository）"""
    from app.repositories import ProjectRepository
    return ProjectRepository().save_document(project_id, doc_type, filename, content, original_name, tags)


def get_document(did):
    """获取文档（委托给ProjectRepository）"""
    from app.repositories import ProjectRepository
    return ProjectRepository().get_document(did)


def list_documents(project_id, doc_type=None, status="active"):
    """列出文档（委托给ProjectRepository）"""
    from app.repositories import ProjectRepository
    return ProjectRepository().list_documents(project_id, doc_type, status)


def get_document_content(did):
    """获取文档内容（委托给ProjectRepository）"""
    from app.repositories import ProjectRepository
    doc = ProjectRepository().get_document(did)
    return doc["content"] if doc else None


def delete_document(did):
    """删除文档（委托给ProjectRepository）"""
    from app.repositories import ProjectRepository
    return ProjectRepository().delete_document(did)


def get_document_types():
    """获取文档类型"""
    return ["prd", "meeting_notes", "process_doc", "bid_material", "other"]


def add_member(project_id, user_id, role="viewer"):
    """添加成员（委托给KnowledgeRepository）"""
    from app.repositories import KnowledgeRepository
    return KnowledgeRepository().add_member(project_id, user_id, role)


def get_member(project_id, user_id):
    """获取成员（委托给KnowledgeRepository）"""
    from app.repositories import KnowledgeRepository
    return KnowledgeRepository().get_member(project_id, user_id)


def list_members(project_id):
    """列出成员（委托给KnowledgeRepository）"""
    db = get_db()
    return [_row_to_dict(r) for r in db.execute("SELECT * FROM project_members WHERE project_id=?", (project_id,)).fetchall()]


def remove_member(project_id, user_id):
    """移除成员"""
    get_db().execute("DELETE FROM project_members WHERE project_id=? AND user_id=?", (project_id, user_id))
    get_db().commit()
    return True


def check_permission(project_id, user_id, action):
    """检查权限（委托给KnowledgeRepository）"""
    from app.repositories import KnowledgeRepository
    return KnowledgeRepository().check_permission(project_id, user_id, action)


def get_user_projects(user_id):
    """获取用户项目"""
    db = get_db()
    rows = db.execute(
        "SELECT p.*, pm.role as user_role FROM projects p JOIN project_members pm ON p.id=pm.project_id WHERE pm.user_id=? AND p.status='active' ORDER BY p.updated_at DESC",
        (user_id,)).fetchall()
    return [_row_to_dict(r) for r in rows]


def _log_activity(project_id, user_id, action, detail=""):
    """记录活动"""
    db = get_db()
    db.execute("INSERT INTO activity_log (id,project_id,user_id,action,detail,created_at) VALUES (?,?,?,?,?,?)",
               (str(uuid.uuid4())[:12], project_id, user_id, action, detail, time.strftime("%Y-%m-%dT%H:%M:%S")))
    db.commit()


def get_activity(project_id='', limit=50):
    """获取活动记录"""
    db = get_db()
    if project_id:
        rows = db.execute("SELECT * FROM activity_log WHERE project_id=? ORDER BY created_at DESC LIMIT ?", (project_id, limit)).fetchall()
    else:
        rows = db.execute("SELECT * FROM activity_log ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [_row_to_dict(r) for r in rows]


def save_knowledge_entity(entity_id, project_id, category, title, description="", data=None, domain="general", tags=None, status="active"):
    """保存知识实体（委托给KnowledgeRepository）"""
    from app.repositories import KnowledgeRepository
    return KnowledgeRepository().save_knowledge_entity(entity_id, project_id, category, title, description, data, domain, tags, status)


def get_knowledge_entity(entity_id):
    """获取知识实体（委托给KnowledgeRepository）"""
    from app.repositories import KnowledgeRepository
    return KnowledgeRepository().get_knowledge_entity(entity_id)


def list_knowledge_entities(project_id='', category=None, domain=None, status="active", limit=100, offset=0):
    """列出知识实体（委托给KnowledgeRepository）"""
    from app.repositories import KnowledgeRepository
    return KnowledgeRepository().list_knowledge_entities(project_id, category, domain, status, limit, offset)


def delete_knowledge_entity(entity_id):
    """删除知识实体（委托给KnowledgeRepository）"""
    from app.repositories import KnowledgeRepository
    return KnowledgeRepository().delete_knowledge_entity(entity_id)


def get_knowledge_statistics():
    """获取知识统计"""
    from app.repositories import KnowledgeRepository
    return KnowledgeRepository().get_knowledge_stats()


def create_reference(source_entity_id, target_entity_id, relation, weight=1.0):
    """创建引用"""
    db = get_db()
    ref_id = str(uuid.uuid4())[:12]
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    db.execute("INSERT INTO knowledge_references (id,source_entity_id,target_entity_id,relation,weight,created_at) VALUES (?,?,?,?,?,?)",
               (ref_id, source_entity_id, target_entity_id, relation, weight, now))
    db.commit()
    return {"id": ref_id, "source_entity_id": source_entity_id, "target_entity_id": target_entity_id,
            "relation": relation, "weight": weight, "created_at": now}


def get_references(entity_id, direction="both"):
    """获取引用"""
    db = get_db()
    results = []
    if direction in ("outgoing", "both"):
        rows = db.execute("SELECT * FROM knowledge_references WHERE source_entity_id=?", (entity_id,)).fetchall()
        results.extend([_row_to_dict(r) for r in rows])
    if direction in ("incoming", "both"):
        rows = db.execute("SELECT * FROM knowledge_references WHERE target_entity_id=?", (entity_id,)).fetchall()
        results.extend([_row_to_dict(r) for r in rows])
    return results


def delete_reference(ref_id):
    """删除引用"""
    get_db().execute("DELETE FROM knowledge_references WHERE id=?", (ref_id,))
    get_db().commit()
    return True


def get_entity_graph(entity_id, depth=2):
    """获取实体图"""
    visited = set()
    nodes = []; edges = []
    queue = [(entity_id, 0)]
    while queue:
        eid, d = queue.pop(0)
        if eid in visited or d > depth:
            continue
        visited.add(eid)
        entity = get_knowledge_entity(eid)
        if entity:
            nodes.append({"id": eid, "title": entity.get("title", ""),
                         "category": entity.get("category", ""), "depth": d})
        refs = get_references(eid, direction="both")
        for ref in refs:
            if d < depth:
                neighbor = ref["target_entity_id"] if ref["source_entity_id"] == eid else ref["source_entity_id"]
                edges.append({"from": ref["source_entity_id"], "to": ref["target_entity_id"],
                             "relation": ref["relation"], "weight": ref.get("weight", 1.0)})
                if neighbor not in visited:
                    queue.append((neighbor, d + 1))
    return {"nodes": nodes, "edges": edges, "root_entity_id": entity_id, "depth": depth}


def get_versions(entity_id, limit=20):
    """获取版本历史"""
    rows = get_db().execute(
        "SELECT * FROM knowledge_versions WHERE entity_id=? ORDER BY version_number DESC LIMIT ?",
        (entity_id, limit)).fetchall()
    results = []
    for row in rows:
        d = _row_to_dict(row)
        d["data"] = json.loads(d.get("data", "{}")) if isinstance(d.get("data"), str) else d.get("data", {})
        results.append(d)
    return results


def rollback_entity(entity_id, target_version):
    """回滚实体"""
    db = get_db()
    ver_row = db.execute(
        "SELECT * FROM knowledge_versions WHERE entity_id=? AND version_number=?",
        (entity_id, target_version)).fetchone()
    if not ver_row:
        return None
    entity = db.execute("SELECT * FROM knowledge_entities WHERE id=?", (entity_id,)).fetchone()
    if not entity:
        return None
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    current_ver = (entity["version_number"] or 0) + 1
    db.execute("INSERT INTO knowledge_versions (id,entity_id,version_number,data,change_summary,author,created_at) VALUES (?,?,?,?,?,?,?)",
               (str(uuid.uuid4())[:12], entity_id, current_ver, entity["data"],
                f"Snapshot before rollback to v{target_version}", "system", now))
    old_data = json.loads(ver_row["data"]) if isinstance(ver_row["data"], str) else ver_row["data"]
    db.execute("UPDATE knowledge_entities SET data=?,updated_at=? WHERE id=?",
               (json.dumps(old_data, ensure_ascii=False), now, entity_id))
    db.commit()
    return get_knowledge_entity(entity_id)


def save_graph_snapshot(graph_id, name, data, domain="general", project_id='', node_count=0, edge_count=0):
    """保存图快照（委托给GraphRepository）"""
    from app.repositories import GraphRepository
    return GraphRepository().save_graph_snapshot(graph_id, name, data, domain, project_id, node_count, edge_count)


def get_graph_snapshot(graph_id):
    """获取图快照（委托给GraphRepository）"""
    from app.repositories import GraphRepository
    return GraphRepository().get_graph_snapshot(graph_id)


def list_graph_snapshots(project_id='', domain=None, limit=50):
    """列出图快照（委托给GraphRepository）"""
    from app.repositories import GraphRepository
    return GraphRepository().list_graph_snapshots(project_id, domain, limit)


def delete_graph_snapshot(graph_id):
    """删除图快照（委托给GraphRepository）"""
    from app.repositories import GraphRepository
    return GraphRepository().delete_graph_snapshot(graph_id)


def save_graph_nodes(graph_id, nodes):
    """保存图节点（委托给GraphRepository）"""
    from app.repositories import GraphRepository
    GraphRepository().save_graph_nodes(graph_id, nodes)


def get_graph_nodes(graph_id):
    """获取图节点（委托给GraphRepository）"""
    from app.repositories import GraphRepository
    return GraphRepository().get_graph_nodes(graph_id)


def get_graph_node(node_id):
    """获取单个图节点"""
    row = get_db().execute("SELECT * FROM graph_nodes_persistent WHERE id=?", (node_id,)).fetchone()
    return _row_to_dict(row) if row else None


def save_graph_edges(graph_id, edges):
    """保存图边（委托给GraphRepository）"""
    from app.repositories import GraphRepository
    GraphRepository().save_graph_edges(graph_id, edges)


def get_graph_edges(graph_id, edge_type=None):
    """获取图边（委托给GraphRepository）"""
    from app.repositories import GraphRepository
    return GraphRepository().get_graph_edges(graph_id, edge_type)


def get_graph_neighbors(node_id, graph_id=None):
    """获取图邻居"""
    db = get_db()
    if graph_id:
        outgoing = db.execute(
            "SELECT target_id, edge_type, label FROM graph_edges_persistent WHERE graph_id=? AND source_id=?",
            (graph_id, node_id)).fetchall()
        incoming = db.execute(
            "SELECT source_id, edge_type, label FROM graph_edges_persistent WHERE graph_id=? AND target_id=?",
            (graph_id, node_id)).fetchall()
    else:
        outgoing = db.execute(
            "SELECT target_id, edge_type, label FROM graph_edges_persistent WHERE source_id=?",
            (node_id,)).fetchall()
        incoming = db.execute(
            "SELECT source_id, edge_type, label FROM graph_edges_persistent WHERE target_id=?",
            (node_id,)).fetchall()
    return {
        "node_id": node_id,
        "outgoing": [_row_to_dict(r) for r in outgoing],
        "incoming": [_row_to_dict(r) for r in incoming],
        "degree": len(outgoing) + len(incoming),
    }
