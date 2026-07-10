"""知识库 WebSocket 流式问答：首帧 sources + (T10) 逐 token + end；支持 cancel。"""
from __future__ import annotations
import asyncio
import logging
from typing import Dict, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.knowledge.service import KnowledgeService
from app.middleware.auth import resolve_knowledge_auth

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Knowledge-WS"])


class ConnectionManager:
    def __init__(self):
        self.cancel_events: Dict[str, asyncio.Event] = {}

    def new_cancel(self, rid: str) -> asyncio.Event:
        ev = asyncio.Event()
        self.cancel_events[rid] = ev
        return ev

    def cancel(self, rid: str):
        ev = self.cancel_events.get(rid)
        if ev:
            ev.set()

    def drop(self, rid: str):
        self.cancel_events.pop(rid, None)


manager = ConnectionManager()


def _auth_token(websocket: WebSocket) -> Optional[str]:
    auth = websocket.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return websocket.query_params.get("token")


@router.websocket("/ws/knowledge/ask")
async def ws_ask(websocket: WebSocket):
    await websocket.accept()
    repo = KnowledgeService().repo
    try:
        token = _auth_token(websocket)
        auth = resolve_knowledge_auth(token, repo=repo) if token else None
        if auth is None:
            await websocket.close(code=1008)
            return
        role, project_id = auth
        while True:
            data = await websocket.receive_json()
            mtype = data.get("type")
            if mtype == "ping":
                await websocket.send_json({"type": "pong"})
                continue
            if mtype == "cancel":
                manager.cancel(data.get("request_id", ""))
                continue
            if mtype == "ask":
                await _handle_ask(websocket, data, role, project_id, repo)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("ws_ask error: %s", e)


async def _handle_ask(websocket, data, role, project_id, repo):
    rid = data.get("request_id") or "r1"
    pid = data.get("project_id") or project_id
    # 跨项目越权拦截：非 admin 只能访问自己令牌绑定的 project
    if role != "admin" and pid != project_id:
        await websocket.send_json({"type": "error", "request_id": rid,
                                   "data": "无该项目访问权限"})
        return
    if not pid:
        await websocket.send_json({"type": "error", "request_id": rid,
                                   "data": "project_id 必填"})
        return
    svc = KnowledgeService(repo=repo)
    retrieved = svc.retrieve(data.get("query", ""), top_k=data.get("top_k", 5),
                             project_id=pid, rerank=data.get("rerank"),
                             rerank_top_n=data.get("rerank_top_n"))
    await websocket.send_json({"type": "sources", "request_id": rid, "data": retrieved})
    cancel = manager.new_cancel(rid)
    answer_parts = []
    try:
        from app.services import async_llm_service as _allm
        system, user = _build_prompts(data.get("query", ""), retrieved)
        async for token in _allm.get_async_llm_service().async_stream_chat(
                system_prompt=system, user_prompt=user):
            if cancel.is_set():
                break
            answer_parts.append(token)
            await websocket.send_json({"type": "token", "request_id": rid, "data": token})
        answer = "".join(answer_parts)
        citations = [{"chunk_id": c.get("chunk_id"), "doc_title": c.get("doc_title")}
                     for c in retrieved]
        await websocket.send_json({"type": "end", "request_id": rid,
                                   "data": {"answer": answer, "citations": citations,
                                            "metrics": {"citation_rate": 0.0}}})
    except Exception as e:
        logger.warning("ws stream failed: %s", e)
        await websocket.send_json({"type": "error", "request_id": rid, "data": str(e)})
    finally:
        manager.drop(rid)


def _build_prompts(query: str, chunks):
    ctx = "\n\n".join(f"[{i+1}] {(c.get('content') or '')[:200]}" for i, c in enumerate(chunks))
    system = "你是知识库问答助手，基于检索片段用[n]引用作答。"
    user = f"问题：{query}\n\n检索片段：\n{ctx}"
    return system, user
