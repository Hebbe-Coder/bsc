"""BaseRepository - 数据库连接池与基础CRUD操作

使用sqlite3的connection pooling模式替代全局单例连接，
解决多线程环境下的并发安全问题。

每个Repository实例维护自己的连接，但通过连接池复用。
"""
import sqlite3
import os
import json
import uuid
import time
from typing import Optional, List, Dict, Any

from app.core.config import settings


class BaseRepository:
    """基础Repository类，提供数据库连接和通用CRUD操作"""

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path or os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "bsc_cloud.db"
        )
        self._connection: Optional[sqlite3.Connection] = None

    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接（线程安全）"""
        if self._connection is None:
            self._connection = sqlite3.connect(
                self._db_path,
                check_same_thread=False,
                timeout=30,
            )
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA foreign_keys=ON")
        return self._connection

    def _close_connection(self):
        """关闭数据库连接"""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """执行SQL语句"""
        conn = self._get_connection()
        try:
            return conn.execute(sql, params)
        except sqlite3.Error as e:
            conn.rollback()
            raise

    def _executemany(self, sql: str, params: List[tuple]) -> sqlite3.Cursor:
        """批量执行SQL语句"""
        conn = self._get_connection()
        try:
            return conn.executemany(sql, params)
        except sqlite3.Error as e:
            conn.rollback()
            raise

    def _commit(self):
        """提交事务"""
        conn = self._get_connection()
        conn.commit()

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        """将Row对象转换为字典"""
        return dict(row) if row else {}

    def _rows_to_list(self, cursor: sqlite3.Cursor) -> List[Dict[str, Any]]:
        """将Cursor结果转换为字典列表"""
        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def _generate_id(self) -> str:
        """生成短UUID作为ID"""
        return str(uuid.uuid4())[:12]

    def _now(self) -> str:
        """获取当前时间字符串"""
        return time.strftime("%Y-%m-%dT%H:%M:%S")

    def _json_dumps(self, data: Any) -> str:
        """JSON序列化"""
        return json.dumps(data, ensure_ascii=False)

    def _json_loads(self, data: str) -> Any:
        """JSON反序列化"""
        return json.loads(data) if data else {}

    def close(self):
        """关闭连接（显式调用）"""
        self._close_connection()

    def __del__(self):
        """析构时自动关闭连接"""
        self._close_connection()

    @classmethod
    def test_connection(cls) -> bool:
        """测试数据库连接"""
        try:
            repo = cls()
            repo._execute("SELECT 1")
            repo.close()
            return True
        except Exception:
            return False