import asyncio

import pytest

from app.capabilities.board import BOARD_ROLES, MultiAgentBoard
from app.artifacts import ArtifactGraphStore
from app.core.config import settings


class _BrokenLLM:
    async def generate(self, prompt):
        raise RuntimeError("provider unavailable")


def test_board_rejects_rule_based_substitution_in_production(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "ALLOW_LLM_FALLBACK", False)
    board = MultiAgentBoard(ArtifactGraphStore(str(tmp_path)), _BrokenLLM())

    with pytest.raises(RuntimeError, match="fallback is disabled"):
        asyncio.run(board._analyze_role(BOARD_ROLES["ceo"], "project-1"))


def test_board_can_use_explicit_rule_based_fallback_outside_production(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    board = MultiAgentBoard(ArtifactGraphStore(str(tmp_path)), _BrokenLLM())

    opinion = asyncio.run(board._analyze_role(BOARD_ROLES["ceo"], "project-1"))

    assert opinion.role_id == "ceo"
    assert opinion.analysis
    assert opinion.raw_response["verdict"] in {"go", "conditional_go", "no_go"}
