from hashlib import sha256
from io import BytesIO
import json

import pytest

from app.knowledge import multimodal_extraction
from app.knowledge.multimodal_extraction import CURRENT_EXTRACTOR_REVISION, LocalMultimodalExtractor
from app.knowledge.wiki_contracts import (
    ExtractionArtifact,
    ExtractionStatus,
    KnowledgeRun,
    MediaAsset,
    ReferenceLink,
    SourceRecord,
)
from app.knowledge.wiki_repository import WikiRepository
from app.tasks.knowledge_tasks import execute_knowledge_run
from app.core.config import settings


def _source(project_id: str, source_id: str = "source-1") -> SourceRecord:
    body = "Immutable source provenance"
    return SourceRecord(
        id=source_id,
        project_id=project_id,
        source_type="obsidian_unsupported",
        origin=f"projects/{project_id}/01_Sources/file.csv",
        vault_path=f"projects/{project_id}/01_Sources/file.csv",
        content_hash=sha256(body.encode("utf-8")).hexdigest(),
        raw_content=body,
    )


def test_media_and_extraction_records_are_project_scoped_idempotent_and_redacted(tmp_path):
    repo = WikiRepository(db_path=str(tmp_path / "evidence.db"))
    source = repo.create_source(_source("project-a"))
    try:
        asset = MediaAsset(
            project_id="project-a",
            source_id=source["id"],
            mime_type="text/csv",
            byte_hash="a" * 64,
            byte_size=12,
            storage_ref="projects/project-a/01_Sources/file.csv",
        )
        first = repo.register_media_asset(asset)
        duplicate = repo.register_media_asset(asset)
        assert duplicate["id"] == first["id"]
        assert repo.get_media_asset("project-b", first["id"]) is None

        artifact = repo.create_extraction_artifact(
            ExtractionArtifact(
                project_id="project-a",
                source_id=source["id"],
                asset_id=first["id"],
                extractor="csv-table",
                extractor_revision="local-v1",
                input_hash="a" * 64,
                content_hash="b" * 64,
                content="secret derivative text",
                status=ExtractionStatus.COMPLETE,
            )
        )
        listed = repo.list_extraction_artifacts("project-a")
        assert listed == [{key: value for key, value in artifact.items() if key != "content"}]
        assert repo.get_extraction_artifact("project-b", artifact["id"]) is None
        assert repo.get_extraction_content("project-a", artifact["id"])["content"] == "secret derivative text"

        with pytest.raises(KeyError):
            repo.create_reference_link(
                ReferenceLink(
                    project_id="project-b",
                    source_id=source["id"],
                    target_type="wiki_page",
                    target_id="page-1",
                    anchor_type="table_cell",
                    anchor="A2",
                    relation="supports",
                )
            )
    finally:
        repo.close()


def test_local_csv_extraction_is_versioned_and_creates_a_reviewable_table(tmp_path):
    vault = tmp_path / "vault"
    target = vault / "projects" / "project-a" / "01_Sources" / "metrics.csv"
    target.parent.mkdir(parents=True)
    target.write_text("month,revenue_usd\n2026-06,120\n2026-07,180\n", encoding="utf-8")
    payload = target.read_bytes()
    repo = WikiRepository(db_path=str(tmp_path / "extractor.db"))
    source = repo.create_source(_source("project-a", "source-csv"))
    asset = repo.register_media_asset(
        MediaAsset(
            project_id="project-a",
            source_id=source["id"],
            mime_type="text/csv",
            byte_hash=sha256(payload).hexdigest(),
            byte_size=len(payload),
            storage_ref="projects/project-a/01_Sources/metrics.csv",
        )
    )
    try:
        service = LocalMultimodalExtractor(repo, vault)
        first = service.extract(project_id="project-a", source_id=source["id"], asset_id=asset["id"])
        repeated = service.extract(project_id="project-a", source_id=source["id"], asset_id=asset["id"])
        revision = service.extract(
            project_id="project-a",
            source_id=source["id"],
            asset_id=asset["id"],
            extractor_revision="local-v3",
        )

        assert first["status"] == "complete"
        assert repeated["id"] == first["id"]
        assert revision["id"] != first["id"]
        tables = repo.list_table_artifacts("project-a", extraction_id=first["id"])
        assert tables[0]["row_count"] == 2
        assert tables[0]["schema"] == ["month", "revenue_usd"]
        assert "content" not in repo.get_extraction_artifact("project-a", first["id"])
    finally:
        repo.close()


def test_source_sync_reextracts_a_local_v1_derivative_at_the_current_revision(monkeypatch, tmp_path):
    vault = tmp_path / "vault"
    drawing = vault / "projects" / "project-a" / "03_Projects" / "active" / "maps" / "knowledge-flow.excalidraw.md"
    drawing.parent.mkdir(parents=True)
    drawing.write_text(
        "---\nexcalidraw-plugin: parsed\n---\n\n## Drawing\n```compressed-json\n\n```\n%%\n",
        encoding="utf-8",
    )
    payload = drawing.read_bytes()
    repo = WikiRepository(db_path=str(tmp_path / "revision-reextract.db"))
    source = repo.create_source(_source("project-a", "source-revision"))
    asset = repo.register_media_asset(
        MediaAsset(
            project_id="project-a",
            source_id=source["id"],
            mime_type="text/markdown",
            byte_hash=sha256(payload).hexdigest(),
            byte_size=len(payload),
            storage_ref="projects/project-a/03_Projects/active/maps/knowledge-flow.excalidraw.md",
        )
    )
    repo.create_extraction_artifact(
        ExtractionArtifact(
            project_id="project-a",
            source_id=source["id"],
            asset_id=asset["id"],
            extractor="excalidraw-markdown",
            extractor_revision="local-v1",
            input_hash=sha256(payload).hexdigest(),
            status=ExtractionStatus.PARTIAL,
            error="legacy_excalidraw_parser",
            metadata={"drawing_json_detected": False, "element_count": 0},
        )
    )
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_ROOT", str(vault))
    try:
        from app.tasks.knowledge_tasks import _extract_new_vault_assets

        summary = _extract_new_vault_assets(repo, "project-a")
        artifacts = repo.list_extraction_artifacts("project-a", source_id=source["id"])

        assert summary == {
            "attempted": 1,
            "complete": 0,
            "partial": 1,
            "needs_review": 0,
            "unavailable": 0,
            "restricted": 0,
            "skipped_existing": 0,
        }
        assert {artifact["extractor_revision"] for artifact in artifacts} == {"local-v1", CURRENT_EXTRACTOR_REVISION}
        current = repo.latest_extraction_for_asset(
            "project-a", asset["id"], extractor_revision=CURRENT_EXTRACTOR_REVISION
        )
        assert current["error"] == "excalidraw_no_elements"
        assert current["metadata"] == {
            "drawing_json_detected": True,
            "element_count": 0,
            "scene_encoding": "compressed-json",
        }
    finally:
        repo.close()


def test_local_extractor_marks_missing_or_changed_originals_for_review(tmp_path):
    vault = tmp_path / "vault"
    target = vault / "projects" / "project-a" / "01_Sources" / "changed.canvas"
    target.parent.mkdir(parents=True)
    target.write_text('{"nodes": []}', encoding="utf-8")
    repo = WikiRepository(db_path=str(tmp_path / "changed.db"))
    source = repo.create_source(_source("project-a", "source-changed"))
    asset = repo.register_media_asset(
        MediaAsset(
            project_id="project-a",
            source_id=source["id"],
            mime_type="application/json",
            byte_hash="c" * 64,
            byte_size=2,
            storage_ref="projects/project-a/01_Sources/changed.canvas",
        )
    )
    try:
        result = LocalMultimodalExtractor(repo, vault).extract(
            project_id="project-a", source_id=source["id"], asset_id=asset["id"]
        )
        assert result["status"] == "needs_review"
        assert result["error"] == "original_hash_changed"
    finally:
        repo.close()


def test_local_xlsx_and_excalidraw_extractors_produce_project_scoped_derivatives(tmp_path):
    from openpyxl import Workbook

    vault = tmp_path / "vault"
    spreadsheet = vault / "projects" / "project-a" / "01_Sources" / "metrics.xlsx"
    drawing = vault / "projects" / "project-a" / "03_Projects" / "active" / "maps" / "system.excalidraw.md"
    spreadsheet.parent.mkdir(parents=True)
    drawing.parent.mkdir(parents=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Metrics"
    sheet.append(["month", "conversion_pct"])
    sheet.append(["2026-07", 31])
    workbook.save(spreadsheet)
    drawing.write_text(
        "# System map\n\n```json\n{\"elements\":[{\"text\":\"Research to decision\"}]}\n```\n",
        encoding="utf-8",
    )
    repo = WikiRepository(db_path=str(tmp_path / "xlsx-excalidraw.db"))
    xlsx_source = repo.create_source(_source("project-a", "source-xlsx"))
    drawing_source = repo.create_source(_source("project-a", "source-drawing"))
    xlsx_bytes = spreadsheet.read_bytes()
    drawing_bytes = drawing.read_bytes()
    xlsx_asset = repo.register_media_asset(
        MediaAsset(
            project_id="project-a",
            source_id=xlsx_source["id"],
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            byte_hash=sha256(xlsx_bytes).hexdigest(),
            byte_size=len(xlsx_bytes),
            storage_ref="projects/project-a/01_Sources/metrics.xlsx",
        )
    )
    drawing_asset = repo.register_media_asset(
        MediaAsset(
            project_id="project-a",
            source_id=drawing_source["id"],
            mime_type="text/markdown",
            byte_hash=sha256(drawing_bytes).hexdigest(),
            byte_size=len(drawing_bytes),
            storage_ref="projects/project-a/03_Projects/active/maps/system.excalidraw.md",
        )
    )
    try:
        service = LocalMultimodalExtractor(repo, vault)
        xlsx = service.extract(project_id="project-a", source_id=xlsx_source["id"], asset_id=xlsx_asset["id"])
        drawing_result = service.extract(
            project_id="project-a", source_id=drawing_source["id"], asset_id=drawing_asset["id"]
        )

        assert xlsx["status"] == "complete"
        assert repo.list_table_artifacts("project-a", extraction_id=xlsx["id"])[0]["schema"] == ["month", "conversion_pct"]
        assert drawing_result["status"] == "complete"
        assert repo.get_extraction_content("project-a", drawing_result["id"])["content"] == "Research to decision"
    finally:
        repo.close()


def test_local_excalidraw_extractor_reads_official_compressed_scene_and_keeps_empty_scene_partial(tmp_path):
    vault = tmp_path / "vault"
    drawing = vault / "projects" / "project-a" / "03_Projects" / "active" / "maps" / "knowledge-flow.excalidraw.md"
    empty_drawing = vault / "projects" / "project-a" / "03_Projects" / "active" / "maps" / "empty.excalidraw.md"
    drawing.parent.mkdir(parents=True)
    drawing.write_text(
        "---\n"
        "excalidraw-plugin: parsed\n"
        "tags: [excalidraw]\n"
        "---\n\n"
        "## Drawing\n"
        "```compressed-json\n"
        "N4IgpgNmC2YHYBcDOIBcBtUCCeAHMaICYAHgiADRGnmogCCABIPnKg05qAisYJmmIAvhVngJ1iZStVF0AQowDqASwDWc3gF0eQA=\n"
        "```\n%%\n",
        encoding="utf-8",
    )
    empty_drawing.write_text(
        "---\nexcalidraw-plugin: parsed\ntags: [excalidraw]\n---\n\n## Drawing\n```compressed-json\n\n```\n%%\n",
        encoding="utf-8",
    )
    repo = WikiRepository(db_path=str(tmp_path / "compressed-excalidraw.db"))
    drawing_source = repo.create_source(_source("project-a", "source-compressed-drawing"))
    empty_source = repo.create_source(_source("project-a", "source-empty-drawing"))
    drawing_payload = drawing.read_bytes()
    empty_payload = empty_drawing.read_bytes()
    drawing_asset = repo.register_media_asset(
        MediaAsset(
            project_id="project-a",
            source_id=drawing_source["id"],
            mime_type="text/markdown",
            byte_hash=sha256(drawing_payload).hexdigest(),
            byte_size=len(drawing_payload),
            storage_ref="projects/project-a/03_Projects/active/maps/knowledge-flow.excalidraw.md",
        )
    )
    empty_asset = repo.register_media_asset(
        MediaAsset(
            project_id="project-a",
            source_id=empty_source["id"],
            mime_type="text/markdown",
            byte_hash=sha256(empty_payload).hexdigest(),
            byte_size=len(empty_payload),
            storage_ref="projects/project-a/03_Projects/active/maps/empty.excalidraw.md",
        )
    )
    try:
        service = LocalMultimodalExtractor(repo, vault)
        drawing_result = service.extract(
            project_id="project-a", source_id=drawing_source["id"], asset_id=drawing_asset["id"]
        )
        empty_result = service.extract(project_id="project-a", source_id=empty_source["id"], asset_id=empty_asset["id"])

        assert drawing_result["status"] == "complete"
        assert repo.get_extraction_content("project-a", drawing_result["id"])["content"] == "A 原始资料\nB Wiki"
        assert drawing_result["metadata"] == {
            "drawing_json_detected": True,
            "element_count": 2,
            "scene_encoding": "compressed-json",
        }
        assert empty_result["status"] == "partial"
        assert empty_result["error"] == "excalidraw_no_elements"
        assert empty_result["metadata"] == {
            "drawing_json_detected": True,
            "element_count": 0,
            "scene_encoding": "compressed-json",
        }
    finally:
        repo.close()


def test_multimodal_run_is_audited_and_never_promotes_unavailable_work(monkeypatch, tmp_path):
    vault = tmp_path / "vault"
    target = vault / "projects" / "project-a" / "01_Sources" / "metrics.csv"
    target.parent.mkdir(parents=True)
    target.write_text("metric,value\ntrusted_sources,3\n", encoding="utf-8")
    payload = target.read_bytes()
    repo = WikiRepository(db_path=str(tmp_path / "task.db"))
    repo.configure_vault("project-a", "projects/project-a")
    source = repo.create_source(_source("project-a", "source-task"))
    asset = repo.register_media_asset(
        MediaAsset(
            project_id="project-a",
            source_id=source["id"],
            mime_type="text/csv",
            byte_hash=sha256(payload).hexdigest(),
            byte_size=len(payload),
            storage_ref="projects/project-a/01_Sources/metrics.csv",
        )
    )
    run = repo.create_run(
        KnowledgeRun(
            id="run-extract",
            project_id="project-a",
            run_type="multimodal_extract",
            trigger="manual",
            input_refs={"source_id": source["id"], "asset_id": asset["id"]},
        )
    )
    monkeypatch.setattr(settings, "KNOWLEDGE_WIKI_ENABLED", True)
    monkeypatch.setattr(settings, "OBSIDIAN_VAULT_ROOT", str(vault))
    try:
        result = execute_knowledge_run("project-a", run["id"], repository=repo)
        persisted = repo.get_run("project-a", run["id"])

        assert result["status"] == "completed"
        assert result["extraction"]["status"] == "complete"
        assert persisted["output_refs"]["extraction"]["id"] == result["extraction"]["id"]
        assert any(
            event["event_type"] == "knowledge.multimodal.extraction.completed"
            for event in repo.list_run_events(project_id="project-a", run_id=run["id"])
        )
    finally:
        repo.close()


def test_media_probe_records_truthful_partial_metadata_when_ffprobe_is_available(monkeypatch, tmp_path):
    vault = tmp_path / "vault"
    target = vault / "projects" / "project-a" / "01_Sources" / "briefing.mp4"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"not-a-real-media-stream")
    payload = target.read_bytes()
    repo = WikiRepository(db_path=str(tmp_path / "media.db"))
    source = repo.create_source(_source("project-a", "source-media"))
    asset = repo.register_media_asset(
        MediaAsset(
            project_id="project-a",
            source_id=source["id"],
            mime_type="video/mp4",
            byte_hash=sha256(payload).hexdigest(),
            byte_size=len(payload),
            storage_ref="projects/project-a/01_Sources/briefing.mp4",
        )
    )

    class ProbeResult:
        returncode = 0
        stdout = json.dumps(
            {
                "format": {"duration": "12.5", "format_name": "mov,mp4,m4a,3gp,3g2,mj2"},
                "streams": [
                    {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080},
                    {"codec_type": "audio", "codec_name": "aac", "sample_rate": "48000", "channels": 2},
                ],
            }
        ).encode("utf-8")

    monkeypatch.setattr("app.knowledge.multimodal_extraction.shutil.which", lambda name: "/mock/ffprobe" if name == "ffprobe" else None)
    monkeypatch.setattr("app.knowledge.multimodal_extraction.subprocess.run", lambda *_args, **_kwargs: ProbeResult())
    try:
        result = LocalMultimodalExtractor(repo, vault).extract(
            project_id="project-a", source_id=source["id"], asset_id=asset["id"]
        )

        assert result["status"] == "partial"
        assert result["extractor"] == "ffprobe-media-metadata"
        assert result["error"] == "transcription_unavailable"
        assert result["metadata"] == {
            "audio_streams": 1,
            "container": "mov,mp4,m4a,3gp,3g2,mj2",
            "duration_seconds": 12.5,
            "stream_count": 2,
            "video_streams": 1,
        }
    finally:
        repo.close()


def test_scanned_pdf_uses_local_ocr_fallback_without_mutating_original(monkeypatch, tmp_path):
    fitz = pytest.importorskip("fitz")
    from PIL import Image

    vault = tmp_path / "vault"
    target = vault / "projects" / "project-a" / "01_Sources" / "scanned.pdf"
    target.parent.mkdir(parents=True)
    image = Image.new("RGB", (320, 120), color="white")
    bitmap = BytesIO()
    image.save(bitmap, format="PNG")
    document = fitz.open()
    page = document.new_page(width=320, height=120)
    page.insert_image(page.rect, stream=bitmap.getvalue())
    document.save(target)
    document.close()
    payload = target.read_bytes()
    repo = WikiRepository(db_path=str(tmp_path / "scanned-pdf.db"))
    source = repo.create_source(_source("project-a", "source-scanned-pdf"))
    asset = repo.register_media_asset(
        MediaAsset(
            project_id="project-a",
            source_id=source["id"],
            mime_type="application/pdf",
            byte_hash=sha256(payload).hexdigest(),
            byte_size=len(payload),
            storage_ref="projects/project-a/01_Sources/scanned.pdf",
        )
    )
    monkeypatch.setattr(LocalMultimodalExtractor, "_binary", staticmethod(lambda name: "/mock/tesseract" if name == "tesseract" else None), raising=False)
    try:
        service = LocalMultimodalExtractor(repo, vault)
        monkeypatch.setattr(service, "_ocr", lambda _payload: "scanned OCR evidence")
        result = service.extract(project_id="project-a", source_id=source["id"], asset_id=asset["id"])

        assert result["status"] == "complete"
        assert result["extractor"] == "pdf-ocr"
        assert result["metadata"] == {"ocr": "complete", "page_count": 1}
        assert repo.get_extraction_content("project-a", result["id"])["content"] == "scanned OCR evidence"
        assert target.read_bytes() == payload
    finally:
        repo.close()


def test_ffprobe_resolution_supports_a_fresh_windows_winget_install(monkeypatch, tmp_path):
    binary = tmp_path / "Microsoft" / "WinGet" / "Packages" / "Gyan.FFmpeg_Microsoft.Winget.Source" / "ffmpeg-build" / "bin" / "ffprobe.exe"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(multimodal_extraction.os, "name", "nt")
    monkeypatch.setattr(multimodal_extraction.shutil, "which", lambda _name: None)

    assert LocalMultimodalExtractor._binary("ffprobe") == str(binary)
    assert LocalMultimodalExtractor.capabilities()["media_probe"]["state"] == "available"
