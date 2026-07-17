"""可信审计整合：缝合 A（方法论引用）与 B（约束覆盖 + SHA-256 审计链）。

本模块不依赖数据库 / 编排引擎，纯函数式消费编译器产物 state：
- 收集所有 `source_ref`（来自 sop 与 business_model 各元素）灌入审计链；
- 把约束覆盖率快照（来自 risk.coverage / risk.gate）作为链中第二个节点；
- 任何对引用集合或覆盖率快照的篡改都会断链 → verify() 返回 False。

复用 B 的 `app.constraint.audit.AuditChain` / `AuditEntry`，保证与约束审计同源同构。
"""
from __future__ import annotations

from typing import Optional

from app.constraint.audit import AuditChain, AuditEntry, GENESIS, _sha256, _stable

# business_model 中携带 source_ref 的元素分组键
_BM_REF_GROUPS = ("flows", "roles", "rules")


def collect_source_refs(state: Optional[dict]) -> list[str]:
    """从编译产物 state 收集所有方法论 source_ref（chunk_id），去重且保序。

    来源：
      - state["sop"]["sops"][i]["source_ref"]
      - state["business_model"][group][j]["source_ref"]  (group ∈ flows/roles/rules)
    空值 / 非列表字段安全跳过；None 与空串不入列。
    """
    state = state or {}
    refs: list[str] = []

    sop = state.get("sop") or {}
    for s in (sop.get("sops") or []):
        if isinstance(s, dict):
            r = s.get("source_ref")
            if isinstance(r, list):
                refs.extend(str(x) for x in r)

    bm = state.get("business_model") or {}
    for grp in _BM_REF_GROUPS:
        for el in (bm.get(grp) or []):
            if isinstance(el, dict):
                r = el.get("source_ref")
                if isinstance(r, list):
                    refs.extend(str(x) for x in r)

    seen: set[str] = set()
    out: list[str] = []
    for x in refs:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _coverage_snapshot(state: Optional[dict]) -> dict:
    """从 risk 段提取约束覆盖率 + 门禁快照。"""
    risk = (state or {}).get("risk") or {}
    cov = risk.get("coverage") or {}
    gate = risk.get("gate") or {}
    return {
        "coverage_pct": cov.get("coverage_pct"),
        "covered": cov.get("covered"),
        "total": cov.get("total"),
        "uncovered_ids": cov.get("uncovered_ids", []),
        "gate_decision": gate.get("decision"),
    }


def _count_elements(state: Optional[dict]) -> int:
    """粗略统计参与审计的业务元素数（用于 citation_index 的输入元数据）。"""
    state = state or {}
    sop = state.get("sop") or {}
    bm = state.get("business_model") or {}
    n = len(sop.get("sops") or [])
    for grp in _BM_REF_GROUPS:
        n += len(bm.get(grp) or [])
    return n


def build_trusted_audit(state: Optional[dict]) -> dict:
    """把编译产物 state 重塑为一条可信审计记录。

    Returns:
        {
          "source_refs": [str],          # 全部去重后的 chunk_id
          "coverage": {coverage_pct, covered, total, uncovered_ids, gate_decision},
          "audit": [AuditEntry.model_dump(), ...],  # SHA-256 链
          "chain_hash": str,             # 链头哈希（最终节点 hash）
          "verified": bool,              # 构建时链自洽
        }
    空 state 仍可构建：source_refs=[]、coverage 字段为 None、链仍自洽（verified=True）。
    """
    state = state or {}
    source_refs = collect_source_refs(state)
    snapshot = _coverage_snapshot(state)

    chain = AuditChain()
    chain.append(
        "methodology", "citation_index",
        {"input": {"elements": _count_elements(state)},
         "output": {"source_refs": source_refs, "count": len(source_refs)}},
    )
    chain.append(
        "constraint", "coverage_snapshot",
        {"input": {"gate": snapshot.get("gate_decision")},
         "output": snapshot},
    )

    head = chain.entries[-1].hash if chain.entries else GENESIS
    return {
        "source_refs": source_refs,
        "coverage": snapshot,
        "audit": [e.model_dump() for e in chain.entries],
        "chain_hash": head,
        "verified": chain.verify(),
    }


def verify_trusted_audit(record: Optional[dict]) -> bool:
    """独立验证一条可信审计记录是否被篡改。

    双重校验：
      1. 重建 SHA-256 链并重放 verify()（捕获链的任一节点被改动）；
      2. 交叉核对 record["source_refs"]（展示用便捷字段）与链内 citation_index 节点
         记录的 output.source_refs 是否一致（捕获便捷字段被单独篡改）。
    任一不符即返回 False。
    """
    record = record or {}
    entries = record.get("audit") or []
    if not entries:
        return False

    chain = AuditChain()
    try:
        chain.entries = [AuditEntry(**e) for e in entries]
    except Exception:
        return False

    if not chain.verify():
        return False

    # 密码学绑定：便捷字段 source_refs 必须可重算出链中 citation_index 节点的 output_hash。
    # （AuditEntry 仅持久化哈希、不持久化原始 output，故由 source_refs 反推哈希做交叉校验，
    #   任一字段被单独篡改都会断链。）
    refs = record.get("source_refs") or []
    expected_output = {"source_refs": refs, "count": len(refs)}
    if entries[0].get("output_hash") != _sha256(_stable(expected_output)):
        return False

    return True
