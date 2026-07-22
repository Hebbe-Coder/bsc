"""Release performance and server-side response bound gates."""

from __future__ import annotations

from math import ceil
import time

from fastapi.testclient import TestClient

from app.api.growth_api import get_growth_repository
from app.core.config import settings
from app.knowledge.growth_repository import GrowthRepository
from app.main import app


def _seed_outputs(repo: GrowthRepository, project_id: str, count: int) -> None:
    rows = []
    for index in range(count):
        output_id = f"perf-output-{index:05d}"
        created_at = f"2026-07-{1 + index % 20:02d}T{index % 24:02d}:00:00+00:00"
        rows.append(
            (
                output_id,
                project_id,
                "report",
                f"Performance output {index}",
                "text/markdown",
                f"{index:064x}",
                f"outputs/2026/{output_id}/report.md",
                f"run-{index:05d}",
                "",
                "",
                "[]",
                "[]",
                f"perf:{index:05d}",
                "accepted" if index % 4 else "rejected",
                '{"quality":90}',
                '{"task_family":"performance"}',
                created_at,
                created_at,
            )
        )
    repo._executemany(
        "INSERT INTO knowledge_outputs "
        "(id,project_id,kind,title,mime_type,content_hash,vault_path,run_id,method_revision_id,context_revision,source_refs_json,page_refs_json,idempotency_key,status,quality_json,metadata_json,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    repo._commit()


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, ceil(len(ordered) * 0.95) - 1)]


def test_metadata_list_p95_is_below_300ms_for_10000_project_records(tmp_path, monkeypatch):
    repo = GrowthRepository(db_path=str(tmp_path / "growth-performance.db"))
    try:
        _seed_outputs(repo, "project-performance", 10_000)
        assert len(repo.list_outputs("project-performance", limit=10_000)) == 500

        monkeypatch.setattr(settings, "KNOWLEDGE_GROWTH_ENABLED", True)
        monkeypatch.setattr(settings, "API_KEY", "growth-performance-key")
        monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
        app.dependency_overrides[get_growth_repository] = lambda: repo
        client = TestClient(app, headers={"Authorization": "Bearer growth-performance-key"})

        warmup = client.get(
            "/knowledge/growth/project-performance/assets",
            params={"stage": "D", "limit": 100},
        )
        assert warmup.status_code == 200, warmup.text
        assert len(warmup.json()["data"]["items"]) == 100

        durations = []
        for _ in range(30):
            started = time.perf_counter()
            response = client.get(
                "/knowledge/growth/project-performance/assets",
                params={"stage": "D", "limit": 100},
            )
            durations.append((time.perf_counter() - started) * 1_000)
            assert response.status_code == 200
            assert len(response.json()["data"]["items"]) == 100
        assert _p95(durations) < 300, durations
    finally:
        app.dependency_overrides.pop(get_growth_repository, None)
        repo.close()


def test_lineage_slice_is_bounded_to_500_edges(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "growth-graph-bound.db"))
    try:
        _seed_outputs(repo, "project-graph", 1_202)
        now = "2026-07-22T00:00:00+00:00"
        repo._executemany(
            "INSERT INTO knowledge_graph_edges "
            "(id,project_id,from_id,to_id,edge_type,metadata_json,revision,created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            [
                (
                    f"edge-{index:04d}",
                    "project-graph",
                    f"perf-output-{index:05d}",
                    f"perf-output-{index + 1:05d}",
                    "output_proposes_page",
                    "{}",
                    "fixture-v1",
                    now,
                )
                for index in range(1_001)
            ],
        )
        repo._commit()
        assert len(repo.list_lineage("project-graph", limit=5_000)) == 500
    finally:
        repo.close()
