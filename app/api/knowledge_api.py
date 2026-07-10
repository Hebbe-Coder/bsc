"""知识库 API 端点：上传/文本灌入、列出、检索、删除。"""
from __future__ import annotations
import hashlib
import secrets
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
    - reader（全局 API_KEY_READER）: 系统级只读；可读任意 project，但写操作 403；project_id 必填。
    - project_admin: 可读写，但仅限自己令牌绑定的 project。
    - project_reader: 只读；写操作 403；仅限自己的 project。
    - 其它(None): 403。
    非 admin 且 requested 为空时，回退为令牌绑定的 project_id。
    请求的 project_id 与令牌绑定的不一致 → 403（杜绝跨项目越权）。
    """
    role, token_pid = _role_and_project(request)
    if role == "admin":
        if not requested_project_id and not allow_admin_all:
            raise HTTPException(status_code=400, detail="project_id 必填")
        return requested_project_id
    if role == "reader":
        if write:
            raise HTTPException(status_code=403, detail="只读密钥（reader）无写入权限")
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


# ---- T6：仅限 admin 的「项目 / 项目密钥签发」端点 ----

class CreateProjectRequest(BaseModel):
    name: str
    metadata: dict = {}


class IssueKeyRequest(BaseModel):
    role: str = "project_reader"
    label: str = ""


@router.post("/projects")
def create_project(
    req: CreateProjectRequest,
    _admin: bool = Depends(require_admin),
    service: KnowledgeService = Depends(get_knowledge_service),
):
    """admin 创建项目并一次性返回 project_admin 明文 key。"""
    pid = f"proj_{secrets.token_hex(6)}"
    service.repo.create_project(pid, req.name, req.metadata, {})
    plaintext = f"sk-{secrets.token_urlsafe(24)}"
    service.repo.create_project_key(
        hashlib.sha256(plaintext.encode()).hexdigest(), pid, "project_admin", "owner")
    return ApiResponse.ok({"project_id": pid, "key": plaintext, "role": "project_admin"})


@router.post("/projects/{project_id}/keys")
def issue_project_key(
    project_id: str,
    req: IssueKeyRequest,
    _admin: bool = Depends(require_admin),
    service: KnowledgeService = Depends(get_knowledge_service),
):
    """admin 为已存在项目签发 key。"""
    if service.repo.get_project(project_id) is None:
        return ApiResponse.not_found("项目不存在")
    if req.role not in ("project_admin", "project_reader"):
        return ApiResponse.error("role 须为 project_admin/project_reader", code=400)
    plaintext = f"sk-{secrets.token_urlsafe(24)}"
    service.repo.create_project_key(
        hashlib.sha256(plaintext.encode()).hexdigest(), project_id, req.role, req.label)
    return ApiResponse.ok({"project_id": project_id, "key": plaintext, "role": req.role})


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


class BenchmarkGoldRequest(BaseModel):
    project_id: Optional[str] = None
    query: str
    expected_chunk_ids: List[str] = []
    notes: str = ""


@router.post("/evaluate/benchmark/gold")
def add_benchmark_gold(
    req: BenchmarkGoldRequest,
    service: KnowledgeService = Depends(get_knowledge_service),
    _admin: bool = Depends(require_admin),
):
    """admin 注入一条常驻 gold benchmark 记录（用于 before/after rerank 对比）。"""
    service.repo.add_benchmark(req.project_id, req.query, req.expected_chunk_ids, req.notes)
    return ApiResponse.ok({"added": True})


@router.get("/evaluate/benchmark")
def benchmark(
    project_id: Optional[str] = None,
    top_k: int = 5,
    rerank_top_n: Optional[int] = None,
    service: KnowledgeService = Depends(get_knowledge_service),
    _admin: bool = Depends(require_admin),
):
    """admin 运行常驻 gold 的 before/after rerank 对比，并报告项目隔离情况。"""
    gold = service.repo.list_benchmarks(project_id)
    if not gold:
        return ApiResponse.error("无常驻 gold（请先 POST /evaluate/benchmark/gold）", code=400)
    from app.knowledge.eval import RAGEvaluator
    ev = RAGEvaluator()
    try:
        report = ev.compare_before_after(
            service, gold, top_k=top_k, project_id=project_id, rerank_top_n=rerank_top_n)
    except ValueError as e:
        return ApiResponse.error(str(e), code=400)
    isolation_ok = True
    if project_id:
        for item in gold:
            got = {r["chunk_id"] for r in service.retrieve(item["query"], top_k=top_k, project_id=project_id)}
            for cid in got:
                row = service.repo._execute(
                    "SELECT d.project_id FROM knowledge_chunks c "
                    "JOIN knowledge_docs d ON c.doc_id=d.id WHERE c.id=?",
                    (cid,)).fetchone()
                if row and row["project_id"] != project_id:
                    isolation_ok = False
    report["isolation_ok"] = isolation_ok
    report["gold_count"] = len(gold)
    return ApiResponse.ok(report)


@router.delete("/documents/{doc_id}")
def delete_document(
    doc_id: str,
    service: KnowledgeService = Depends(get_knowledge_service),
    _admin: bool = Depends(require_admin),
):
    if not service.delete_document(doc_id):
        return ApiResponse.not_found("文档不存在")
    return ApiResponse.ok({"deleted": doc_id})
