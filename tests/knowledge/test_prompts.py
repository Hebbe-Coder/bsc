from app.knowledge.prompts import (
    build_system_prompt,
    build_user_prompt,
    build_citation_plan_prompt,
    build_answer_prompt,
    ROLE_BLOCK,
    TASK_BLOCK,
    CONTEXT_CONTRACT_BLOCK,
    CITATION_RULES_BLOCK,
    OUTPUT_SCHEMA_BLOCK,
)


def test_system_prompt_has_five_subblocks():
    sp = build_system_prompt()
    for blk in (ROLE_BLOCK, TASK_BLOCK, CONTEXT_CONTRACT_BLOCK,
                CITATION_RULES_BLOCK, OUTPUT_SCHEMA_BLOCK):
        assert blk in sp


def test_user_prompt_contains_question_and_context():
    up = build_user_prompt("什么是 SLA?", "[1] SLA 是服务等级")
    assert "什么是 SLA?" in up
    assert "[1] SLA 是服务等级" in up


def test_citation_plan_prompt_mentions_cite_ids():
    assert "cite_ids" in build_citation_plan_prompt("Q", "ctx")


def test_answer_prompt_constrains_to_plan():
    ap = build_answer_prompt("Q", "ctx", [1, 3])
    assert "[1]" in ap and "[3]" in ap
