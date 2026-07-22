"""Lifecycle-neutral completion bridges into the governed D-layer registry."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import logging
from pathlib import PurePath
from typing import Any

from app.knowledge.growth_contracts import OutputAsset
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.output_registry import OutputRegistry
from app.knowledge.wiki_contracts import KnowledgeRun, RunStatus


logger = logging.getLogger(__name__)
_COMPLETED = {"completed", "succeeded", "success", "accepted"}


@dataclass(frozen=True)
class BridgeResult:
    status: str
    producer_type: str
    producer_id: str
    output_id: str = ""
    audit_run_id: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class OutputCompletionBridge:
    """Best-effort bridge that never changes the producer lifecycle."""

    def __init__(
        self,
        repository: GrowthRepository,
        vault_root: Any,
        *,
        raise_on_error: bool = False,
    ) -> None:
        self.repository = repository
        self.vault_root = vault_root
        self.raise_on_error = raise_on_error

    def register_skill_completion(
        self,
        *,
        execution_id: str,
        skill_id: str,
        status: str,
        result: str | bytes | None,
        context: dict[str, Any],
    ) -> BridgeResult:
        return self._register(
            producer_type="skill",
            producer_id=execution_id,
            producer_name=skill_id,
            producer_status=status,
            result=result,
            filename=str(context.get("filename") or f"{skill_id}.md"),
            mime_type=str(context.get("mime_type") or "text/markdown"),
            context=context,
        )

    def register_orchestration_completion(
        self,
        *,
        session_id: str,
        status: str,
        result: str | bytes | None,
        context: dict[str, Any],
    ) -> BridgeResult:
        return self._register(
            producer_type="orchestration",
            producer_id=session_id,
            producer_name=str(context.get("workflow") or "orchestration"),
            producer_status=status,
            result=result,
            filename=str(context.get("filename") or "result.md"),
            mime_type=str(context.get("mime_type") or "text/markdown"),
            context=context,
        )

    def register_export_completion(
        self,
        *,
        export_id: str,
        status: str,
        result: str | bytes | None,
        filename: str,
        mime_type: str,
        context: dict[str, Any],
    ) -> BridgeResult:
        return self._register(
            producer_type="export",
            producer_id=export_id,
            producer_name=str(context.get("exporter") or "export"),
            producer_status=status,
            result=result,
            filename=filename,
            mime_type=mime_type,
            context=context,
        )

    def _register(
        self,
        *,
        producer_type: str,
        producer_id: str,
        producer_name: str,
        producer_status: str,
        result: str | bytes | None,
        filename: str,
        mime_type: str,
        context: dict[str, Any],
    ) -> BridgeResult:
        if producer_status.lower() not in _COMPLETED or result is None or result == "" or result == b"":
            return BridgeResult("not_registered_incomplete", producer_type, producer_id)
        project_id = str(context.get("project_id") or "").strip()
        if not project_id:
            return BridgeResult("not_registered_unscoped", producer_type, producer_id)

        content = result.encode("utf-8") if isinstance(result, str) else bytes(result)
        content_hash = hashlib.sha256(content).hexdigest()
        audit_run_id = hashlib.sha256(
            f"{project_id}|bridge|{producer_type}|{producer_id}|{content_hash}".encode("utf-8")
        ).hexdigest()[:24]
        audit = self._ensure_audit_run(
            audit_run_id=audit_run_id,
            project_id=project_id,
            producer_type=producer_type,
            producer_id=producer_id,
            producer_status=producer_status,
            context=context,
        )
        if not audit:
            return BridgeResult(
                "registration_failed",
                producer_type,
                producer_id,
                audit_run_id=audit_run_id,
                error="could not create bridge audit run",
            )

        safe_filename = PurePath(filename).name
        if safe_filename in {"", ".", "..", "index.md"}:
            return self._failed(
                project_id,
                audit_run_id,
                producer_type,
                producer_id,
                ValueError("output filename is not safe"),
            )
        gaps: list[str] = []

        def provenance(name: str, fallback: str = "not_provided") -> str:
            value = str(context.get(name) or "").strip()
            if not value:
                gaps.append(name)
                return fallback
            return value

        metadata = {
            **dict(context.get("metadata") or {}),
            "goal": provenance("goal"),
            "audience": provenance("audience"),
            "channel": provenance("channel", producer_type),
            "generator": f"{producer_type}:{producer_name}",
            "provider": provenance("provider", "unknown"),
            "model": provenance("model", "unknown"),
            "prompt_revision": provenance("prompt_revision", "unknown"),
            "producer_type": producer_type,
            "producer_id": producer_id,
            "producer_status": producer_status,
            "provenance_gaps": gaps,
        }
        output = OutputAsset(
            project_id=project_id,
            kind=str(context.get("kind") or producer_type),
            title=str(context.get("title") or safe_filename),
            mime_type=mime_type,
            content_hash=content_hash,
            vault_path=f"outputs/{datetime.now(timezone.utc):%Y}/pending/{safe_filename}",
            run_id=audit_run_id,
            method_revision_id=str(context.get("method_revision_id") or ""),
            context_revision=str(context.get("context_revision") or ""),
            source_refs=[str(value) for value in context.get("source_refs") or []],
            page_refs=[str(value) for value in context.get("page_refs") or []],
            idempotency_key=f"{producer_type}|{producer_id}|{safe_filename}",
            metadata=metadata,
        )
        try:
            saved = OutputRegistry(self.repository, self.vault_root).register_content(output, content)
            self.repository.update_run_status(
                project_id,
                audit_run_id,
                RunStatus.COMPLETED,
                output_refs={"output_id": saved["id"], "producer_id": producer_id},
            )
            return BridgeResult(
                "registered",
                producer_type,
                producer_id,
                output_id=saved["id"],
                audit_run_id=audit_run_id,
            )
        except Exception as exc:
            return self._failed(
                project_id, audit_run_id, producer_type, producer_id, exc
            )

    def _ensure_audit_run(
        self,
        *,
        audit_run_id: str,
        project_id: str,
        producer_type: str,
        producer_id: str,
        producer_status: str,
        context: dict[str, Any],
    ) -> dict[str, Any] | None:
        existing = self.repository.get_run(project_id, audit_run_id)
        if existing:
            return existing
        try:
            return self.repository.create_run(
                KnowledgeRun(
                    id=audit_run_id,
                    project_id=project_id,
                    run_type="output_registration_bridge",
                    trigger="producer_completion",
                    status=RunStatus.RUNNING,
                    actor_id=str(context.get("actor_id") or "system"),
                    input_refs={
                        "producer_type": producer_type,
                        "producer_id": producer_id,
                        "producer_status": producer_status,
                    },
                )
            )
        except Exception:
            logger.exception("Failed to create output bridge audit run")
            if self.raise_on_error:
                raise
            return None

    def _failed(
        self,
        project_id: str,
        audit_run_id: str,
        producer_type: str,
        producer_id: str,
        exc: Exception,
    ) -> BridgeResult:
        error = str(exc) or exc.__class__.__name__
        try:
            self.repository.update_run_status(
                project_id, audit_run_id, RunStatus.FAILED, error=error
            )
        except Exception:
            logger.exception("Failed to persist output bridge failure")
        logger.warning(
            "Output registration bridge failed for %s %s: %s",
            producer_type,
            producer_id,
            error,
        )
        if self.raise_on_error:
            raise exc
        return BridgeResult(
            "registration_failed",
            producer_type,
            producer_id,
            audit_run_id=audit_run_id,
            error=error,
        )
