"""
Repository层单元测试

测试覆盖：
- ProjectRepository: 创建、获取、更新、删除项目，保存资产和文档
- KnowledgeRepository: 索引知识、搜索知识、保存知识实体、权限检查
- GraphRepository: 保存图快照、节点、边
- CacheService: 缓存设置、获取、过期、删除等操作
"""
import pytest
from app.core.cache_service import MemoryCache


class TestProjectRepository:
    """ProjectRepository单元测试"""

    def test_create_project(self, test_project_repository):
        """测试创建项目"""
        project = test_project_repository.create_project(
            name="测试项目",
            description="测试描述",
            domain="test",
            metadata={"key": "value"},
        )
        
        assert project is not None
        assert project["name"] == "测试项目"
        assert project["description"] == "测试描述"
        assert project["domain"] == "test"
        assert project["status"] == "active"
        assert project["id"] is not None

    def test_get_project(self, test_project_repository, temp_project):
        """测试获取项目"""
        project = test_project_repository.get_project(temp_project["id"])
        
        assert project is not None
        assert project["id"] == temp_project["id"]
        assert project["name"] == "测试项目"

    def test_get_nonexistent_project(self, test_project_repository):
        """测试获取不存在的项目"""
        project = test_project_repository.get_project("nonexistent-id")
        assert project is None

    def test_list_projects(self, test_project_repository):
        """测试列出项目"""
        test_project_repository.create_project(name="项目1", domain="domain1")
        test_project_repository.create_project(name="项目2", domain="domain2")
        
        projects = test_project_repository.list_projects()
        
        assert len(projects) >= 2

    def test_update_project(self, test_project_repository, temp_project):
        """测试更新项目"""
        updated = test_project_repository.update_project(
            temp_project["id"],
            name="更新后的项目",
            description="更新后的描述",
        )
        
        assert updated is not None
        assert updated["name"] == "更新后的项目"
        assert updated["description"] == "更新后的描述"

    def test_delete_project(self, test_project_repository, temp_project):
        """测试删除项目"""
        pid = temp_project["id"]
        result = test_project_repository.delete_project(pid)
        
        assert result is True
        assert test_project_repository.get_project(pid) is None

    def test_save_asset(self, test_project_repository, temp_project):
        """测试保存资产"""
        asset = test_project_repository.save_asset(
            project_id=temp_project["id"],
            asset_type="sop",
            data={"workflow": []},
            label="测试资产",
            source_prd="test prd",
        )
        
        assert asset is not None
        assert asset["asset_type"] == "sop"
        assert asset["label"] == "测试资产"

    def test_save_document(self, test_project_repository, temp_project):
        """测试保存文档"""
        doc = test_project_repository.save_document(
            project_id=temp_project["id"],
            doc_type="prd",
            filename="test_prd.txt",
            content="这是一份测试PRD文档",
            original_name="原始名称.txt",
            tags=["测试", "prd"],
        )
        
        assert doc is not None
        assert doc["doc_type"] == "prd"
        assert doc["filename"] == "test_prd.txt"
        assert doc["content"] == "这是一份测试PRD文档"


class TestKnowledgeRepository:
    """KnowledgeRepository单元测试"""

    def test_index_knowledge(self, test_knowledge_repository):
        """测试索引知识"""
        entries = [
            {"key": "entity1", "value": "value1", "category": "test"},
            {"key": "entity2", "value": "value2", "category": "test"},
        ]
        
        test_knowledge_repository.index_knowledge(
            project_id="test-project",
            asset_id="test-asset",
            entries=entries,
        )
        
        results = test_knowledge_repository.search_knowledge(
            query="entity",
            project_id="test-project",
        )
        
        assert len(results) >= 2

    def test_search_knowledge(self, test_knowledge_repository):
        """测试搜索知识"""
        entries = [
            {"key": "业务目标", "value": "实现数字化转型", "category": "business_objective"},
            {"key": "风险评估", "value": "合规风险分析", "category": "risk"},
        ]
        
        test_knowledge_repository.index_knowledge(
            project_id="test-project",
            asset_id="test-asset",
            entries=entries,
        )
        
        results = test_knowledge_repository.search_knowledge(query="业务")
        
        assert len(results) >= 1
        assert any(r["key"] == "业务目标" for r in results)

    def test_save_knowledge_entity(self, test_knowledge_repository):
        """测试保存知识实体"""
        entity = test_knowledge_repository.save_knowledge_entity(
            entity_id="test-entity",
            project_id="test-project",
            category="business_objective",
            title="测试实体",
            description="测试实体描述",
            data={"key": "value"},
            domain="test",
            tags=["tag1", "tag2"],
            status="active",
        )
        
        assert entity is not None
        assert entity["title"] == "测试实体"
        assert entity["category"] == "business_objective"
        assert entity["data"] == {"key": "value"}
        assert entity["tags"] == ["tag1", "tag2"]

    def test_get_knowledge_entity(self, test_knowledge_repository):
        """测试获取知识实体"""
        test_knowledge_repository.save_knowledge_entity(
            entity_id="test-entity",
            project_id="test-project",
            category="business_objective",
            title="测试实体",
        )
        
        entity = test_knowledge_repository.get_knowledge_entity("test-entity")
        
        assert entity is not None
        assert entity["title"] == "测试实体"

    def test_list_knowledge_entities(self, test_knowledge_repository):
        """测试列出知识实体"""
        test_knowledge_repository.save_knowledge_entity(
            entity_id="entity1",
            project_id="test-project",
            category="business_objective",
            title="实体1",
        )
        test_knowledge_repository.save_knowledge_entity(
            entity_id="entity2",
            project_id="test-project",
            category="risk",
            title="实体2",
        )
        
        entities = test_knowledge_repository.list_knowledge_entities(project_id="test-project")
        
        assert len(entities) >= 2

    def test_add_member(self, test_knowledge_repository):
        """测试添加成员"""
        member = test_knowledge_repository.add_member(
            project_id="test-project",
            user_id="user1",
            role="editor",
        )
        
        assert member is not None
        assert member["user_id"] == "user1"
        assert member["role"] == "editor"

    def test_check_permission(self, test_knowledge_repository):
        """测试权限检查"""
        test_knowledge_repository.add_member(
            project_id="test-project",
            user_id="owner",
            role="owner",
        )
        test_knowledge_repository.add_member(
            project_id="test-project",
            user_id="viewer",
            role="viewer",
        )
        
        assert test_knowledge_repository.check_permission("test-project", "owner", "delete") is True
        assert test_knowledge_repository.check_permission("test-project", "owner", "read") is True
        assert test_knowledge_repository.check_permission("test-project", "viewer", "read") is True
        assert test_knowledge_repository.check_permission("test-project", "viewer", "delete") is False
        assert test_knowledge_repository.check_permission("test-project", "unknown", "read") is False


class TestGraphRepository:
    """GraphRepository单元测试"""

    def test_save_graph_snapshot(self, test_graph_repository):
        """测试保存图快照"""
        snapshot = test_graph_repository.save_graph_snapshot(
            graph_id="test-graph",
            name="测试图",
            data={"nodes": [], "edges": []},
            domain="test",
            project_id="test-project",
            node_count=0,
            edge_count=0,
        )
        
        assert snapshot is not None
        assert snapshot["name"] == "测试图"
        assert snapshot["data"] == {"nodes": [], "edges": []}

    def test_get_graph_snapshot(self, test_graph_repository):
        """测试获取图快照"""
        test_graph_repository.save_graph_snapshot(
            graph_id="test-graph",
            name="测试图",
            data={"nodes": [], "edges": []},
        )
        
        snapshot = test_graph_repository.get_graph_snapshot("test-graph")
        
        assert snapshot is not None
        assert snapshot["name"] == "测试图"

    def test_save_graph_nodes(self, test_graph_repository):
        """测试保存图节点"""
        test_graph_repository.save_graph_snapshot(
            graph_id="test-graph",
            name="测试图",
            data={"nodes": [], "edges": []},
        )
        
        nodes = [
            {"node_id": "node1", "node_type": "process", "label": "节点1", "description": "描述1"},
            {"node_id": "node2", "node_type": "process", "label": "节点2", "description": "描述2"},
        ]
        
        test_graph_repository.save_graph_nodes(graph_id="test-graph", nodes=nodes)
        
        saved_nodes = test_graph_repository.get_graph_nodes("test-graph")
        
        assert len(saved_nodes) == 2
        assert saved_nodes[0]["label"] == "节点1"

    def test_save_graph_edges(self, test_graph_repository):
        """测试保存图边"""
        test_graph_repository.save_graph_snapshot(
            graph_id="test-graph",
            name="测试图",
            data={"nodes": [], "edges": []},
        )
        
        nodes = [
            {"node_id": "node1", "node_type": "process", "label": "节点1"},
            {"node_id": "node2", "node_type": "process", "label": "节点2"},
        ]
        test_graph_repository.save_graph_nodes(graph_id="test-graph", nodes=nodes)
        
        edges = [
            {"source_id": "node1", "target_id": "node2", "edge_type": "depends_on", "label": "依赖"},
        ]
        
        test_graph_repository.save_graph_edges(graph_id="test-graph", edges=edges)
        
        saved_edges = test_graph_repository.get_graph_edges("test-graph")
        
        assert len(saved_edges) == 1
        assert saved_edges[0]["edge_type"] == "depends_on"


class TestCacheService:
    """缓存服务单元测试"""

    def test_cache_get_set(self, memory_cache):
        """测试缓存设置和获取"""
        memory_cache.set("test_key", "test_value", ttl=60)
        
        result = memory_cache.get("test_key")
        
        assert result == "test_value"

    def test_cache_expire(self):
        """测试缓存过期"""
        import time
        
        cache = MemoryCache(default_ttl=1)
        
        cache.set("test_key", "test_value")
        
        time.sleep(2)
        
        result = cache.get("test_key")
        
        assert result is None

    def test_cache_delete(self, memory_cache):
        """测试缓存删除"""
        memory_cache.set("test_key", "test_value")
        
        result = memory_cache.delete("test_key")
        
        assert result is True
        assert memory_cache.get("test_key") is None

    def test_cache_exists(self, memory_cache):
        """测试缓存存在检查"""
        memory_cache.set("test_key", "test_value")
        
        assert memory_cache.exists("test_key") is True
        assert memory_cache.exists("nonexistent") is False

    def test_cache_clear(self, memory_cache):
        """测试缓存清除"""
        memory_cache.set("key1", "value1")
        memory_cache.set("key2", "value2")
        
        memory_cache.clear()
        
        assert memory_cache.get("key1") is None
        assert memory_cache.get("key2") is None