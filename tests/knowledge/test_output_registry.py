import hashlib
from pathlib import Path

import pytest

from app.knowledge.growth_contracts import OutputAsset, OutputStatus
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.output_registry import OutputRegistry
from app.knowledge.output_source_gate import OutputSourceAdmissionError
from app.knowledge.wiki_contracts import KnowledgeRun, RunStatus, SourceRecord, SourceStatus


def _provenance(**overrides):
    return {
        "goal": "Produce a grounded project report",
        "audience": "project team",
        "channel": "report",
        "generator": "test-suite",
        "provider": "deterministic",
        "model": "none",
        "prompt_revision": "prompt-v1",
        **overrides,
    }


def _write_managed_sop_orphan(
    repo: GrowthRepository,
    vault_root: Path,
    *,
    project_id: str = "project-a",
    output_id: str = "a" * 24,
    run_id: str = "sop_" + "b" * 24,
    index_project_id: str | None = None,
    content: bytes = b"# Recovered SOP\n",
    declared_hash: str | None = None,
) -> tuple[OutputRegistry, OutputAsset]:
    registry = OutputRegistry(repo, vault_root)
    output = OutputAsset(
        id=output_id,
        project_id=project_id,
        kind="project_sop",
        title="Recovered SOP",
        mime_type="text/markdown",
        content_hash=declared_hash or hashlib.sha256(content).hexdigest(),
        vault_path=f"outputs/2026/{output_id}/project-sop.md",
        run_id=run_id,
        context_revision="c" * 64,
        source_refs=["source-a"],
        idempotency_key=f"unavailable-legacy-key:{output_id}",
        metadata=_provenance(generator="project_sop_generation_service"),
    )
    target = vault_root / "projects" / project_id / output.vault_path
    target.parent.mkdir(parents=True)
    target.write_bytes(content)
    index = registry._index(output, original_path="")
    if index_project_id:
        index = index.replace(f"project_id: {project_id}", f"project_id: {index_project_id}")
    (target.parent / "index.md").write_text(index, encoding="utf-8")
    return registry, output


def test_recover_managed_sop_orphan_restores_registered_output_and_run_lineage(tmp_path):
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "recovery.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        repo.create_source(SourceRecord(
            id="source-a", project_id="project-a", source_type="article",
            content_hash="s" * 64, raw_content="evidence", status=SourceStatus.ELIGIBLE,
        ))
        registry, output = _write_managed_sop_orphan(repo, vault_root)

        recovered = registry.recover_managed_sop_orphans("project-a")

        assert recovered["recovered"] == [output.id]
        saved = repo.get_output("project-a", output.id)
        assert saved is not None
        assert saved["status"] == OutputStatus.REGISTERED.value
        assert saved["vault_path"] == output.vault_path
        assert saved["metadata"]["recovery"]["state"] == "recovered_from_managed_artifact"
        run = repo.get_run("project-a", output.run_id)
        assert run is not None
        assert run["status"] == RunStatus.COMPLETED.value
        assert run["trigger"] == "recovery"
        assert run["output_refs"]["output_id"] == output.id
        relations = {edge["edge_type"] for edge in repo.list_lineage("project-a")}
        assert {"output_used_source", "output_produced_by_run"}.issubset(relations)
    finally:
        repo.close()


def test_recovery_rejects_tampered_cross_project_and_unmanaged_sop_indexes(tmp_path):
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "recovery-rejections.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        repo.create_source(SourceRecord(
            id="source-a", project_id="project-a", source_type="article",
            content_hash="s" * 64, raw_content="evidence", status=SourceStatus.ELIGIBLE,
        ))
        registry, _ = _write_managed_sop_orphan(
            repo, vault_root, output_id="c" * 24, declared_hash="d" * 64,
        )
        _write_managed_sop_orphan(
            repo, vault_root, output_id="e" * 24, index_project_id="project-b",
        )
        unmanaged_id = "f" * 24
        unmanaged = vault_root / "projects" / "project-a" / "outputs" / "2026" / unmanaged_id
        unmanaged.mkdir(parents=True)
        (unmanaged / "project-sop.md").write_text("# Unmanaged\n", encoding="utf-8")
        (unmanaged / "index.md").write_text("---\nbsc_managed: false\n---\n", encoding="utf-8")

        result = registry.recover_managed_sop_orphans("project-a")

        assert result["recovered"] == []
        assert result["rejected"] == {
            "c" * 24: "content_hash_mismatch",
            "e" * 24: "project_scope_mismatch",
            unmanaged_id: "unmanaged_index",
        }
        assert repo.list_outputs("project-a") == []
        assert repo.get_run("project-a", "sop_" + "b" * 24) is None
    finally:
        repo.close()


def test_recovery_is_idempotent_and_refuses_existing_conflicting_records(tmp_path):
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "recovery-idempotency.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        repo.create_source(SourceRecord(
            id="source-a", project_id="project-a", source_type="article",
            content_hash="s" * 64, raw_content="evidence", status=SourceStatus.ELIGIBLE,
        ))
        registry, output = _write_managed_sop_orphan(repo, vault_root)
        assert registry.recover_managed_sop_orphans("project-a")["recovered"] == [output.id]

        repeated = registry.recover_managed_sop_orphans("project-a")

        assert repeated["already_registered"] == [output.id]
        assert len(repo.list_outputs("project-a")) == 1
        assert len(repo.list_run_events(project_id="project-a", run_id=output.run_id)) == 2

        repo._execute(
            "UPDATE knowledge_outputs SET content_hash=? WHERE project_id=? AND id=?",
            ("0" * 64, "project-a", output.id),
        )
        repo._commit()
        conflict = registry.recover_managed_sop_orphans("project-a")
        assert conflict["rejected"] == {output.id: "existing_output_conflict"}
    finally:
        repo.close()


def test_register_output_materializes_text_atomically_and_is_idempotent(tmp_path):
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "outputs.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        registry = OutputRegistry(repo, vault_root)
        content = b"# Report\n"
        output = OutputAsset(
            project_id="project-a", kind="report", title="Report", content_hash=hashlib.sha256(content).hexdigest(),
            vault_path="outputs/2026/generated/report.md", idempotency_key="run-a|report", metadata=_provenance(),
        )
        first = registry.register_content(output, content)
        second = registry.register_content(output, content)
        assert first["id"] == second["id"]
        materialized = vault_root / "projects" / "project-a" / first["vault_path"]
        assert materialized.parent.name == first["id"]
        assert materialized.read_bytes() == b"# Report\n"
        assert "bsc_managed: true" in (materialized.parent / "index.md").read_text(encoding="utf-8")
        assert len(repo.list_outputs("project-a")) == 1
    finally:
        repo.close()


def test_register_output_preserves_original_and_rejects_hash_mismatch(tmp_path):
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    original = tmp_path / "source.md"
    original.write_bytes(b"original")
    repo = GrowthRepository(db_path=str(tmp_path / "outputs-mismatch.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        registry = OutputRegistry(repo, vault_root)
        output = OutputAsset(
            project_id="project-a", kind="report", title="Report", content_hash=hashlib.sha256(b"expected").hexdigest(),
            vault_path="outputs/2026/generated/report.md", idempotency_key="run-a|report", metadata=_provenance(),
        )
        with pytest.raises(ValueError, match="content hash"):
            registry.register_content(output, b"different")
        assert original.read_bytes() == b"original"
    finally:
        repo.close()


def test_registry_rejects_missing_provenance_and_unknown_reference_ownership(tmp_path):
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "ownership.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        registry = OutputRegistry(repo, vault_root)
        content = b"report"
        base = dict(
            project_id="project-a", kind="report", content_hash=hashlib.sha256(content).hexdigest(),
            vault_path="outputs/2026/generated/report.md", idempotency_key="run-a|report",
        )
        with pytest.raises(ValueError, match="provenance"):
            registry.register_content(OutputAsset(**base), content)
        with pytest.raises(ValueError, match="source reference"):
            registry.register_content(OutputAsset(**base, source_refs=["missing"], metadata=_provenance()), content)
        assert repo.list_outputs("project-a") == []
    finally:
        repo.close()


def test_registry_rejects_content_collision_and_cleans_up_after_repository_failure(tmp_path, monkeypatch):
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "collision.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        registry = OutputRegistry(repo, vault_root)
        content = b"expected"
        output = OutputAsset(
            project_id="project-a", kind="report", content_hash=hashlib.sha256(content).hexdigest(),
            vault_path="outputs/2026/generated/report.md", idempotency_key="run-a|report", metadata=_provenance(),
        )
        output_id = registry.deterministic_id(output)
        target = vault_root / "projects" / "project-a" / "outputs" / "2026" / output_id / "report.md"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"user-owned collision")
        with pytest.raises(FileExistsError, match="collision"):
            registry.register_content(output, content)
        assert target.read_bytes() == b"user-owned collision"

        target.unlink()
        target.parent.rmdir()
        monkeypatch.setattr(repo, "register_output", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("db unavailable")))
        with pytest.raises(RuntimeError, match="db unavailable"):
            registry.register_content(output, content)
        assert not target.exists()
        assert not (target.parent / "index.md").exists()
    finally:
        repo.close()


def test_external_adoption_requires_admin_and_preserves_original(tmp_path):
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    original = tmp_path / "deliverable.bin"
    original.write_bytes(b"\x00\xffdeliverable")
    repo = GrowthRepository(db_path=str(tmp_path / "adopt.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        registry = OutputRegistry(repo, vault_root)
        output = OutputAsset(
            project_id="project-a", kind="binary", mime_type="application/octet-stream",
            content_hash=hashlib.sha256(original.read_bytes()).hexdigest(), vault_path="outputs/2026/external/deliverable.bin",
            idempotency_key="external|deliverable", metadata=_provenance(generator="external-adoption", origin="external"),
        )
        with pytest.raises(PermissionError):
            registry.adopt_external(output, original, actor_role="project_writer")
        saved = registry.adopt_external(output, original, actor_role="project_admin")
        assert original.read_bytes() == b"\x00\xffdeliverable"
        assert (vault_root / "projects" / "project-a" / Path(saved["vault_path"])).read_bytes() == original.read_bytes()
        assert saved["metadata"]["origin"] == "external"
    finally:
        repo.close()


def test_registration_retry_repairs_authoritative_source_and_run_lineage(tmp_path):
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "lineage-repair.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        repo.create_source(SourceRecord(id="source-a", project_id="project-a", source_type="article",
                                        content_hash="s" * 64, raw_content="evidence", status=SourceStatus.ELIGIBLE))
        repo.create_run(KnowledgeRun(id="run-a", project_id="project-a", run_type="report", trigger="test",
                                     status=RunStatus.COMPLETED))
        content = b"grounded report"
        output = OutputAsset(project_id="project-a", kind="report", content_hash=hashlib.sha256(content).hexdigest(),
                             vault_path="outputs/2026/report.md", idempotency_key="run-a|report", run_id="run-a",
                             source_refs=["source-a"], metadata=_provenance())
        registry = OutputRegistry(repo, vault_root)
        saved = registry.register_content(output, content)
        repo._execute("DELETE FROM knowledge_graph_edges WHERE project_id=? AND to_id=?", ("project-a", saved["id"]))
        repo._commit()
        registry.register_content(output, content)
        relations = {edge["edge_type"] for edge in repo.list_lineage("project-a")}
        assert {"output_used_source", "output_produced_by_run"}.issubset(relations)
    finally:
        repo.close()


def test_file_output_verifies_materialization_and_preserves_content(tmp_path):
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "file-output.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        registry = OutputRegistry(repo, vault_root)
        content = b"approved report"
        output = OutputAsset(
            project_id="project-a",
            kind="report",
            content_hash=hashlib.sha256(content).hexdigest(),
            vault_path="outputs/2026/report.md",
            idempotency_key="approved-report",
            status=OutputStatus.ACCEPTED,
            metadata=_provenance(),
        )
        registered = registry.register_content(output, content)

        filed = registry.file_output(
            "project-a",
            registered["id"],
            actor_id="owner",
            reason="approved for durable filing",
            expected_status=OutputStatus.ACCEPTED,
        )
        target = vault_root / "projects" / "project-a" / Path(filed["vault_path"])
        assert filed["status"] == "filed"
        assert target.read_bytes() == content
        assert registry.file(
            "project-a",
            registered["id"],
            actor_id="owner",
            reason="approved for durable filing",
            expected_status=OutputStatus.ACCEPTED,
        )["status"] == "filed"
    finally:
        repo.close()


def test_file_output_rejects_tampering_and_cross_project_access(tmp_path):
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "file-output-guards.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        repo.configure_vault("project-b", "projects/project-b", "owner")
        registry = OutputRegistry(repo, vault_root)
        content = b"approved report"
        registered = registry.register_content(
            OutputAsset(
                project_id="project-a",
                kind="report",
                content_hash=hashlib.sha256(content).hexdigest(),
                vault_path="outputs/2026/report.md",
                idempotency_key="approved-report",
                status=OutputStatus.ACCEPTED,
                metadata=_provenance(),
            ),
            content,
        )
        target = vault_root / "projects" / "project-a" / Path(registered["vault_path"])
        target.write_bytes(b"tampered")

        with pytest.raises(ValueError, match="content hash"):
            registry.file(
                "project-a", registered["id"], actor_id="owner", reason="file it"
            )
        assert repo.get_output("project-a", registered["id"])["status"] == "accepted"
        with pytest.raises(KeyError, match="not found in project"):
            registry.file(
                "project-b", registered["id"], actor_id="owner", reason="cross project"
            )
    finally:
        repo.close()


def test_file_output_rechecks_current_source_admission(tmp_path):
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    repo = GrowthRepository(db_path=str(tmp_path / "file-source-drift.db"))
    try:
        repo.configure_vault("project-a", "projects/project-a", "owner")
        repo.create_source(SourceRecord(
            id="source-a", project_id="project-a", source_type="article",
            content_hash="s" * 64, raw_content="evidence", status=SourceStatus.ELIGIBLE,
        ))
        registry = OutputRegistry(repo, vault_root)
        content = b"approved report"
        registered = registry.register_content(
            OutputAsset(
                project_id="project-a", kind="report", content_hash=hashlib.sha256(content).hexdigest(),
                vault_path="outputs/2026/report.md", idempotency_key="source-drift-report",
                status=OutputStatus.ACCEPTED, source_refs=["source-a"], metadata=_provenance(),
            ),
            content,
        )
        repo.update_source_status("project-a", "source-a", SourceStatus.REJECTED)

        with pytest.raises(OutputSourceAdmissionError, match="regenerate the output"):
            registry.file_output("project-a", registered["id"], actor_id="owner", reason="approved")

        assert repo.get_output("project-a", registered["id"])["status"] == "accepted"
    finally:
        repo.close()
