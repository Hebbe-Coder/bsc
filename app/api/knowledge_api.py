"""知识库 API 端点：上传/文本灌入、列出、检索、删除。"""
from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel

from fastapi import APIRouter, Depends, UploadFile, File, Form
from app.core.document_parser import parse_document
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


@router.post("/ingest")
async def ingest(
    files: Optional[List[UploadFile]] = File(None),
    text: str = Form(default=""),
    project_id: str = Form(default=""),
    asset_id: str = Form(default=""),
    title: str = Form(default=""),
    source: str = Form(default="upload"),
    service: KnowledgeService = Depends(get_knowledge_service),
):
    units = []
    parse_errors = []
    for f in (files or []):
        content = await f.read()
        parsed = parse_document(content, f.filename or "unknown")
        if parsed["success"]:
            units.append((title or f.filename or "unknown", parsed["text"]))
        else:
            parse_errors.append({"filename": f.filename, "error": parsed["error"]})
    if text and text.strip():
        units.append((title or "text", text))
    if not units:
        return ApiResponse.error("请提供文件或文本内容", code=400)
    docs = []
    for disp_title, t in units:
        doc_id = service.ingest(
            t, project_id=project_id, asset_id=asset_id,
            title=disp_title, source=source)
        docs.append({"doc_id": doc_id, "title": disp_title,
                     "status": "ok" if doc_id else "skipped"})
    if parse_errors:
        return ApiResponse.partial(
            data={"docs": docs, "count": len(docs)},
            message="部分文件解析失败", errors=parse_errors)
    return ApiResponse.ok({"docs": docs, "count": len(docs)})


class RetrieveRequest(BaseModel):
    query: str
    top_k: int = 5
    project_id: str = ""


@router.post("/retrieve")
def retrieve(
    req: RetrieveRequest,
    service: KnowledgeService = Depends(get_knowledge_service),
):
    if not req.query or not req.query.strip():
        return ApiResponse.error("请提供查询语句", code=400)
    results = service.retrieve(
        req.query, top_k=req.top_k, project_id=req.project_id or None)
    return ApiResponse.ok({"results": results})


@router.delete("/documents/{doc_id}")
def delete_document(
    doc_id: str,
    service: KnowledgeService = Depends(get_knowledge_service),
):
    if not service.delete_document(doc_id):
        return ApiResponse.not_found("文档不存在")
    return ApiResponse.ok({"deleted": doc_id})
