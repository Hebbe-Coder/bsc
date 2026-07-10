"""知识库 API 端点：上传/文本灌入、列出、检索、删除。"""
from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel

from fastapi import APIRouter, Depends, UploadFile, File, Form, Request, HTTPException
from app.core.document_parser import parse_document
from app.api.response import ApiResponse
from app.knowledge.service import KnowledgeService

router = APIRouter(prefix="/knowledge", tags=["Knowledge"])


def get_knowledge_service() -> KnowledgeService:
    return KnowledgeService()


def require_admin(request: Request) -> bool:
    """RBAC：ingest / delete 等写入型操作仅限 admin Key。"""
    role = getattr(request.state, "knowledge_role", None)
    if role != "admin":
        raise HTTPException(
            status_code=403,
            detail="需要管理员权限：ingest / delete 仅限 admin Key",
        )
    return True


def _role_and_project(request: Request):
    return (getattr(request.state, "knowledge_role", None),
            getattr(request.state, "knowledge_project_id", None))


def _enforce_project_access(request: Request, requested_project_id: str,
                            write: bool = False, allow_admin_all: bool = False) -> str:
    """校验并返回本次请求应使用的 project_id。

    - admin: 可访问任意 project；project_id 必填（除非 allow_admin_all=True 允许空=全部）。
    - project_admin: 可读写，但仅限自己令牌绑定的 project。
    - project_reader: 只读；写操作 403；仅限自己的 project。
    - 其它(reader/None): 403。
    非 admin 且 requested 为空时，回退为令牌绑定的 project_id。
    请求的 project_id 与令牌绑定的不一致 → 403（杜绝跨项目越权）。
    """
    role, token_pid = _role_and_project(request)
    if role == "admin":
        if not requested_project_id and not allow_admin_all:
            raise HTTPException(status_code=400, detail="project_id 必填")
        return requested_project_id
    if role == "project_admin":
        eff = requested_project_id or token_pid
        if not eff or eff != token_pid:
            raise HTTPException(status_code=403, detail="无该项目访问权限")
        return eff
    if role == "project_reader":
        if write:
            raise HTTPException(status_code=403, detail="project_reader 只读，无写入权限")
        eff = requested_project_id or token_pid
        if not eff or eff != token_pid:
            raise HTTPException(status_code=403, detail="无该项目访问权限")
        return eff
    raise HTTPException(status_code=403, detail="无访问权限")


@router.get("/documents")
def list_documents(request: Request, project_id: str = "", limit: int = 100, offset: int = 0,
                   service: KnowledgeService = Depends(get_knowledge_service)):
    pid = _enforce_project_access(request, project_id, allow_admin_all=True)
    result = service.list_documents(
        project_id=pid or None, limit=limit, offset=offset)
    return ApiResponse.ok(result)


@router.post("/ingest")
async def ingest(
    request: Request,
    files: Optional[List[UploadFile]] = File(None),
    text: str = Form(default=""),
    project_id: str = Form(default=""),
    asset_id: str = Form(default=""),
    title: str = Form(default=""),
    source: str = Form(default="upload"),
    doc_id: str = Form(default=""),
    service: KnowledgeService = Depends(get_knowledge_service),
):
    # 写入鉴权：admin 任意项目；project_admin 仅自己项目；其它 403
    pid = _enforce_project_access(request, project_id, write=True)
    role, _ = _role_and_project(request)
    # 自动建 project（仅 admin；project_admin 的项目已存在）
    if pid and role == "admin" and not service.repo.get_project(pid):
        service.repo.create_project(pid, title or pid, {}, {})

    units = []
    parse_errors = []
    for f in (files or []):
        content = await f.read()
        parsed = parse_document(content, f.filename or "unknown")
        if parsed["success"]:
            units.append((title or f.filename or "unknown", parsed["text"],
                          parsed.get("doc_format")))
        else:
            parse_errors.append({"filename": f.filename, "error": parsed["error"]})
    if text and text.strip():
        units.append((title or "text", text, "text"))
    if not units:
        return ApiResponse.error("请提供文件或文本内容", code=400)
    docs = []
    for disp_title, t, doc_format in units:
        res = service.ingest_text(
            t, project_id=pid, asset_id=asset_id,
            title=disp_title, source=source, doc_format=doc_format or "text",
            doc_id=doc_id or None)
        docs.append({
            "doc_id": res.get("doc_id"),
            "title": disp_title,
            "status": res.get("status", "skipped"),
            "version": res.get("version"),
        })
    if parse_errors:
        return ApiResponse.partial(
            data={"docs": docs, "count": len(docs)},
            message="部分文件解析失败", errors=parse_errors)
    return ApiResponse.ok({"docs": docs, "count": len(docs)})


class RetrieveRequest(BaseModel):
    query: str
    top_k: int = 5
    project_id: str = ""
    rerank: Optional[bool] = None
    rerank_top_n: Optional[int] = None


@router.post("/retrieve")
def retrieve(request: Request, req: RetrieveRequest,
             service: KnowledgeService = Depends(get_knowledge_service)):
    if not req.query or not req.query.strip():
        return ApiResponse.error("请提供查询语句", code=400)
    pid = _enforce_project_access(request, req.project_id)
    results = service.retrieve(
        req.query, top_k=req.top_k, project_id=pid,
        rerank=req.rerank, rerank_top_n=req.rerank_top_n)
    return ApiResponse.ok({"results": results})


class AskRequest(BaseModel):
    question: str
    project_id: str = ""
    top_k: int = 5
    rerank: Optional[bool] = None
    rerank_top_n: Optional[int] = None


class EvaluateRequest(BaseModel):
    gold: Optional[List[dict]] = None
    top_k: int = 5
    with_faithfulness: bool = False


@router.post("/ask")
def ask(request: Request, req: AskRequest,
        service: KnowledgeService = Depends(get_knowledge_service)):
    if not req.question or not req.question.strip():
        return ApiResponse.error("请提供问题", code=400)
    pid = _enforce_project_access(request, req.project_id)
    from app.knowledge.answer import RAGAnswerGenerator
    gen = RAGAnswerGenerator(service=service)
    result = gen.answer(
        req.question, project_id=pid, top_k=req.top_k,
        rerank=req.rerank, rerank_top_n=req.rerank_top_n)
    return ApiResponse.ok(result)


@router.post("/evaluate")
def evaluate(req: EvaluateRequest, service: KnowledgeService = Depends(get_knowledge_service)):
    from app.knowledge.eval import RAGEvaluator
    try:
        gold = req.gold if req.gold else RAGEvaluator.DEFAULT_GOLD
        if not gold:
            return ApiResponse.error("gold 为空", code=400)
        ev = RAGEvaluator()
        metrics = ev.evaluate(service, gold, top_k=req.top_k, with_faithfulness=req.with_faithfulness)
        return ApiResponse.ok(metrics)
    except ValueError as e:
        return ApiResponse.error(str(e), code=400)


@router.delete("/documents/{doc_id}")
def delete_document(
    doc_id: str,
    service: KnowledgeService = Depends(get_knowledge_service),
    _admin: bool = Depends(require_admin),
):
    if not service.delete_document(doc_id):
        return ApiResponse.not_found("文档不存在")
    return ApiResponse.ok({"deleted": doc_id})
