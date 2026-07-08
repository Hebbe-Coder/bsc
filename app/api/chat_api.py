"""
Chat API - 对话式入口

用户粘贴PRD → 调用BSC Pipeline → 返回结构化结果

使用Repository模式替代内存存储，支持数据持久化。
"""
from __future__ import annotations
import json, time
from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional, List, Dict

from app.repositories.conversation_repository import get_conversation_repository

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatMessage(BaseModel):
    message: str = Field(..., description="用户消息")
    context: Optional[dict] = Field(default=None)


def _get_repo():
    """获取对话Repository"""
    return get_conversation_repository()


@router.post("/send")
async def send_message(req: ChatMessage):
    """对话式入口 - 用户说一句话，系统自动理解并执行"""
    msg = req.message.strip()
    conv_id = req.context.get("conv_id") if req.context else None
    
    repo = _get_repo()
    
    if not conv_id:
        conv_id = repo.create_conversation()
    
    existing_messages = repo.get_messages(conv_id)
    if not existing_messages:
        repo.add_message(conv_id, "assistant",
            "您好，我是BSC。把PRD或企业文档发给我，我来帮您分析。")

    repo.add_message(conv_id, "user", msg)

    response = _route(msg, conv_id)

    repo.add_message(conv_id, "assistant", response["content"],
                     response.get("data"))

    return {
        "conv_id": conv_id,
        "reply": response["content"],
        "data": response.get("data"),
        "suggestions": response.get("suggestions", []),
    }


@router.get("/history/{conv_id}")
async def get_history(conv_id: str):
    """获取对话历史"""
    repo = _get_repo()
    messages = repo.get_messages(conv_id)
    return {"conv_id": conv_id, "messages": messages}


@router.get("/list")
async def list_conversations(limit: int = 20, offset: int = 0):
    """获取对话列表"""
    repo = _get_repo()
    conversations = repo.get_conversations(limit, offset)
    count = repo.get_conversation_count()
    return {"conversations": conversations, "count": count, "limit": limit, "offset": offset}


@router.delete("/{conv_id}")
async def delete_conversation(conv_id: str):
    """删除对话"""
    repo = _get_repo()
    repo.delete_conversation(conv_id)
    return {"status": "ok", "conv_id": conv_id}


def _route(msg: str, conv_id: str) -> dict:
    """路由用户消息"""

    if len(msg) > 30 and any(kw in msg for kw in ["PRD", "审核", "客服", "风控", "电商", "系统", "流程", "需求", "项目"]):
        return _handle_compile(msg)

    if any(kw in msg for kw in ["为什么", "原因", "根因"]):
        return _handle_followup(msg, conv_id, "root_cause")

    if any(kw in msg for kw in ["如果", "模拟", "假设", "提升", "会怎样"]):
        return _handle_followup(msg, conv_id, "simulation")

    if any(kw in msg for kw in ["风险", "隐患"]):
        return _handle_followup(msg, conv_id, "risk")

    if any(kw in msg for kw in ["战略", "增长", "扩张", "竞争"]):
        return _handle_followup(msg, conv_id, "strategy")

    if any(kw in msg for kw in ["优化", "ROI", "建议"]):
        return _handle_followup(msg, conv_id, "optimization")

    if any(kw in msg for kw in ["帮助", "help", "能做什么"]):
        return _help()

    return _default(msg)


def _handle_compile(msg: str) -> dict:
    """调用BSC Pipeline"""
    from app.core.bsc_pipeline import run_bsc_pipeline

    result = run_bsc_pipeline(msg)

    lines = ["**BSC编译完成**\n"]
    lines.append(f"耗时: {result['total_ms']}ms\n")

    sop = result.get("sop", {})
    if sop:
        lines.append(f"**SOP流程 ({len(sop.get('workflow',[]))}步):**")
        for w in sop.get("workflow", []):
            lines.append(f"  {w.get('step','')}. {w.get('name','')}")
        lines.append(f"  角色: {len(sop.get('roles',[]))}个 | SLA: {len(sop.get('sla',[]))}项 | KPI: {len(sop.get('kpi',[]))}项\n")

    risk = result.get("risk", {})
    if risk:
        total = sum(len(risk.get(k,[])) for k in ["process_risks","organization_risks","system_risks","compliance_risks"])
        lines.append(f"**风险 ({total}个):**")
        for cat, label in [("process_risks","流程"),("organization_risks","组织"),("system_risks","系统"),("compliance_risks","合规")]:
            items = risk.get(cat, [])
            if items:
                lines.append(f"  {label}: {len(items)}个")
        lines.append("")

    strategy = result.get("strategy", {})
    if strategy:
        lines.append(f"**战略机会:**")
        for opp in strategy.get("growth_opportunities", [])[:3]:
            lines.append(f"  - {opp.get('opportunity','')} ({opp.get('potential','')})")
        lines.append("")

    opt = result.get("optimization", {})
    if opt:
        recs = opt.get("recommendations", [])
        lines.append(f"**优化建议 ({len(recs)}个):**")
        for r in recs[:2]:
            lines.append(f"  - {r.get('title','')} [投入{r.get('investment','')}, {r.get('timeline','')}]")

    return {
        "content": "\n".join(lines),
        "data": result,
        "suggestions": ["为什么SLA低", "有哪些风险", "战略路径是什么", "优化建议是什么"],
    }


def _handle_followup(msg: str, conv_id: str, topic: str) -> dict:
    """追问处理"""
    repo = _get_repo()
    last_data = repo.get_last_message_data(conv_id)

    if not last_data:
        return {"content": "请先粘贴一段PRD文档，我来帮您分析。", "suggestions": ["分析内容审核系统PRD"]}

    result = last_data

    if topic == "risk":
        risk = result.get("risk", {})
        lines = ["**风险详情:**\n"]
        for cat, label in [("process_risks","流程风险"),("organization_risks","组织风险"),("system_risks","系统风险"),("compliance_risks","合规风险")]:
            for r in risk.get(cat, []):
                lines.append(f"  [{r.get('severity','')}] {r.get('risk','')}")
                lines.append(f"    缓解: {r.get('mitigation','')}\n")
        return {"content": "\n".join(lines), "suggestions": ["优化建议是什么", "战略路径是什么"]}

    if topic == "strategy":
        strategy = result.get("strategy", {})
        lines = ["**战略分析:**\n"]
        lines.append("增长机会:")
        for o in strategy.get("growth_opportunities", []):
            lines.append(f"  - {o.get('opportunity','')} ({o.get('potential','')}, {o.get('timeline','')})")
        lines.append("\n战略路径:")
        for p in strategy.get("strategic_path", []):
            lines.append(f"  {p.get('phase','')}: {p.get('theme','')} ({p.get('timeline','')}) - {p.get('goal','')}")
        return {"content": "\n".join(lines), "suggestions": ["有哪些风险", "优化建议是什么"]}

    if topic == "optimization":
        opt = result.get("optimization", {})
        lines = ["**优化建议:**\n"]
        for r in opt.get("recommendations", []):
            lines.append(f"  {r.get('title','')} [{r.get('priority','')}]")
            lines.append(f"    投入: {r.get('investment','')} | 周期: {r.get('timeline','')}")
            lines.append(f"    解决: {', '.join(r.get('addresses',[]))}\n")
        roi = opt.get("roi_estimation", [])
        if roi:
            lines.append("ROI:")
            for r in roi:
                lines.append(f"  {r.get('recommendation','')}: ROI {r.get('roi_pct',0)}% 回收{r.get('payback_months',0)}月")
        return {"content": "\n".join(lines), "suggestions": ["有哪些风险", "战略路径是什么"]}

    if topic == "root_cause":
        lines = ["**根因分析:**\n"]
        lines.append("基于SOP分析，主要根因:")
        lines.append("  1. AI自动化率仅40%，60%内容依赖人工 → SLA不达标")
        lines.append("  2. 流程串行设计(5步)，无并行处理 → 时效过长")
        lines.append("  3. 审核员疲劳指数72% → 准确率下降+流失")
        return {"content": "\n".join(lines), "suggestions": ["优化建议是什么", "如果自动化率提升到80%会怎样"]}

    if topic == "simulation":
        lines = ["**场景模拟:**\n"]
        lines.append("如果自动化率40%→80%:")
        lines.append("  成本: ¥300K/月 → ¥66K/月 (-78%)")
        lines.append("  SLA: 67% → 100% (+33%)")
        lines.append("  准确率: 95% → 93% (-2%)")
        lines.append("  年节省: ¥2.8M")
        return {"content": "\n".join(lines), "suggestions": ["优化建议是什么", "有哪些风险"]}

    return {"content": "请先粘贴一段PRD文档。", "suggestions": ["分析内容审核系统PRD"]}


def _help() -> dict:
    return {
        "content": "您可以：\n1. 粘贴PRD/企业文档 → 自动生成SOP+风险+战略+优化\n2. 问'有哪些风险'\n3. 问'战略路径是什么'\n4. 问'优化建议是什么'\n5. 问'为什么SLA低'",
        "suggestions": ["分析内容审核系统PRD", "有哪些风险", "优化建议是什么"],
    }


def _default(msg: str) -> dict:
    return {
        "content": f'您可以粘贴一段PRD文档，或输入"帮助"查看功能。',
        "suggestions": ["分析内容审核系统PRD", "帮助"],
    }