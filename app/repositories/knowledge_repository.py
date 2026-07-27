"""KnowledgeRepository - 知识实体数据访问"""
from typing import Optional, List, Dict, Any

from .base_repository import BaseRepository
from app.core.config import settings


class KnowledgeRepository(BaseRepository):
    """知识实体相关数据操作"""

    VALID_ROLES = ["owner", "editor", "viewer"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from app.core.migrations import ensure_persistence_schema
        from app.knowledge.schema import ensure_schema

        ensure_persistence_schema(self._get_connection())
        ensure_schema(self)
    ROLE_PERMISSIONS = {
        "owner": ["read", "write", "delete", "invite", "compile", "upload"],
        "editor": ["read", "write", "compile", "upload"],
        "viewer": ["read"],
    }

    def index_knowledge(self, project_id: str, asset_id: str, entries: List[Dict]):
        """索引知识条目"""
        rows = []
        for entry in entries:
            rows.append(
                (
                    self._generate_id(),
                    project_id,
                    asset_id,
                    entry["key"],
                    self._json_dumps(entry["value"]),
                    entry.get("category", ""),
                )
            )
        if rows:
            self._executemany(
                "INSERT INTO knowledge_index VALUES (?,?,?,?,?,?)", rows
            )
            self._commit()

    def search_knowledge(
        self,
        query: str = "",
        category: Optional[str] = None,
        project_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """搜索知识"""
        query_sql = "SELECT k.*, p.name as project_name FROM knowledge_index k LEFT JOIN projects p ON k.project_id=p.id WHERE 1=1"
        params = []
        if query:
            query_sql += " AND (k.key LIKE ? OR k.value LIKE ?)"
            params.extend([f"%{query}%", f"%{query}%"])
        if category:
            query_sql += " AND k.category=?"
            params.append(category)
        if project_id:
            query_sql += " AND k.project_id=?"
            params.append(project_id)
        query_sql += f" ORDER BY k.key LIMIT {limit}"
        return self._rows_to_list(self._execute(query_sql, tuple(params)))

    def get_knowledge_stats(self) -> Dict[str, Any]:
        """获取知识统计"""
        total = self._execute("SELECT COUNT(*) FROM knowledge_index").fetchone()[0]
        by_cat = {
            r["category"]: r["cnt"]
            for r in self._execute(
                "SELECT category, COUNT(*) as cnt FROM knowledge_index GROUP BY category"
            ).fetchall()
        }
        pc = self._execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        ac = self._execute("SELECT COUNT(*) FROM assets").fetchone()[0]
        return {
            "total_entries": total,
            "by_category": by_cat,
            "projects": pc,
            "assets": ac,
        }

    def save_knowledge_entity(
        self,
        entity_id: str,
        project_id: str,
        category: str,
        title: str,
        description: str = "",
        data: Optional[Dict] = None,
        domain: str = "general",
        tags: Optional[List[str]] = None,
        status: str = "active",
    ) -> Dict[str, Any]:
        """创建或更新知识实体"""
        now = self._now()
        data_json = self._json_dumps(data or {})
        tags_json = self._json_dumps(tags or [])
        existing = self._execute(
            "SELECT id FROM knowledge_entities WHERE id=?", (entity_id,)
        ).fetchone()
        if existing:
            old = self._execute(
                "SELECT data, version_number FROM knowledge_entities WHERE id=?",
                (entity_id,),
            ).fetchone()
            if old:
                new_ver = (old["version_number"] or 0) + 1
                self._execute(
                    "INSERT INTO knowledge_versions (id,entity_id,version_number,data,created_at) VALUES (?,?,?,?,?)",
                    (self._generate_id(), entity_id, new_ver, old["data"], now),
                )
            self._execute(
                "UPDATE knowledge_entities SET name=?,entity_type=?,attributes=?,title=?,description=?,data=?,status=?,domain=?,tags=?,updated_at=? WHERE id=?",
                (title, category, data_json, title, description, data_json, status, domain, tags_json, now, entity_id),
            )
        else:
            self._execute(
                "INSERT INTO knowledge_entities (id,name,entity_type,description,attributes,project_id,category,title,version_number,data,status,domain,tags,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (entity_id, title, category, description, data_json, project_id, category, title, 1, data_json, status, domain, tags_json, now, now),
            )
        self._commit()
        return self.get_knowledge_entity(entity_id)

    def get_knowledge_entity(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """获取知识实体"""
        row = self._execute(
            "SELECT * FROM knowledge_entities WHERE id=?", (entity_id,)
        ).fetchone()
        if not row:
            return None
        d = self._row_to_dict(row)
        d["data"] = self._json_loads(d.get("data", "{}"))
        d["tags"] = self._json_loads(d.get("tags", "[]"))
        return d

    def list_knowledge_entities(
        self,
        project_id: str = "",
        category: Optional[str] = None,
        domain: Optional[str] = None,
        status: str = "active",
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """列出知识实体"""
        query = "SELECT * FROM knowledge_entities WHERE 1=1"
        params = []
        if project_id:
            query += " AND project_id=?"
            params.append(project_id)
        if category:
            query += " AND category=?"
            params.append(category)
        if domain:
            query += " AND domain=?"
            params.append(domain)
        if status:
            query += " AND status=?"
            params.append(status)
        query += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = self._execute(query, tuple(params)).fetchall()
        result = []
        for row in rows:
            d = self._row_to_dict(row)
            d["data"] = self._json_loads(d.get("data", "{}"))
            d["tags"] = self._json_loads(d.get("tags", "[]"))
            result.append(d)
        return result

    def delete_knowledge_entity(self, entity_id: str) -> bool:
        """删除知识实体（软删除）"""
        self._execute(
            "UPDATE knowledge_entities SET status='archived',updated_at=? WHERE id=?",
            (self._now(), entity_id),
        )
        self._commit()
        return True

    def add_member(self, project_id: str, user_id: str, role: str = "viewer") -> Dict[str, Any]:
        """添加项目成员"""
        if role not in self.VALID_ROLES:
            role = "viewer"
        mid = self._generate_id()
        try:
            self._execute(
                "INSERT INTO project_members (id,project_id,user_id,role,joined_at) VALUES (?,?,?,?,?)",
                (mid, project_id, user_id, role, self._now()),
            )
            self._commit()
        except Exception:
            self._execute(
                "UPDATE project_members SET role=?,joined_at=? WHERE project_id=? AND user_id=?",
                (role, self._now(), project_id, user_id),
            )
            self._commit()
        return self.get_member(project_id, user_id)

    def get_member(self, project_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """获取成员"""
        row = self._execute(
            "SELECT * FROM project_members WHERE project_id=? AND user_id=?",
            (project_id, user_id),
        ).fetchone()
        return self._row_to_dict(row)

    def check_permission(self, project_id: str, user_id: str, action: str) -> bool:
        """检查权限"""
        member = self.get_member(project_id, user_id)
        if not member:
            return False
        allowed = self.ROLE_PERMISSIONS.get(member["role"], [])
        return action in allowed

    # ---- 生产级加固：项目 / 项目密钥 / benchmark ----
    def create_project(self, project_id: str, name: str, metadata: dict = None,
                       rerank_config: dict = None, *, tenant_id: str = "") -> dict:
        """Upsert (INSERT OR REPLACE) a project, preserving the original created_at."""
        tenant = (tenant_id or settings.DEFAULT_TENANT_ID).strip()
        if not tenant:
            raise ValueError("tenant_id is required")
        existing = self.get_project(project_id)
        if existing and existing.get("tenant_id") != tenant:
            raise ValueError("project ID is already bound to another tenant")
        created_at = existing["created_at"] if existing else self._now()
        self._execute(
            "INSERT INTO knowledge_projects (id,tenant_id,name,created_at,metadata,rerank_config) "
            "VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
            "name=excluded.name, metadata=excluded.metadata, rerank_config=excluded.rerank_config",
            (project_id, tenant, name, created_at, self._json_dumps(metadata or {}),
             self._json_dumps(rerank_config or {})),
        )
        self._commit()
        return self.get_project(project_id)

    def get_project(self, project_id: str) -> Optional[dict]:
        row = self._execute(
            "SELECT * FROM knowledge_projects WHERE id=?", (project_id,)).fetchone()
        if not row:
            return None
        d = self._row_to_dict(row)
        d["metadata"] = self._json_loads(d.get("metadata", "{}"))
        d["rerank_config"] = self._json_loads(d.get("rerank_config", "{}"))
        return d

    def list_projects(self) -> List[dict]:
        rows = self._execute("SELECT * FROM knowledge_projects ORDER BY created_at DESC").fetchall()
        result = []
        for r in rows:
            d = self._row_to_dict(r)
            d["metadata"] = self._json_loads(d.get("metadata", "{}"))
            d["rerank_config"] = self._json_loads(d.get("rerank_config", "{}"))
            result.append(d)
        return result

    def get_project_for_tenant(self, project_id: str, tenant_id: str) -> Optional[dict]:
        tenant = tenant_id.strip()
        if not tenant:
            return None
        row = self._execute(
            "SELECT * FROM knowledge_projects WHERE id=? AND tenant_id=?",
            (project_id, tenant),
        ).fetchone()
        if not row:
            return None
        value = self._row_to_dict(row)
        value["metadata"] = self._json_loads(value.get("metadata", "{}"))
        value["rerank_config"] = self._json_loads(value.get("rerank_config", "{}"))
        return value

    def list_projects_for_tenant(self, tenant_id: str) -> List[dict]:
        tenant = tenant_id.strip()
        if not tenant:
            return []
        rows = self._execute(
            "SELECT * FROM knowledge_projects WHERE tenant_id=? ORDER BY created_at DESC, id DESC",
            (tenant,),
        ).fetchall()
        result = []
        for row in rows:
            value = self._row_to_dict(row)
            value["metadata"] = self._json_loads(value.get("metadata", "{}"))
            value["rerank_config"] = self._json_loads(value.get("rerank_config", "{}"))
            result.append(value)
        return result

    def create_project_key(self, key_hash: str, project_id: str, role: str,
                           label: str = "") -> None:
        self._execute(
            "INSERT INTO project_keys (key_hash,project_id,role,label,created_at) "
            "VALUES (?,?,?,?,?) ON CONFLICT(key_hash) DO UPDATE SET "
            "project_id=excluded.project_id, role=excluded.role, label=excluded.label, "
            "created_at=excluded.created_at",
            (key_hash, project_id, role, label, self._now()))
        self._commit()

    def get_project_key_by_hash(self, key_hash: str) -> Optional[tuple]:
        row = self._execute(
            "SELECT role, project_id FROM project_keys WHERE key_hash=?",
            (key_hash,)).fetchone()
        if not row:
            return None
        return (row["role"], row["project_id"])

    def add_benchmark(self, project_id: Optional[str], query: str,
                      expected_chunk_ids: List[str], notes: str = "") -> None:
        self._execute(
            "INSERT INTO knowledge_benchmarks (project_id,query,expected_chunk_ids,notes,created_at) "
            "VALUES (?,?,?,?,?)",
            (project_id, query, self._json_dumps(expected_chunk_ids or []), notes, self._now()))
        self._commit()

    def list_benchmarks(self, project_id: Optional[str] = None) -> List[dict]:
        if project_id:
            rows = self._execute(
                "SELECT * FROM knowledge_benchmarks WHERE project_id=? ORDER BY id",
                (project_id,)).fetchall()
        else:
            rows = self._execute(
                "SELECT * FROM knowledge_benchmarks ORDER BY id").fetchall()
        out = []
        for r in rows:
            d = self._row_to_dict(r)
            d["expected_chunk_ids"] = self._json_loads(d.get("expected_chunk_ids", "[]"))
            out.append(d)
        return out
