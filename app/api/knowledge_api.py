"""知识库 API 端点：上传/文本灌入、列出、检索、删除。"""
from __future__ import annotations
from typing import List, Optional

from fastapi import APIRouter, Depends
from app.api.response import ApiResponse
from app.knowledge.service import KnowledgeService

router = APIRouter(prefix="/knowledge", tags=["Knowledge"])


def get_knowledge_service() -> KnowledgeService:
    return KnowledgeService()


@router.get("/documents")
def list_documents(
    project_id: str = "",
    limit: int = 100,
    offset: int = 0,
    service: KnowledgeService = Depends(get_knowledge_service),
):
    result = service.list_documents(
        project_id=project_id or None, limit=limit, offset=offset)
    return ApiResponse.ok(result)
