"""知识库 WebSocket 流式问答：首帧 sources + 逐 token + end；支持 cancel。

并发模型：主消息循环只负责读消息并分发；每个 `ask` 的检索+流式在**后台 task** 中执行，
因此主循环可持续接收 `cancel`/`ping` 而不被流式阻塞（这是 cancel 能真正生效的前提）。
取消状态按**每连接**作用域管理（避免不同连接用相同 request_id 时互相串扰）。
"""
from __future__ import annotations
import asyncio
import logging
from typing import Dict, Optional, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.knowledge.service import KnowledgeService
from app.middleware.auth import resolve_knowledge_auth

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Knowledge-WS"])


class ConnectionState:
    """单个 WS 连接的取消事件与后台任务集合（连接级隔离，非全局）。"""

    def __init__(self):
        self.cancels: Dict[str, asyncio.Event] = {}
        self.tasks: Set[asyncio.Task] = set()

    def new_cancel(self, rid: str) -> asyncio.Event:
        ev = asyncio.Event()
        self.cancels[rid] = ev
        return ev

    def cancel(self, rid: str):
        ev = self.cancels.get(rid)
        if ev:
            ev.set()

    def drop(self, rid: str):
        self.cancels.pop(rid, None)

    def spawn(self, coro):
        task = asyncio.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def cleanup(self):
        for task in list(self.tasks):
            task.cancel()
        if self.tasks:
            await asyncio.gather(*list(self.tasks), return_exceptions=True)
        self.cancels.clear()


def _auth_token(websocket: WebSocket) -> Optional[str]:
    auth = websocket.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return websocket.query_params.get("token")


@router.websocket("/ws/knowledge/ask")
async def ws_ask(websocket: WebSocket):
    await websocket.accept()
    repo = KnowledgeService().repo
    conn = ConnectionState()
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
                conn.cancel(data.get("request_id", ""))
                continue
            if mtype == "ask":
                # 后台执行，主循环立即返回继续读消息（cancel 才能在流中生效）
                conn.spawn(_handle_ask(websocket, data, role, project_id, repo, conn))
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("ws_ask error: %s", e)
    finally:
        await conn.cleanup()


async def _handle_ask(websocket, data, role, project_id, repo, conn: ConnectionState):
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
    loop = asyncio.get_running_loop()
    # 在 worker 线程内构造 KnowledgeService，使 SQLite 连接线程本地，
    # 避免同一 WS 上并发 ask 共享连接导致跨线程竞态（run_in_executor 路径）。
    retrieved = await loop.run_in_executor(
        None,
        lambda: KnowledgeService().retrieve(
            data.get("query", ""), top_k=data.get("top_k", 5),
            project_id=pid, rerank=data.get("rerank"),
            rerank_top_n=data.get("rerank_top_n")))
    await websocket.send_json({"type": "sources", "request_id": rid, "data": retrieved})
    cancel = conn.new_cancel(rid)
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
                                            "cancelled": cancel.is_set(),
                                            "metrics": {"citation_rate": 0.0}}})
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.warning("ws stream failed: %s", e)
        try:
            await websocket.send_json({"type": "error", "request_id": rid, "data": str(e)})
        except Exception:
            pass
    finally:
        conn.drop(rid)


def _build_prompts(query: str, chunks):
    ctx = "\n\n".join(f"[{i+1}] {(c.get('content') or '')[:200]}" for i, c in enumerate(chunks))
    system = "你是知识库问答助手，基于检索片段用[n]引用作答。"
    user = f"问题：{query}\n\n检索片段：\n{ctx}"
    return system, user
