"""
Pytest配置文件 - 测试框架配置

提供测试夹具（fixtures）：
- test_db: 测试数据库连接
- temp_project: 临时项目
- mock_llm_service: Mock LLM服务
"""
import os
import sys
import pytest
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.repositories import ProjectRepository, KnowledgeRepository, GraphRepository
from app.core.llm_service import LLMService
from app.core.cache_service import MemoryCache, get_cache_service


def _init_test_db(db_path):
    """初始化测试数据库表结构"""
    import sqlite3
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT, domain TEXT, status TEXT, created_at TEXT, updated_at TEXT, metadata TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS assets (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, asset_type TEXT NOT NULL, label TEXT, version INTEGER, data TEXT NOT NULL, source_prd TEXT, created_at TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS knowledge_index (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, asset_id TEXT, key TEXT NOT NULL, value TEXT NOT NULL, category TEXT)")
    conn.execute("""CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
        doc_type TEXT NOT NULL,
        filename TEXT NOT NULL, original_name TEXT,
        content TEXT NOT NULL, size_bytes INTEGER DEFAULT 0,
        status TEXT DEFAULT 'active',
        tags TEXT DEFAULT '[]',
        uploaded_at TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS project_members (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'viewer',
        joined_at TEXT,
        UNIQUE(project_id, user_id)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS knowledge_entities (
        id TEXT PRIMARY KEY, project_id TEXT,
        category TEXT NOT NULL,
        title TEXT NOT NULL, description TEXT DEFAULT '',
        version_number INTEGER DEFAULT 1,
        data TEXT NOT NULL DEFAULT '{}',
        status TEXT DEFAULT 'active',
        domain TEXT DEFAULT 'general',
        tags TEXT DEFAULT '[]',
        created_at TEXT, updated_at TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS graph_snapshots (
        id TEXT PRIMARY KEY, name TEXT NOT NULL,
        domain TEXT DEFAULT 'general', project_id TEXT DEFAULT '',
        version TEXT DEFAULT '1.0.0',
        data TEXT NOT NULL DEFAULT '{}',
        node_count INTEGER DEFAULT 0, edge_count INTEGER DEFAULT 0,
        created_at TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS graph_nodes_persistent (
        id TEXT PRIMARY KEY, graph_id TEXT NOT NULL,
        node_type TEXT NOT NULL,
        label TEXT NOT NULL, description TEXT DEFAULT '',
        owner TEXT DEFAULT '', domain TEXT DEFAULT 'general',
        project_id TEXT DEFAULT '',
        entity_ref TEXT DEFAULT '',
        properties TEXT DEFAULT '{}',
        weight REAL DEFAULT 1.0,
        status TEXT DEFAULT 'active',
        created_at TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS graph_edges_persistent (
        id TEXT PRIMARY KEY, graph_id TEXT NOT NULL,
        source_id TEXT NOT NULL, target_id TEXT NOT NULL,
        edge_type TEXT NOT NULL,
        label TEXT DEFAULT '', weight REAL DEFAULT 1.0,
        properties TEXT DEFAULT '{}',
        created_at TEXT
    )""")
    conn.commit()
    conn.close()


@pytest.fixture(scope="function")
def test_project_repository():
    """创建测试用的ProjectRepository（使用内存数据库）"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    
    _init_test_db(db_path)
    repo = ProjectRepository(db_path)
    
    try:
        yield repo
    finally:
        repo.close()
        os.unlink(db_path)


@pytest.fixture(scope="function")
def test_knowledge_repository():
    """创建测试用的KnowledgeRepository（使用内存数据库）"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    
    _init_test_db(db_path)
    repo = KnowledgeRepository(db_path)
    
    try:
        yield repo
    finally:
        repo.close()
        os.unlink(db_path)


@pytest.fixture(scope="function")
def test_graph_repository():
    """创建测试用的GraphRepository（使用内存数据库）"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    
    _init_test_db(db_path)
    repo = GraphRepository(db_path)
    
    try:
        yield repo
    finally:
        repo.close()
        os.unlink(db_path)


@pytest.fixture(scope="function")
def mock_llm_service():
    """创建Mock LLM服务"""
    return LLMService(provider="mock")


@pytest.fixture(scope="function")
def memory_cache():
    """创建内存缓存"""
    return MemoryCache(default_ttl=60)


@pytest.fixture(scope="function")
def temp_project(test_project_repository):
    """创建临时项目"""
    project = test_project_repository.create_project(
        name="测试项目",
        description="测试项目描述",
        domain="test",
        metadata={"test_key": "test_value"},
    )
    return project


@pytest.fixture(autouse=True)
def reset_cache():
    """每个测试后重置缓存"""
    cache = get_cache_service()
    cache.clear()
    yield