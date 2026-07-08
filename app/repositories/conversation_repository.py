"""ConversationRepository - 对话历史存储

使用SQLite替代内存字典存储，支持：
- 对话创建/查询
- 消息添加/查询
- 对话统计
- 数据持久化（重启不丢失）
"""
from __future__ import annotations
from typing import List, Dict, Any, Optional

from app.repositories.base_repository import BaseRepository


class ConversationRepository(BaseRepository):
    """对话历史Repository"""

    def __init__(self, db_path: Optional[str] = None):
        super().__init__(db_path)
        self._init_schema()

    def _init_schema(self):
        """初始化数据库表"""
        sql = """
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            metadata TEXT DEFAULT '{}'
        );
        
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            conv_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            data TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY (conv_id) REFERENCES conversations(id) ON DELETE CASCADE
        );
        
        CREATE INDEX IF NOT EXISTS idx_messages_conv_id ON messages(conv_id);
        """
        conn = self._get_connection()
        conn.executescript(sql)
        conn.commit()

    def create_conversation(self, conv_id: str = None, metadata: Dict = None) -> str:
        """创建对话
        
        Args:
            conv_id: 对话ID（可选，自动生成）
            metadata: 对话元数据
        
        Returns:
            对话ID
        """
        conv_id = conv_id or self._generate_id()
        metadata = metadata or {}
        
        sql = """
        INSERT OR IGNORE INTO conversations (id, created_at, updated_at, metadata)
        VALUES (?, ?, ?, ?)
        """
        now = self._now()
        self._execute(sql, (conv_id, now, now, self._json_dumps(metadata)))
        self._commit()
        
        return conv_id

    def get_conversation(self, conv_id: str) -> Optional[Dict[str, Any]]:
        """获取对话详情
        
        Args:
            conv_id: 对话ID
        
        Returns:
            对话信息或None
        """
        sql = "SELECT * FROM conversations WHERE id = ?"
        row = self._execute(sql, (conv_id,)).fetchone()
        if row:
            result = self._row_to_dict(row)
            result["metadata"] = self._json_loads(result["metadata"])
            return result
        return None

    def delete_conversation(self, conv_id: str):
        """删除对话（级联删除消息）
        
        Args:
            conv_id: 对话ID
        """
        sql = "DELETE FROM conversations WHERE id = ?"
        self._execute(sql, (conv_id,))
        self._commit()

    def add_message(self, conv_id: str, role: str, content: str, data: Dict = None):
        """添加消息
        
        Args:
            conv_id: 对话ID
            role: 角色（user/assistant）
            content: 消息内容
            data: 附加数据（可选）
        """
        data = data or {}
        
        if not self.get_conversation(conv_id):
            self.create_conversation(conv_id)
        
        sql = """
        INSERT INTO messages (id, conv_id, role, content, data, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """
        self._execute(sql, (
            self._generate_id(),
            conv_id,
            role,
            content,
            self._json_dumps(data),
            self._now(),
        ))
        
        sql_update = "UPDATE conversations SET updated_at = ? WHERE id = ?"
        self._execute(sql_update, (self._now(), conv_id))
        
        self._commit()

    def get_messages(self, conv_id: str) -> List[Dict[str, Any]]:
        """获取对话消息列表
        
        Args:
            conv_id: 对话ID
        
        Returns:
            消息列表
        """
        sql = "SELECT * FROM messages WHERE conv_id = ? ORDER BY created_at ASC"
        rows = self._rows_to_list(self._execute(sql, (conv_id,)))
        
        for row in rows:
            row["data"] = self._json_loads(row["data"])
        
        return rows

    def get_conversations(self, limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        """获取对话列表（按更新时间排序）
        
        Args:
            limit: 数量限制
            offset: 偏移量
        
        Returns:
            对话列表
        """
        sql = "SELECT * FROM conversations ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        rows = self._rows_to_list(self._execute(sql, (limit, offset)))
        
        for row in rows:
            row["metadata"] = self._json_loads(row["metadata"])
        
        return rows

    def get_conversation_count(self) -> int:
        """获取对话总数
        
        Returns:
            对话数量
        """
        sql = "SELECT COUNT(*) FROM conversations"
        result = self._execute(sql).fetchone()
        return result[0] if result else 0

    def get_last_message_data(self, conv_id: str) -> Optional[Dict[str, Any]]:
        """获取最后一条assistant消息的data
        
        Args:
            conv_id: 对话ID
        
        Returns:
            最后一条消息的data或None
        """
        sql = """
        SELECT data FROM messages 
        WHERE conv_id = ? AND role = 'assistant' 
        ORDER BY created_at DESC LIMIT 1
        """
        row = self._execute(sql, (conv_id,)).fetchone()
        if row and row["data"]:
            return self._json_loads(row["data"])
        return None


def get_conversation_repository() -> ConversationRepository:
    """获取对话Repository实例"""
    return ConversationRepository()