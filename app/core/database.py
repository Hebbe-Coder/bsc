"""
Database Abstraction Layer - 数据库抽象层

支持多数据库后端：SQLite（开发环境）和 PostgreSQL（生产环境）

配置方式：
    DB_TYPE=sqlite          # sqlite 或 postgresql
    DB_PATH=bsc_cloud.db    # SQLite文件路径（仅SQLite）
    DB_URL=postgres://user:pass@host:port/db   # PostgreSQL连接URL（仅PostgreSQL）

设计原则：
1. 接口统一，切换数据库无需修改业务代码
2. 支持连接池（PostgreSQL）
3. 支持事务管理
4. 支持批量操作
5. 线程安全：SQLite使用线程本地连接，PostgreSQL使用独立连接
"""
from __future__ import annotations
import sqlite3
import os
import json
import uuid
import time
import threading
from typing import Optional, List, Dict, Any, Protocol

from app.core.config import settings


class DatabaseBackend(Protocol):
    """数据库后端协议接口"""
    
    def connect(self) -> None:
        """建立数据库连接"""
        ...
    
    def close(self) -> None:
        """关闭数据库连接"""
        ...
    
    def execute(self, sql: str, params: tuple = ()) -> Any:
        """执行SQL语句，返回游标对象"""
        ...
    
    def executemany(self, sql: str, params: List[tuple]) -> Any:
        """批量执行SQL语句，返回游标对象"""
        ...
    
    def commit(self) -> None:
        """提交事务"""
        ...
    
    def rollback(self) -> None:
        """回滚事务"""
        ...
    
    def row_to_dict(self, row) -> Dict[str, Any]:
        """将行对象转换为字典"""
        ...
    
    def rows_to_list(self, cursor) -> List[Dict[str, Any]]:
        """将游标结果转换为字典列表"""
        ...
    
    def test_connection(self) -> bool:
        """测试数据库连接"""
        ...


class SQLiteBackend:
    """SQLite数据库后端 - 线程安全实现"""
    
    _global_thread_local = threading.local()
    
    def __init__(self, db_path: str = None):
        self._db_path = db_path or os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "bsc_cloud.db"
        )
        self._instance_id = id(self)
    
    def _get_connection(self) -> sqlite3.Connection:
        """获取当前线程的数据库连接"""
        if not hasattr(self._global_thread_local, "connections"):
            self._global_thread_local.connections = {}
        
        if self._instance_id not in self._global_thread_local.connections:
            conn = sqlite3.connect(
                self._db_path,
                timeout=30,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._global_thread_local.connections[self._instance_id] = conn
        
        return self._global_thread_local.connections[self._instance_id]
    
    def connect(self):
        self._get_connection()
    
    def close(self):
        if hasattr(self._global_thread_local, "connections"):
            if self._instance_id in self._global_thread_local.connections:
                self._global_thread_local.connections[self._instance_id].close()
                del self._global_thread_local.connections[self._instance_id]
    
    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        conn = self._get_connection()
        try:
            return conn.execute(sql, params)
        except sqlite3.Error as e:
            conn.rollback()
            raise
    
    def executemany(self, sql: str, params: List[tuple]) -> sqlite3.Cursor:
        conn = self._get_connection()
        try:
            return conn.executemany(sql, params)
        except sqlite3.Error as e:
            conn.rollback()
            raise
    
    def commit(self):
        conn = self._get_connection()
        conn.commit()
    
    def rollback(self):
        if hasattr(self._global_thread_local, "connections"):
            if self._instance_id in self._global_thread_local.connections:
                self._global_thread_local.connections[self._instance_id].rollback()
    
    def row_to_dict(self, row) -> Dict[str, Any]:
        return dict(row) if row else {}
    
    def rows_to_list(self, cursor) -> List[Dict[str, Any]]:
        return [self.row_to_dict(row) for row in cursor.fetchall()]
    
    def test_connection(self) -> bool:
        try:
            self.connect()
            self.execute("SELECT 1")
            return True
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.debug(f"SQLite connection test failed: {e}")
            return False


class PostgreSQLBackend:
    """PostgreSQL数据库后端"""
    
    def __init__(self, db_url: str = None):
        self._db_url = db_url or settings.DB_URL
        self._connection = None
        self._pool = None
    
    def connect(self):
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
            
            if self._connection is None:
                self._connection = psycopg2.connect(self._db_url)
                self._connection.autocommit = False
        except ImportError:
            raise RuntimeError("psycopg2未安装，请运行: pip install psycopg2-binary")
        except Exception as e:
            raise RuntimeError(f"PostgreSQL连接失败: {e}")
    
    def close(self):
        if self._connection is not None:
            self._connection.close()
            self._connection = None
    
    def execute(self, sql: str, params: tuple = ()) -> 'psycopg2.extensions.cursor':
        self.connect()
        try:
            cursor = self._connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute(sql, params)
            return cursor
        except psycopg2.Error as e:
            self._connection.rollback()
            raise
    
    def executemany(self, sql: str, params: List[tuple]) -> 'psycopg2.extensions.cursor':
        self.connect()
        try:
            cursor = self._connection.cursor()
            cursor.executemany(sql, params)
            return cursor
        except psycopg2.Error as e:
            self._connection.rollback()
            raise
    
    def commit(self):
        self.connect()
        self._connection.commit()
    
    def rollback(self):
        if self._connection:
            self._connection.rollback()
    
    def row_to_dict(self, row) -> Dict[str, Any]:
        return dict(row) if row else {}
    
    def rows_to_list(self, cursor) -> List[Dict[str, Any]]:
        return [dict(row) for row in cursor.fetchall()]
    
    def test_connection(self) -> bool:
        try:
            self.connect()
            cursor = self.execute("SELECT 1")
            cursor.fetchone()
            return True
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.debug(f"PostgreSQL connection test failed: {e}")
            return False


def get_database_backend(db_type: str = None) -> DatabaseBackend:
    """获取数据库后端实例"""
    db_type = db_type or settings.DB_TYPE
    
    if db_type == "postgresql":
        return PostgreSQLBackend()
    else:
        return SQLiteBackend()


def init_database():
    """初始化数据库（创建必要的表）"""
    backend = get_database_backend()
    
    create_tables = [
        """
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            domain TEXT DEFAULT 'general',
            status TEXT DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            metadata TEXT DEFAULT '{}'
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS project_assets (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            name TEXT NOT NULL,
            type TEXT DEFAULT 'file',
            content TEXT DEFAULT '',
            path TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS project_documents (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            name TEXT NOT NULL,
            content TEXT DEFAULT '',
            document_type TEXT DEFAULT 'prd',
            created_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS knowledge_entities (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            entity_type TEXT DEFAULT 'general',
            description TEXT DEFAULT '',
            attributes TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS knowledge_members (
            id TEXT PRIMARY KEY,
            entity_id TEXT NOT NULL,
            member_id TEXT NOT NULL,
            role TEXT DEFAULT 'viewer',
            FOREIGN KEY (entity_id) REFERENCES knowledge_entities(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS graph_snapshots (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            snapshot_type TEXT NOT NULL,
            data TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS graph_nodes (
            id TEXT PRIMARY KEY,
            snapshot_id TEXT NOT NULL,
            node_id TEXT NOT NULL,
            data TEXT DEFAULT '{}',
            FOREIGN KEY (snapshot_id) REFERENCES graph_snapshots(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS graph_edges (
            id TEXT PRIMARY KEY,
            snapshot_id TEXT NOT NULL,
            source TEXT NOT NULL,
            target TEXT NOT NULL,
            data TEXT DEFAULT '{}',
            FOREIGN KEY (snapshot_id) REFERENCES graph_snapshots(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS api_usage_log (
            id TEXT PRIMARY KEY,
            endpoint TEXT NOT NULL,
            method TEXT NOT NULL,
            status_code INTEGER DEFAULT 200,
            duration_ms INTEGER DEFAULT 0,
            client_ip TEXT DEFAULT '',
            api_key_hash TEXT DEFAULT '',
            timestamp TEXT NOT NULL,
            trace_id TEXT DEFAULT ''
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS daily_stats (
            id TEXT PRIMARY KEY,
            date TEXT NOT NULL UNIQUE,
            total_requests INTEGER DEFAULT 0,
            total_errors INTEGER DEFAULT 0,
            total_llm_calls INTEGER DEFAULT 0,
            avg_response_ms REAL DEFAULT 0,
            p95_response_ms REAL DEFAULT 0,
            p99_response_ms REAL DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS business_metrics (
            id TEXT PRIMARY KEY,
            project_id TEXT DEFAULT '',
            domain TEXT DEFAULT '',
            metric_type TEXT NOT NULL,
            metric_value REAL DEFAULT 0,
            metric_units TEXT DEFAULT '',
            timestamp TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS templates (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT DEFAULT 'analysis',
            industry TEXT DEFAULT 'general',
            type TEXT DEFAULT 'custom',
            config_json TEXT DEFAULT '{}',
            description TEXT DEFAULT '',
            is_builtin INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            sort_order INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS compile_history (
            id TEXT PRIMARY KEY,
            prd_content TEXT DEFAULT '',
            business_domain TEXT DEFAULT '',
            industry TEXT DEFAULT 'general',
            template_id TEXT DEFAULT '',
            result_summary TEXT DEFAULT '',
            execution_time_ms INTEGER DEFAULT 0,
            success INTEGER DEFAULT 1,
            error_message TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            metadata TEXT DEFAULT '{}'
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS recommendations (
            id TEXT PRIMARY KEY,
            project_id TEXT DEFAULT '',
            user_id TEXT DEFAULT '',
            type TEXT DEFAULT 'optimization',
            content TEXT DEFAULT '',
            confidence REAL DEFAULT 0.0,
            source TEXT DEFAULT 'system',
            applied INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            applied_at TEXT DEFAULT ''
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS industry_patterns (
            id TEXT PRIMARY KEY,
            industry TEXT NOT NULL,
            pattern_type TEXT DEFAULT 'optimization',
            pattern_name TEXT NOT NULL,
            pattern_content TEXT DEFAULT '',
            frequency INTEGER DEFAULT 0,
            avg_improvement REAL DEFAULT 0.0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
    ]
    
    try:
        for sql in create_tables:
            backend.execute(sql)
        backend.commit()
        backend.close()
    except Exception as e:
        backend.rollback()
        backend.close()
        raise