import hashlib
import threading
import time

import pytest

from app.knowledge.candidate_extraction import (
    CANDIDATE_EXTRACTION_RUN_TYPE,
    CandidateExtractionError,
    SourceCandidateExtractionService,
    claim_source_candidate_extraction_run,
)
from app.knowledge.growth_contracts import KnowledgeCandidateStatus
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.wiki_contracts import KnowledgeRun, SourceRecord, SourceStatus
from app.tasks.candidate_extraction_tasks import execute_source_candidate_extraction


SOURCE_TEXT = """The research team used an evidence ladder before selecting an intervention.
The principle was to prefer direct observations over assumptions when the two disagree.
In one case, interview transcripts changed the launch sequence and reduced rework.
A counterexample appeared when the sample was too small: direct observations then overfit a single customer.
The term evidence ladder means an ordered comparison of source reliability and relevance."""


class FakeCandidateProvider:
    def __init__(self, *, bad_quote: bool = False):
        self.calls = []
        self.bad_quote = bad_quote

    def extract(self, *, project_id, source, candidate_type):
        self.calls.append(candidate_type.value)
        evidence = {
            "framework": ("paragraph-1", "The research team used an evidence ladder before selecting an intervention."),
            "principle": ("paragraph-2", "The principle was to prefer direct observations over assumptions when the two disagree."),
            "case": ("paragraph-3", "In one case, interview transcripts changed the launch sequence and reduced rework."),
            "counterexample": ("paragraph-4", "A counterexample appeared when the sample was too small: direct observations then overfit a single customer."),
            "glossary": ("paragraph-5", "The term evidence ladder means an ordered comparison of source reliability and relevance."),
        }[candidate_type.value]
        quote = "fabricated evidence quote" if self.bad_quote else evidence[1]
        return {
            "candidates": [{
                "candidate_type": candidate_type.value,
                "title": f"{candidate_type.value} evidence",
                "claim": f"The source provides a concrete {candidate_type.value} candidate for review.",
                "explanation": "This stays a review artifact and does not create a method or Wiki page.",
                "evidence": [{"anchor": evidence[0], "quote": quote}],
            }]
        }, {"run_id": f"prompt-{candidate_type.value}", "provider": "fake", "model": "fixture"}


def _source(repo: GrowthRepository, *, project_id: str = "project-a", classification: str = "internal") -> dict:
    return repo.create_source(
        SourceRecord(
            id=f"{project_id}-source",
            project_id=project_id,
            source_type="meeting_notes",
            origin=f"obsidian://{project_id}/research",
            content_hash=hashlib.sha256(SOURCE_TEXT.encode()).hexdigest(),
            raw_content=SOURCE_TEXT,
            trust_level="reviewed",
            status=SourceStatus.ELIGIBLE,
            metadata={"data_classification": classification},
        )
    )


def test_five_way_extraction_persists_review_only_candidates_with_exact_evidence_and_lineage(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "candidate-extraction.db"))
    source = _source(repo)
    provider = FakeCandidateProvider()
    try:
        result = SourceCandidateExtractionService(repo, provider=provider).extract(
            project_id="project-a", source_id=source["id"], actor_id="owner"
        )

        assert sorted(provider.calls) == ["case", "counterexample", "framework", "glossary", "principle"]
        assert result["outcome"] == "completed"
        assert len(result["candidates"]) == 5
        assert {item["candidate_type"] for item in result["candidates"]} == {
            "framework", "principle", "case", "counterexample", "glossary"
        }
        assert all(item["status"] == KnowledgeCandidateStatus.PENDING_REVIEW.value for item in result["candidates"])
        assert all(item["source_content_hash"] == source["content_hash"] for item in result["candidates"])
        assert all(item["evidence"][0]["quote"] in SOURCE_TEXT for item in result["candidates"])
        assert repo.list_method_proposals("project-a") == []
        assert repo.list_methods("project-a") == []
        assert repo.list_pages("project-a") == []

        edges = repo.list_lineage("project-a")
        for candidate in result["candidates"]:
            assert any(
                edge["edge_type"] == "source_extracts_candidate"
                and edge["from_id"] == source["id"]
                and edge["to_id"] == candidate["id"]
                for edge in edges
            )
            assert any(
                edge["edge_type"] == "run_produces_candidate"
                and edge["to_id"] == candidate["id"]
                for edge in edges
            )

        accepted = repo.review_candidate(
            "project-a",
            result["candidates"][0]["id"],
            decision=KnowledgeCandidateStatus.ACCEPTED,
            actor_id="owner",
            review_note="Useful framing; retain for later method selection.",
        )
        assert accepted["status"] == KnowledgeCandidateStatus.ACCEPTED.value
        assert accepted["reviewer_id"] == "owner"
        assert repo.list_methods("project-a") == []
        assert repo.list_method_proposals("project-a") == []
        with pytest.raises(Exception, match="already recorded"):
            repo.review_candidate(
                "project-a",
                accepted["id"],
                decision=KnowledgeCandidateStatus.REJECTED,
                actor_id="owner",
            )
    finally:
        repo.close()


def test_bad_quotes_never_persist_candidates_and_leave_an_honest_failed_run(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "bad-candidate-evidence.db"))
    source = _source(repo)
    try:
        with pytest.raises(CandidateExtractionError, match="all independent candidate extractors failed"):
            SourceCandidateExtractionService(repo, provider=FakeCandidateProvider(bad_quote=True)).extract(
                project_id="project-a", source_id=source["id"], actor_id="owner"
            )
        assert repo.list_candidates("project-a") == []
        run = repo.latest_run_for_type("project-a", CANDIDATE_EXTRACTION_RUN_TYPE)
        assert run and run["status"] == "failed"
        assert run["output_refs"]["publication_status"] == "review_only"
    finally:
        repo.close()


def test_private_raw_source_never_reaches_any_candidate_extractor(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "private-candidate.db"))
    source = _source(repo, classification="private")
    provider = FakeCandidateProvider()
    try:
        with pytest.raises(CandidateExtractionError, match="sanitized derivative"):
            SourceCandidateExtractionService(repo, provider=provider).extract(
                project_id="project-a", source_id=source["id"], actor_id="owner"
            )
        assert provider.calls == []
        assert repo.list_candidates("project-a") == []
    finally:
        repo.close()


def test_detached_delivery_is_idempotent_and_never_creates_a_method(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "candidate-detached.db"))
    source = _source(repo)
    provider = FakeCandidateProvider()
    service = SourceCandidateExtractionService(repo, provider=provider)
    try:
        submitted = service.submit(project_id="project-a", source_id=source["id"], actor_id="owner", trigger="http")
        assert submitted["status"] == "queued"
        result = execute_source_candidate_extraction(
            "project-a",
            submitted["id"],
            repository=repo,
            service_factory=lambda _repository: service,
        )
        assert result["outcome"] == "completed"
        assert len(repo.list_candidates("project-a")) == 5
        assert repo.list_methods("project-a") == []
        duplicate = execute_source_candidate_extraction("project-a", submitted["id"], repository=repo)
        assert duplicate == {"status": "completed", "run_id": submitted["id"], "duplicate": True}
        events = repo.list_run_events(project_id="project-a", run_id=submitted["id"])
        event_types = [item["event_type"] for item in events]
        assert event_types[0] == "knowledge.run.queued"
        assert "knowledge.candidate_extraction.started" in event_types
        assert event_types.count("knowledge.candidate_extraction.type_started") == 5
        assert event_types.count("knowledge.candidate_extraction.type_completed") == 5
        assert "knowledge.candidate_extraction.completed" in event_types
    finally:
        repo.close()


def test_five_candidate_extractors_overlap_while_repository_writes_remain_governed(tmp_path):
    class ConcurrentCandidateProvider(FakeCandidateProvider):
        def __init__(self):
            super().__init__()
            self._lock = threading.Lock()
            self.active = 0
            self.maximum_active = 0

        def extract(self, *, project_id, source, candidate_type):
            with self._lock:
                self.active += 1
                self.maximum_active = max(self.maximum_active, self.active)
            try:
                # A short overlap window proves the extractors are not run in
                # a serial loop without making the test timing-sensitive.
                time.sleep(0.05)
                return super().extract(project_id=project_id, source=source, candidate_type=candidate_type)
            finally:
                with self._lock:
                    self.active -= 1

    repo = GrowthRepository(db_path=str(tmp_path / "concurrent-candidates.db"))
    source = _source(repo)
    provider = ConcurrentCandidateProvider()
    try:
        result = SourceCandidateExtractionService(repo, provider=provider).extract(
            project_id="project-a", source_id=source["id"], actor_id="owner"
        )

        assert provider.maximum_active >= 2
        assert len(result["candidates"]) == 5
        events = repo.list_run_events(project_id="project-a", run_id=result["run_id"])
        assert [item["event_type"] for item in events].count("knowledge.candidate_extraction.type_started") == 5
        assert len(repo.list_methods("project-a")) == 0
        assert len(repo.list_pages("project-a")) == 0
    finally:
        repo.close()


def test_candidate_extraction_claim_is_atomic(tmp_path):
    repo = GrowthRepository(db_path=str(tmp_path / "candidate-claim.db"))
    source = _source(repo)
    try:
        submitted = SourceCandidateExtractionService(repo, provider=FakeCandidateProvider()).submit(
            project_id="project-a", source_id=source["id"], actor_id="owner"
        )
        assert claim_source_candidate_extraction_run(repo, project_id="project-a", run_id=submitted["id"]) is True
        assert claim_source_candidate_extraction_run(repo, project_id="project-a", run_id=submitted["id"]) is False
    finally:
        repo.close()


def test_sqlite_candidate_submission_stays_in_process_when_celery_broker_is_available(monkeypatch, tmp_path):
    """A broker alone cannot hand a local SQLite run to a different worker DB."""
    from app.tasks import candidate_extraction_tasks

    repo = GrowthRepository(db_path=str(tmp_path / "sqlite-candidate-dispatch.db"))
    run = repo.create_run(
        KnowledgeRun(project_id="project-a", run_type=CANDIDATE_EXTRACTION_RUN_TYPE, trigger="test")
    )
    execution_calls: list[tuple[str, str, GrowthRepository | None]] = []
    celery_calls: list[list[str]] = []

    class ImmediateThread:
        def __init__(self, *, target, **_kwargs):
            self.target = target

        def start(self):
            self.target()

    def execute(project_id, run_id, *, repository=None, **_kwargs):
        execution_calls.append((project_id, run_id, repository))
        return {"status": "completed", "run_id": run_id}

    try:
        monkeypatch.setattr(candidate_extraction_tasks, "is_celery_real", lambda: True)
        monkeypatch.setattr(candidate_extraction_tasks, "is_celery_broker_available", lambda: True)
        monkeypatch.setattr(candidate_extraction_tasks, "Thread", ImmediateThread)
        monkeypatch.setattr(candidate_extraction_tasks, "execute_source_candidate_extraction", execute)
        monkeypatch.setattr(
            candidate_extraction_tasks.source_candidate_extraction_execute,
            "apply_async",
            lambda args: celery_calls.append(args),
        )

        assignment = candidate_extraction_tasks.dispatch_source_candidate_extraction(
            "project-a", run["id"], repository=repo
        )

        assert assignment == {
            "execution": "in_process",
            "task_name": "knowledge.candidate_extraction.execute",
            "task_id": f"in-process:{run['id']}",
        }
        assert celery_calls == []
        assert execution_calls == [("project-a", run["id"], repo)]
        assert repo.list_run_events(project_id="project-a", run_id=run["id"])[-1]["payload"] == assignment
    finally:
        repo.close()
