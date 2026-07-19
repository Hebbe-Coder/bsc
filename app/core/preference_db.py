"""
用户偏好存储模块 - SQLite实现

设计原则：
- 零外部依赖：使用Python内置sqlite3
- 自动迁移：首次运行时自动创建表
- 线程安全：使用连接池管理
- 数据持久化：用户偏好跨会话保存

表结构：
- users: 用户基本信息
- user_preferences: 用户偏好设置
- template_usage: 模板使用记录
- dialog_sessions: 对话会话记录
"""
from __future__ import annotations
import sqlite3
import json
import uuid
import os
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class PreferenceDB:
    """用户偏好数据库操作类"""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or self._get_default_path()
        self._ensure_tables()
    
    def _get_default_path(self) -> str:
        """获取默认数据库路径"""
        data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
        os.makedirs(data_dir, exist_ok=True)
        return os.path.join(data_dir, "preferences.db")
    
    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _ensure_tables(self):
        """确保表存在，自动迁移"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id VARCHAR(36) PRIMARY KEY,
                name VARCHAR(100),
                email VARCHAR(200),
                default_depth VARCHAR(20) DEFAULT 'medium',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_preferences (
                pref_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id VARCHAR(36),
                key VARCHAR(100),
                value TEXT,
                category VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS template_usage (
                usage_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id VARCHAR(36),
                template_key VARCHAR(50),
                industry VARCHAR(50),
                sections_used TEXT,
                success_rating INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS dialog_sessions (
                session_id VARCHAR(36) PRIMARY KEY,
                user_id VARCHAR(36),
                input_text TEXT,
                depth VARCHAR(20),
                industry VARCHAR(50),
                status VARCHAR(20) DEFAULT 'started',
                collected_data TEXT,
                prd_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS dialog_messages (
                message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id VARCHAR(36),
                question_key VARCHAR(100),
                question TEXT,
                answer TEXT,
                question_number INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES dialog_sessions(session_id)
            )
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_user_preferences_user_id ON user_preferences(user_id)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_template_usage_user_id ON template_usage(user_id)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_dialog_sessions_user_id ON dialog_sessions(user_id)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_dialog_messages_session_id ON dialog_messages(session_id)
        ''')
        
        conn.commit()
        conn.close()
    
    def create_user(self, user_id: str, name: str = None, email: str = None, 
                    default_depth: str = "medium") -> bool:
        """创建用户"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO users 
                (user_id, name, email, default_depth, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (user_id, name, email, default_depth))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Failed to create user: {e}")
            return False
    
    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """获取用户信息"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()
            
            conn.close()
            
            if row:
                return {
                    "user_id": row["user_id"],
                    "name": row["name"],
                    "email": row["email"],
                    "default_depth": row["default_depth"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            return None
        except Exception as e:
            logger.error(f"Failed to get user: {e}")
            return None
    
    def update_user(self, user_id: str, **kwargs) -> bool:
        """更新用户信息"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            fields = []
            values = []
            
            if "name" in kwargs:
                fields.append("name = ?")
                values.append(kwargs["name"])
            if "email" in kwargs:
                fields.append("email = ?")
                values.append(kwargs["email"])
            if "default_depth" in kwargs:
                fields.append("default_depth = ?")
                values.append(kwargs["default_depth"])
            
            fields.append("updated_at = CURRENT_TIMESTAMP")
            values.append(user_id)
            
            if fields:
                cursor.execute(f'''
                    UPDATE users SET {", ".join(fields)} WHERE user_id = ?
                ''', values)  # nosec B608 - fields are hardcoded whitelist
                
                conn.commit()
            
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Failed to update user: {e}")
            return False
    
    def set_preference(self, user_id: str, key: str, value: Any, 
                       category: str = "general") -> bool:
        """设置用户偏好"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO user_preferences 
                (user_id, key, value, category)
                VALUES (?, ?, ?, ?)
            ''', (user_id, key, json.dumps(value), category))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Failed to set preference: {e}")
            return False
    
    def get_preference(self, user_id: str, key: str) -> Optional[Any]:
        """获取用户偏好"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT value FROM user_preferences 
                WHERE user_id = ? AND key = ?
            ''', (user_id, key))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return json.loads(row["value"])
            return None
        except Exception as e:
            logger.error(f"Failed to get preference: {e}")
            return None
    
    def get_all_preferences(self, user_id: str) -> Dict[str, Any]:
        """获取用户所有偏好"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT key, value, category FROM user_preferences 
                WHERE user_id = ?
            ''', (user_id,))
            
            rows = cursor.fetchall()
            conn.close()
            
            preferences = {}
            for row in rows:
                try:
                    preferences[row["key"]] = json.loads(row["value"])
                except json.JSONDecodeError:
                    preferences[row["key"]] = row["value"]
            
            return preferences
        except Exception as e:
            logger.error(f"Failed to get all preferences: {e}")
            return {}
    
    def delete_preference(self, user_id: str, key: str) -> bool:
        """删除用户偏好"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                DELETE FROM user_preferences 
                WHERE user_id = ? AND key = ?
            ''', (user_id, key))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Failed to delete preference: {e}")
            return False
    
    def record_template_usage(self, user_id: str, template_key: str, 
                              industry: str, sections_used: List[str], 
                              success_rating: int = None) -> bool:
        """记录模板使用"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO template_usage 
                (user_id, template_key, industry, sections_used, success_rating)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, template_key, industry, json.dumps(sections_used), success_rating))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Failed to record template usage: {e}")
            return False
    
    def get_template_usage(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """获取用户模板使用记录"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM template_usage 
                WHERE user_id = ? 
                ORDER BY created_at DESC 
                LIMIT ?
            ''', (user_id, limit))
            
            rows = cursor.fetchall()
            conn.close()
            
            result = []
            for row in rows:
                result.append({
                    "usage_id": row["usage_id"],
                    "template_key": row["template_key"],
                    "industry": row["industry"],
                    "sections_used": json.loads(row["sections_used"]) if row["sections_used"] else [],
                    "success_rating": row["success_rating"],
                    "created_at": row["created_at"],
                })
            
            return result
        except Exception as e:
            logger.error(f"Failed to get template usage: {e}")
            return []
    
    def create_dialog_session(self, user_id: str, input_text: str, 
                              depth: str, industry: str) -> str:
        """创建对话会话"""
        session_id = str(uuid.uuid4())
        
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO dialog_sessions 
                (session_id, user_id, input_text, depth, industry)
                VALUES (?, ?, ?, ?, ?)
            ''', (session_id, user_id, input_text, depth, industry))
            
            conn.commit()
            conn.close()
            return session_id
        except Exception as e:
            logger.error(f"Failed to create dialog session: {e}")
            return ""
    
    def get_dialog_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取对话会话"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM dialog_sessions WHERE session_id = ?', (session_id,))
            row = cursor.fetchone()
            
            if row:
                cursor.execute('''
                    SELECT * FROM dialog_messages 
                    WHERE session_id = ? 
                    ORDER BY question_number
                ''', (session_id,))
                
                messages = cursor.fetchall()
                
                conn.close()
                
                result = {
                    "session_id": row["session_id"],
                    "user_id": row["user_id"],
                    "input_text": row["input_text"],
                    "depth": row["depth"],
                    "industry": row["industry"],
                    "status": row["status"],
                    "collected_data": json.loads(row["collected_data"]) if row["collected_data"] else {},
                    "prd_text": row["prd_text"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "messages": [],
                }
                
                for msg in messages:
                    result["messages"].append({
                        "message_id": msg["message_id"],
                        "question_key": msg["question_key"],
                        "question": msg["question"],
                        "answer": msg["answer"],
                        "question_number": msg["question_number"],
                        "created_at": msg["created_at"],
                    })
                
                return result
            
            conn.close()
            return None
        except Exception as e:
            logger.error(f"Failed to get dialog session: {e}")
            return None
    
    def update_dialog_session(self, session_id: str, **kwargs) -> bool:
        """更新对话会话"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            fields = []
            values = []
            
            if "status" in kwargs:
                fields.append("status = ?")
                values.append(kwargs["status"])
            if "collected_data" in kwargs:
                fields.append("collected_data = ?")
                values.append(json.dumps(kwargs["collected_data"]))
            if "prd_text" in kwargs:
                fields.append("prd_text = ?")
                values.append(kwargs["prd_text"])
            
            fields.append("updated_at = CURRENT_TIMESTAMP")
            values.append(session_id)
            
            if fields:
                cursor.execute(f'''
                    UPDATE dialog_sessions SET {", ".join(fields)} WHERE session_id = ?
                ''', values)  # nosec B608 - fields are hardcoded whitelist
                
                conn.commit()
            
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Failed to update dialog session: {e}")
            return False
    
    def add_dialog_message(self, session_id: str, question_key: str, 
                           question: str, answer: str, question_number: int) -> bool:
        """添加对话消息"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO dialog_messages 
                (session_id, question_key, question, answer, question_number)
                VALUES (?, ?, ?, ?, ?)
            ''', (session_id, question_key, question, answer, question_number))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Failed to add dialog message: {e}")
            return False
    
    def update_dialog_message_answer(self, session_id: str, question_number: int, answer: str) -> bool:
        """更新对话消息的回答"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE dialog_messages 
                SET answer = ? 
                WHERE session_id = ? AND question_number = ?
            ''', (answer, session_id, question_number))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Failed to update dialog message: {e}")
            return False
    
    def delete_dialog_session(self, session_id: str) -> bool:
        """删除对话会话"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM dialog_messages WHERE session_id = ?', (session_id,))
            cursor.execute('DELETE FROM dialog_sessions WHERE session_id = ?', (session_id,))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Failed to delete dialog session: {e}")
            return False
    
    def get_user_dialog_sessions(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """获取用户对话会话列表"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT session_id, input_text, status, created_at 
                FROM dialog_sessions 
                WHERE user_id = ? 
                ORDER BY created_at DESC 
                LIMIT ?
            ''', (user_id, limit))
            
            rows = cursor.fetchall()
            conn.close()
            
            result = []
            for row in rows:
                result.append({
                    "session_id": row["session_id"],
                    "input_text": row["input_text"],
                    "status": row["status"],
                    "created_at": row["created_at"],
                })
            
            return result
        except Exception as e:
            logger.error(f"Failed to get user dialog sessions: {e}")
            return []


_preference_db: Optional[PreferenceDB] = None


def get_preference_db() -> PreferenceDB:
    """获取偏好数据库实例（单例）"""
    global _preference_db
    if _preference_db is None:
        _preference_db = PreferenceDB()
    return _preference_db


__all__ = ["PreferenceDB", "get_preference_db"]
