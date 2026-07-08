"""ProjectRepository - 项目数据访问"""
from typing import Optional, List, Dict, Any

from .base_repository import BaseRepository


class ProjectRepository(BaseRepository):
    """项目相关数据操作"""

    def create_project(
        self,
        name: str,
        description: str = "",
        domain: str = "general",
        metadata: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """创建项目"""
        pid = self._generate_id()
        now = self._now()
        self._execute(
            "INSERT INTO projects VALUES (?,?,?,?,?,?,?,?)",
            (
                pid,
                name,
                description,
                domain,
                "active",
                now,
                now,
                self._json_dumps(metadata or {}),
            ),
        )
        self._commit()
        return self.get_project(pid)

    def get_project(self, pid: str) -> Optional[Dict[str, Any]]:
        """获取项目"""
        row = self._execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        return self._row_to_dict(row) if row else None

    def list_projects(
        self, status: Optional[str] = None, domain: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """列出项目"""
        query = "SELECT * FROM projects WHERE 1=1"
        params = []
        if status:
            query += " AND status=?"
            params.append(status)
        if domain:
            query += " AND domain=?"
            params.append(domain)
        query += " ORDER BY updated_at DESC"
        return self._rows_to_list(self._execute(query, tuple(params)))

    def update_project(self, pid: str, **fields) -> Optional[Dict[str, Any]]:
        """更新项目"""
        allowed = {"name", "description", "domain", "status", "metadata"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return self.get_project(pid)
        if "metadata" in updates and isinstance(updates["metadata"], dict):
            updates["metadata"] = self._json_dumps(updates["metadata"])
        updates["updated_at"] = self._now()
        sets = ", ".join(f"{k}=?" for k in updates)
        self._execute(
            f"UPDATE projects SET {sets} WHERE id=?",
            list(updates.values()) + [pid],
        )
        self._commit()
        return self.get_project(pid)

    def delete_project(self, pid: str) -> bool:
        """删除项目"""
        for table in ["knowledge_index", "assets", "projects"]:
            id_col = "project_id" if table != "projects" else "id"
            self._execute(f"DELETE FROM {table} WHERE {id_col}=?", (pid,))
        self._commit()
        return True

    def save_asset(
        self,
        project_id: str,
        asset_type: str,
        data: Dict,
        label: str = "",
        source_prd: str = "",
        version: int = 1,
    ) -> Dict[str, Any]:
        """保存资产"""
        aid = self._generate_id()
        self._execute(
            "INSERT INTO assets VALUES (?,?,?,?,?,?,?,?)",
            (
                aid,
                project_id,
                asset_type,
                label,
                version,
                self._json_dumps(data),
                source_prd,
                self._now(),
            ),
        )
        self._commit()
        return self.get_asset(aid)

    def get_asset(self, aid: str) -> Optional[Dict[str, Any]]:
        """获取资产"""
        row = self._execute("SELECT * FROM assets WHERE id=?", (aid,)).fetchone()
        return self._row_to_dict(row)

    def list_assets(self, project_id: str, asset_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出项目资产"""
        query = "SELECT * FROM assets WHERE project_id=?"
        params = [project_id]
        if asset_type:
            query += " AND asset_type=?"
            params.append(asset_type)
        query += " ORDER BY created_at DESC"
        return self._rows_to_list(self._execute(query, tuple(params)))

    def save_document(
        self,
        project_id: str,
        doc_type: str,
        filename: str,
        content: str,
        original_name: str = "",
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """保存文档"""
        did = self._generate_id()
        self._execute(
            "INSERT INTO documents (id,project_id,doc_type,filename,original_name,content,size_bytes,status,tags,uploaded_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                did,
                project_id,
                doc_type,
                filename,
                original_name or filename,
                content,
                len(content.encode("utf-8")),
                "active",
                self._json_dumps(tags or []),
                self._now(),
            ),
        )
        self._commit()
        return self.get_document(did)

    def get_document(self, did: str) -> Optional[Dict[str, Any]]:
        """获取文档"""
        row = self._execute("SELECT * FROM documents WHERE id=?", (did,)).fetchone()
        return self._row_to_dict(row)

    def list_documents(
        self, project_id: str, doc_type: Optional[str] = None, status: str = "active"
    ) -> List[Dict[str, Any]]:
        """列出文档"""
        query = "SELECT id,project_id,doc_type,filename,original_name,size_bytes,status,tags,uploaded_at FROM documents WHERE project_id=? AND status=?"
        params = [project_id, status]
        if doc_type:
            query += " AND doc_type=?"
            params.append(doc_type)
        query += " ORDER BY uploaded_at DESC"
        return self._rows_to_list(self._execute(query, tuple(params)))

    def delete_document(self, did: str) -> bool:
        """删除文档（软删除）"""
        self._execute("UPDATE documents SET status='deleted' WHERE id=?", (did,))
        self._commit()
        return True