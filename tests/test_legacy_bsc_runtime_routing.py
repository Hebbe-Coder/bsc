import asyncio

from app.api import bsc_api
from app.core.config import settings


def _compile_payload() -> dict:
    return {
        "business_system": {"composed": {}, "business_domain": "test"},
        "pipeline": {"stages": [], "parallel": True},
        "workspace": {},
        "summary": "legacy runtime result",
    }


def test_legacy_compile_endpoint_delegates_to_runtime(monkeypatch):
    calls = {}

    async def fake_run(**kwargs):
        calls.update(kwargs)
        return _compile_payload()

    monkeypatch.setattr(
        "app.capabilities.runner.run_legacy_bsc_runtime",
        fake_run,
    )

    response = asyncio.run(
        bsc_api.compile_prd(
            bsc_api.CompileRequest(
                input="x" * 10,
                output_types=[],
                template_id="builtin_ecommerce",
            )
        )
    )

    assert response.success is True
    assert calls == {
        "input_text": "x" * 10,
        "template_id": "builtin_ecommerce",
        "async_mode": True,
        "tenant_id": settings.DEFAULT_TENANT_ID,
        "project_id": "",
    }


def test_legacy_stage_endpoint_delegates_to_runtime(monkeypatch):
    calls = {}

    async def fake_run(**kwargs):
        calls.update(kwargs)
        return {"result": {"business_domain": "test"}}

    monkeypatch.setattr(
        "app.capabilities.runner.run_legacy_bsc_stage_runtime",
        fake_run,
    )

    response = asyncio.run(
        bsc_api.execute_stage(
            bsc_api.StageRequest(input="x" * 10, stage_key="business_understanding")
        )
    )

    assert response.success is True
    assert response.data["data"]["result"]["business_domain"] == "test"
    assert calls == {
        "input_text": "x" * 10,
        "stage_key": "business_understanding",
        "tenant_id": settings.DEFAULT_TENANT_ID,
        "project_id": "",
    }


def test_prd_compile_endpoint_delegates_to_runtime(monkeypatch):
    from app.api import prd_api

    calls = {}

    class FakeAnalyzer:
        def analyze(self, prd_text, use_llm=False):
            assert prd_text == "x" * 10
            assert use_llm is False
            return {"prd_quality": 100, "recommendations": []}

    async def fake_run(**kwargs):
        calls.update(kwargs)
        return _compile_payload()

    monkeypatch.setattr("app.engines.prd_analyzer.PRDAnalyzer", FakeAnalyzer)
    monkeypatch.setattr("app.capabilities.runner.run_legacy_bsc_runtime", fake_run)

    response = asyncio.run(
        prd_api.prd_analyze_and_compile(
            prd_api.CompileWithAnalysisRequest(
                prd_text="x" * 10,
                template_id="builtin_ecommerce",
                output_types=[],
            )
        )
    )

    assert response.success is True
    assert response.data["compiled"] is True
    assert calls == {
        "input_text": "x" * 10,
        "template_id": "builtin_ecommerce",
        "tenant_id": settings.DEFAULT_TENANT_ID,
        "project_id": "",
    }
