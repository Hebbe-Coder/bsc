"""Repository层 - 数据访问层

采用Repository模式，将数据库操作与业务逻辑解耦：
- BaseRepository: 提供数据库连接池和基础CRUD操作
- ProjectRepository: 项目相关操作
- KnowledgeRepository: 知识实体相关操作
- GraphRepository: 图数据相关操作

使用连接池替代全局单例连接，解决SQLite并发安全问题。
"""
from .base_repository import BaseRepository
from .project_repository import ProjectRepository
from .knowledge_repository import KnowledgeRepository
from .graph_repository import GraphRepository

__all__ = [
    "BaseRepository",
    "ProjectRepository",
    "KnowledgeRepository",
    "GraphRepository",
]