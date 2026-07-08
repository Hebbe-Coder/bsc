"""PRD Editor API - 实时预览和交互式编辑接口"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Union
import logging
import asyncio
import json

from app.api.response import ApiResponse
from app.core.dialog_engine import DialogEngine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/prd/editor", tags=["PRD Editor"])


class SectionUpdateRequest(BaseModel):
    """章节更新请求"""
    title: Optional[str] = Field(None, description="章节标题")
    content: Optional[str] = Field(None, description="章节内容（Markdown格式）")
    level: Optional[int] = Field(None, description="标题级别（1-6）", ge=1, le=6)


class SectionCreateRequest(BaseModel):
    """章节创建请求"""
    title: str = Field(..., description="章节标题")
    content: str = Field("", description="章节内容（Markdown格式）")
    level: int = Field(1, description="标题级别（1-6）", ge=1, le=6)
    parent_id: Optional[str] = Field(None, description="父章节ID")


class BatchUpdateRequest(BaseModel):
    """批量更新请求"""
    changes: List[Dict[str, Any]] = Field(..., description="变更列表")


class EditorSessionManager:
    """编辑器会话管理器"""
    
    _sessions: Dict[str, Dict[str, Any]] = {}
    _listeners: Dict[str, List[asyncio.Queue]] = {}
    
    @classmethod
    def get_document(cls, session_id: str) -> Optional[Any]:
        """获取会话的PRD文档"""
        return cls._sessions.get(session_id, {}).get("document")
    
    @classmethod
    def set_document(cls, session_id: str, document: Any):
        """设置会话的PRD文档"""
        cls._sessions[session_id] = {"document": document}
    
    @classmethod
    def register_listener(cls, session_id: str, queue: asyncio.Queue):
        """注册预览监听器"""
        if session_id not in cls._listeners:
            cls._listeners[session_id] = []
        cls._listeners[session_id].append(queue)
    
    @classmethod
    def unregister_listener(cls, session_id: str, queue: asyncio.Queue):
        """注销预览监听器"""
        if session_id in cls._listeners:
            cls._listeners[session_id].remove(queue)
            if not cls._listeners[session_id]:
                del cls._listeners[session_id]
    
    @classmethod
    async def broadcast_update(cls, session_id: str, update_type: str, data: Dict[str, Any]):
        """广播更新到所有监听器"""
        message = json.dumps({
            "type": update_type,
            "data": data,
            "timestamp": asyncio.get_event_loop().time()
        })
        
        if session_id in cls._listeners:
            for queue in cls._listeners[session_id]:
                try:
                    await queue.put(message)
                except asyncio.CancelledError:
                    pass


async def get_dialog_engine():
    """获取对话引擎依赖"""
    from app.core.dialog_engine import DialogEngine
    return DialogEngine()


@router.get("/{session_id}/sections", summary="获取PRD章节树")
async def get_sections(session_id: str, engine: DialogEngine = Depends(get_dialog_engine)):
    """
    获取指定会话的PRD章节树结构，用于编辑器渲染
    
    返回章节的树形结构，包含每个章节的ID、标题、内容、层级和子章节
    """
    session = engine.get_session_status(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    prd_text = session.get("prd_text", "")
    if not prd_text:
        return ApiResponse.ok({"sections": [], "document_id": session_id})
    
    from app.core.prd_document import PRDDocumentManager
    
    document = PRDDocumentManager.parse_markdown(prd_text)
    EditorSessionManager.set_document(session_id, document)
    
    return ApiResponse.ok({
        "sections": document.get_section_tree(),
        "document_id": document.id,
        "title": document.title,
        "industry": document.industry,
        "section_count": len(document.sections),
    })


@router.get("/{session_id}/sections/{section_id}", summary="获取单个章节")
async def get_section(session_id: str, section_id: str, engine: DialogEngine = Depends(get_dialog_engine)):
    """获取指定章节的详细信息"""
    document = EditorSessionManager.get_document(session_id)
    
    if not document:
        session = engine.get_session_status(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="会话不存在")
        
        prd_text = session.get("prd_text", "")
        if not prd_text:
            raise HTTPException(status_code=404, detail="PRD文档不存在")
        
        from app.core.prd_document import PRDDocumentManager
        document = PRDDocumentManager.parse_markdown(prd_text)
        EditorSessionManager.set_document(session_id, document)
    
    section = document.find_section(section_id)
    if not section:
        raise HTTPException(status_code=404, detail="章节不存在")
    
    return ApiResponse.ok({
        "section": section.model_dump(),
        "path": _get_section_path(document, section_id),
    })


def _get_section_path(document, section_id: str) -> List[str]:
    """获取章节路径（从根到该章节的标题列表）"""
    path = []
    
    def find_path(sections, target_id):
        for section in sections:
            if section.id == target_id:
                path.append(section.title)
                return True
            if find_path(section.children, target_id):
                path.append(section.title)
                return True
        return False
    
    find_path(document.sections, section_id)
    return list(reversed(path))


@router.put("/{session_id}/sections/{section_id}", summary="更新章节")
async def update_section(session_id: str, section_id: str, req: SectionUpdateRequest):
    """
    更新指定章节的内容
    
    修改后会自动触发实时预览更新
    """
    document = EditorSessionManager.get_document(session_id)
    
    if not document:
        raise HTTPException(status_code=404, detail="文档未加载，请先调用GET /sections")
    
    section = document.find_section(section_id)
    if not section:
        raise HTTPException(status_code=404, detail="章节不存在")
    
    data = req.dict(exclude_unset=True)
    if data:
        document.update_section(section_id, **data)
        
        await EditorSessionManager.broadcast_update(session_id, "section_updated", {
            "section_id": section_id,
            "title": section.title,
            "content": section.content,
            "level": section.level,
        })
    
    return ApiResponse.ok({
        "section": section.model_dump(),
        "updated": bool(data),
    })


@router.post("/{session_id}/sections", summary="添加新章节")
async def add_section(session_id: str, req: SectionCreateRequest):
    """
    添加新章节到PRD文档
    
    支持添加顶层章节或子章节（通过parent_id指定父章节）
    """
    document = EditorSessionManager.get_document(session_id)
    
    if not document:
        raise HTTPException(status_code=404, detail="文档未加载，请先调用GET /sections")
    
    section = document.add_section(
        title=req.title,
        level=req.level,
        content=req.content,
        parent_id=req.parent_id,
    )
    
    await EditorSessionManager.broadcast_update(session_id, "section_added", {
        "section_id": section.id,
        "title": section.title,
        "level": section.level,
        "parent_id": req.parent_id,
    })
    
    return ApiResponse.ok({
        "section": section.model_dump(),
        "message": "章节添加成功",
    })


@router.delete("/{session_id}/sections/{section_id}", summary="删除章节")
async def delete_section(session_id: str, section_id: str):
    """
    删除指定章节及其所有子章节
    
    删除后会自动触发实时预览更新
    """
    document = EditorSessionManager.get_document(session_id)
    
    if not document:
        raise HTTPException(status_code=404, detail="文档未加载，请先调用GET /sections")
    
    success = document.delete_section(section_id)
    
    if success:
        await EditorSessionManager.broadcast_update(session_id, "section_deleted", {
            "section_id": section_id,
        })
        return ApiResponse.ok({"message": "章节删除成功"})
    else:
        raise HTTPException(status_code=404, detail="章节不存在")


@router.post("/{session_id}/sections/reorder", summary="重新排序章节")
async def reorder_sections(session_id: str, section_ids: List[str]):
    """
    重新排序顶层章节
    
    根据传入的章节ID列表顺序重新排列顶层章节
    """
    document = EditorSessionManager.get_document(session_id)
    
    if not document:
        raise HTTPException(status_code=404, detail="文档未加载，请先调用GET /sections")
    
    success = document.reorder_sections(section_ids)
    
    if success:
        await EditorSessionManager.broadcast_update(session_id, "sections_reordered", {
            "section_ids": section_ids,
        })
        return ApiResponse.ok({"message": "章节排序成功"})
    else:
        return ApiResponse.error("排序失败")


@router.post("/{session_id}/batch", summary="批量更新章节")
async def batch_update(session_id: str, req: BatchUpdateRequest):
    """
    批量应用多个编辑变更
    
    支持的操作类型：add（添加）、update（更新）、delete（删除）、reorder（排序）
    """
    document = EditorSessionManager.get_document(session_id)
    
    if not document:
        raise HTTPException(status_code=404, detail="文档未加载，请先调用GET /sections")
    
    from app.core.prd_document import PRDDocumentManager
    
    document = PRDDocumentManager.merge_changes(document, req.changes)
    EditorSessionManager.set_document(session_id, document)
    
    await EditorSessionManager.broadcast_update(session_id, "batch_updated", {
        "change_count": len(req.changes),
    })
    
    return ApiResponse.ok({
        "sections": document.get_section_tree(),
        "change_count": len(req.changes),
        "message": "批量更新成功",
    })


@router.get("/{session_id}/markdown", summary="获取PRD Markdown全文")
async def get_markdown(session_id: str):
    """获取当前PRD文档的完整Markdown内容"""
    document = EditorSessionManager.get_document(session_id)
    
    if not document:
        raise HTTPException(status_code=404, detail="文档未加载，请先调用GET /sections")
    
    markdown = document.to_markdown()
    
    return ApiResponse.ok({
        "markdown": markdown,
        "length": len(markdown),
    })


@router.get("/{session_id}/preview", summary="实时预览（SSE）")
async def preview(session_id: str):
    """
    实时预览PRD文档（Server-Sent Events）
    
    客户端订阅此端点后，当文档发生任何变更时会自动收到更新通知
    返回的HTML内容可直接渲染为PRD预览页面
    
    使用方式：
    ```javascript
    const eventSource = new EventSource('/prd/editor/{session_id}/preview');
    eventSource.onmessage = function(event) {
        const data = JSON.parse(event.data);
        if (data.type === 'preview_update') {
            document.getElementById('preview').innerHTML = data.data.html;
        }
    };
    ```
    """
    document = EditorSessionManager.get_document(session_id)
    
    if not document:
        raise HTTPException(status_code=404, detail="文档未加载，请先调用GET /sections")
    
    async def event_generator():
        queue = asyncio.Queue()
        EditorSessionManager.register_listener(session_id, queue)
        
        try:
            html = document.to_html()
            yield f"data: {json.dumps({'type': 'preview_update', 'data': {'html': html}})}\n\n"
            
            while True:
                message = await queue.get()
                if message is None:
                    break
                
                parsed = json.loads(message)
                document = EditorSessionManager.get_document(session_id)
                
                if document and parsed.get("type") in ["section_updated", "section_added", "section_deleted", "sections_reordered", "batch_updated"]:
                    html = document.to_html()
                    yield f"data: {json.dumps({'type': 'preview_update', 'data': {'html': html, 'change_type': parsed['type']}})}\n\n"
                else:
                    yield f"data: {message}\n\n"
        finally:
            EditorSessionManager.unregister_listener(session_id, queue)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.get("/{session_id}/preview/html", summary="获取预览HTML")
async def get_preview_html(session_id: str):
    """获取当前PRD文档的HTML预览内容（非SSE版本）"""
    document = EditorSessionManager.get_document(session_id)
    
    if not document:
        raise HTTPException(status_code=404, detail="文档未加载，请先调用GET /sections")
    
    html = document.to_html()
    
    return Response(content=html, media_type="text/html")


@router.post("/{session_id}/export/{format}", summary="导出PRD文档")
async def export_prd(session_id: str, format: str, engine: DialogEngine = Depends(get_dialog_engine)):
    """
    导出PRD文档为指定格式
    
    支持的格式：
    - pdf: PDF文档
    - ppt: PPT演示文稿
    - word: Word文档
    - markdown: Markdown文件
    - html: HTML文件
    
    返回文件下载响应
    """
    document = EditorSessionManager.get_document(session_id)
    
    if not document:
        session = engine.get_session_status(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="会话不存在")
        
        prd_text = session.get("prd_text", "")
        if not prd_text:
            raise HTTPException(status_code=404, detail="PRD文档不存在")
        
        from app.core.prd_document import PRDDocumentManager
        document = PRDDocumentManager.parse_markdown(prd_text)
    
    format = format.lower()
    exporters = {
        "pdf": _export_pdf,
        "ppt": _export_ppt,
        "word": _export_word,
        "markdown": _export_markdown,
        "html": _export_html,
    }
    
    if format not in exporters:
        raise HTTPException(status_code=400, detail=f"不支持的导出格式：{format}")
    
    return await exporters[format](document)


async def _export_pdf(document):
    """导出为PDF"""
    from exporters.prd_exporters import PRDPDFExporter
    
    exporter = PRDPDFExporter()
    pdf_bytes = exporter.export(document)
    
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={document.title}.pdf",
        },
    )


async def _export_ppt(document):
    """导出为PPT"""
    from exporters.prd_exporters import PRDPPTExporter
    
    exporter = PRDPPTExporter()
    ppt_path = exporter.export(document)
    
    with open(ppt_path, "rb") as f:
        ppt_bytes = f.read()
    
    import os
    os.remove(ppt_path)
    
    return Response(
        content=ppt_bytes,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={
            "Content-Disposition": f"attachment; filename={document.title}.pptx",
        },
    )


async def _export_word(document):
    """导出为Word"""
    from exporters.prd_exporters import PRDWordExporter
    
    exporter = PRDWordExporter()
    word_path = exporter.export(document)
    
    with open(word_path, "rb") as f:
        word_bytes = f.read()
    
    import os
    os.remove(word_path)
    
    return Response(
        content=word_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f"attachment; filename={document.title}.docx",
        },
    )


async def _export_markdown(document):
    """导出为Markdown"""
    markdown = document.to_markdown()
    
    return Response(
        content=markdown.encode("utf-8"),
        media_type="text/markdown",
        headers={
            "Content-Disposition": f"attachment; filename={document.title}.md",
        },
    )


async def _export_html(document):
    """导出为HTML"""
    html = document.to_html()
    
    return Response(
        content=html.encode("utf-8"),
        media_type="text/html",
        headers={
            "Content-Disposition": f"attachment; filename={document.title}.html",
        },
    )


@router.post("/{session_id}/save", summary="保存PRD文档")
async def save_prd(session_id: str, engine: DialogEngine = Depends(get_dialog_engine)):
    """
    保存当前编辑的PRD文档到会话
    
    将编辑后的文档转换为Markdown格式并保存到数据库
    """
    document = EditorSessionManager.get_document(session_id)
    
    if not document:
        raise HTTPException(status_code=404, detail="文档未加载")
    
    markdown = document.to_markdown()
    
    from app.core.preference_db import get_preference_db
    db = get_preference_db()
    
    success = db.update_dialog_session(session_id, prd_text=markdown)
    
    if success:
        return ApiResponse.ok({"message": "保存成功", "length": len(markdown)})
    else:
        return ApiResponse.error("保存失败")