"""GraphRepository - 图数据访问"""
from typing import Optional, List, Dict, Any

from .base_repository import BaseRepository


class GraphRepository(BaseRepository):
    """图数据相关操作"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from app.core.migrations import ensure_persistence_schema

        ensure_persistence_schema(self._get_connection())

    def save_graph_snapshot(
        self,
        graph_id: str,
        name: str,
        data: Dict,
        domain: str = "general",
        project_id: str = "",
        node_count: int = 0,
        edge_count: int = 0,
    ) -> Dict[str, Any]:
        """保存图快照"""
        now = self._now()
        data_json = self._json_dumps(data)
        existing = self._execute(
            "SELECT id FROM graph_snapshots WHERE id=?", (graph_id,)
        ).fetchone()
        if existing:
            self._execute(
                "UPDATE graph_snapshots SET name=?,data=?,node_count=?,edge_count=?,domain=?,project_id=? WHERE id=?",
                (name, data_json, node_count, edge_count, domain, project_id, graph_id),
            )
        else:
            self._execute(
                "INSERT INTO graph_snapshots (id,name,domain,project_id,snapshot_type,data,node_count,edge_count,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (graph_id, name, domain, project_id, "snapshot", data_json, node_count, edge_count, now),
            )
        self._commit()
        return self.get_graph_snapshot(graph_id)

    def get_graph_snapshot(self, graph_id: str) -> Optional[Dict[str, Any]]:
        """获取图快照"""
        row = self._execute(
            "SELECT * FROM graph_snapshots WHERE id=?", (graph_id,)
        ).fetchone()
        if not row:
            return None
        d = self._row_to_dict(row)
        d["data"] = self._json_loads(d.get("data", "{}"))
        return d

    def list_graph_snapshots(
        self, project_id: str = "", domain: Optional[str] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """列出图快照"""
        query = "SELECT * FROM graph_snapshots WHERE 1=1"
        params = []
        if project_id:
            query += " AND project_id=?"
            params.append(project_id)
        if domain:
            query += " AND domain=?"
            params.append(domain)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        return self._rows_to_list(self._execute(query, tuple(params)))

    def delete_graph_snapshot(self, graph_id: str) -> bool:
        """删除图快照"""
        self._execute("DELETE FROM graph_snapshots WHERE id=?", (graph_id,))
        self._commit()
        return True

    def save_graph_nodes(self, graph_id: str, nodes: List[Dict]):
        """保存图节点"""
        now = self._now()
        self._execute("DELETE FROM graph_nodes_persistent WHERE graph_id=?", (graph_id,))
        rows = []
        for node in nodes:
            nid = node.get("node_id", node.get("id", self._generate_id()))
            ntype = node.get("node_type", node.get("type", "process"))
            label = node.get("label", node.get("title", ""))
            desc = node.get("description", "")
            owner = node.get("owner", "")
            domain = node.get("domain", "general")
            pid = node.get("project_id", "")
            eref = node.get("entity_ref", "")
            props = self._json_dumps(node.get("properties", node.get("data", {})))
            weight = node.get("weight", 1.0)
            status = node.get("status", "active")
            rows.append(
                (nid, graph_id, ntype, label, desc, owner, domain, pid, eref, props, weight, status, now)
            )
        if rows:
            self._executemany(
                "INSERT INTO graph_nodes_persistent (id,graph_id,node_type,label,description,owner,domain,project_id,entity_ref,properties,weight,status,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                rows,
            )
        self._commit()

    def get_graph_nodes(self, graph_id: str) -> List[Dict[str, Any]]:
        """获取图节点"""
        cursor = self._execute(
            "SELECT * FROM graph_nodes_persistent WHERE graph_id=? ORDER BY node_type, label",
            (graph_id,),
        )
        return self._rows_to_list(cursor)

    def save_graph_edges(self, graph_id: str, edges: List[Dict]):
        """保存图边"""
        now = self._now()
        self._execute("DELETE FROM graph_edges_persistent WHERE graph_id=?", (graph_id,))
        rows = []
        for edge in edges:
            eid = edge.get("edge_id", edge.get("id", self._generate_id()))
            src = edge.get("source_id", edge.get("source", edge.get("from", "")))
            tgt = edge.get("target_id", edge.get("target", edge.get("to", "")))
            etype = edge.get("edge_type", edge.get("type", "depends_on"))
            label = edge.get("label", "")
            weight = edge.get("weight", 1.0)
            props = self._json_dumps(edge.get("properties", {}))
            rows.append((eid, graph_id, src, tgt, etype, label, weight, props, now))
        if rows:
            self._executemany(
                "INSERT INTO graph_edges_persistent (id,graph_id,source_id,target_id,edge_type,label,weight,properties,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                rows,
            )
        self._commit()

    def get_graph_edges(
        self, graph_id: str, edge_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """获取图边"""
        if edge_type:
            cursor = self._execute(
                "SELECT * FROM graph_edges_persistent WHERE graph_id=? AND edge_type=? ORDER BY created_at",
                (graph_id, edge_type),
            )
        else:
            cursor = self._execute(
                "SELECT * FROM graph_edges_persistent WHERE graph_id=? ORDER BY created_at",
                (graph_id,),
            )
        return self._rows_to_list(cursor)
