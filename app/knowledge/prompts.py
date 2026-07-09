"""RAG 接地提示词的细分子块与组装函数。

把提示词拆成独立常量(角色/任务/上下文契约/引用规则/输出 schema),
便于单独测试与调优;可选两阶段(先引证规划再作答)。
"""
from __future__ import annotations

ROLE_BLOCK = (
    "你是严格基于企业知识库作答的业务分析师,只使用下方带编号的 [n] 知识,"
    "不得凭空杜撰或引入未提供的外部信息。"
)
TASK_BLOCK = "根据用户问题,仅使用下方带编号的 [n] 知识给出答案。"
CONTEXT_CONTRACT_BLOCK = (
    "下方知识按「[章节：xxx]」分段,每段内有 [n] 编号的内容块。"
    "未提供编号的知识一律不得使用;每个 [n] 仅对应其下方标注的内容。"
)
CITATION_RULES_BLOCK = (
    "引用规则:每条事实必须标注其来源 [n];禁止出现无任何 [n] 的来源断言;"
    "若现有知识不足以回答问题,明确说明「依据现有知识无法回答」。"
)
OUTPUT_SCHEMA_BLOCK = '只输出 JSON {"answer": "<含 [n] 引用的答案>"},不要额外解释。'


def build_system_prompt() -> str:
    return "\n\n".join([
        ROLE_BLOCK, TASK_BLOCK, CONTEXT_CONTRACT_BLOCK,
        CITATION_RULES_BLOCK, OUTPUT_SCHEMA_BLOCK,
    ])


def build_user_prompt(question: str, context: str) -> str:
    return f"问题：{question}\n\n知识：\n{context}"


def build_citation_plan_prompt(question: str, context: str) -> str:
    return (
        "请先判断支撑回答需要引用哪些知识块。只输出 JSON "
        '{"cite_ids": [<用到的 [n] 编号列表>]}。\n\n'
        f"问题：{question}\n\n知识：\n{context}"
    )


def build_answer_prompt(question: str, context: str, cite_ids: list) -> str:
    ids = ", ".join(f"[{i}]" for i in (cite_ids or []))
    return (
        f"问题：{question}\n\n"
        f"只允许引用以下编号的知识:{ids}\n\n知识：\n{context}"
    )
