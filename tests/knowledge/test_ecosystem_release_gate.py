import pytest
from pydantic import ValidationError

from app.knowledge.ecosystem_release_gate import (
    REQUIRED_RELEASE_EVIDENCE,
    ReleaseEvidence,
    ReleaseEvidencePacket,
    evaluate_release_evidence,
)


def _evidence(
    evidence_id: str,
    *,
    state: str = "verified",
    proof_class: str = "real",
    durable_ids: tuple[str, ...] = ("run:fixture-1",),
) -> ReleaseEvidence:
    return ReleaseEvidence(
        evidence_id=evidence_id,
        state=state,
        proof_class=proof_class,
        observed_at="2026-07-31T00:00:00+00:00",
        durable_ids=durable_ids,
        detail_code="verified" if state == "verified" else state,
    )


def _complete_packet() -> ReleaseEvidencePacket:
    return ReleaseEvidencePacket(
        contract_revision="e1-knowledge-ecosystem-v1",
        evidence=tuple(_evidence(evidence_id) for evidence_id in REQUIRED_RELEASE_EVIDENCE),
    )


def test_missing_or_pending_external_proof_cannot_become_release_ready():
    packet = ReleaseEvidencePacket(
        contract_revision="e1-knowledge-ecosystem-v1",
        evidence=(_evidence(REQUIRED_RELEASE_EVIDENCE[0]), _evidence(REQUIRED_RELEASE_EVIDENCE[1], state="pending", durable_ids=())),
    )

    decision = evaluate_release_evidence(packet)

    assert decision.status == "implemented_with_operational_proof_pending"
    assert REQUIRED_RELEASE_EVIDENCE[2] in decision.missing_evidence
    assert REQUIRED_RELEASE_EVIDENCE[1] in decision.pending_evidence
    assert "raw_content" not in str(decision.model_dump())


def test_fixture_substitution_is_a_release_blocker_not_pending_evidence():
    evidence = list(_complete_packet().evidence)
    evidence[2] = _evidence(REQUIRED_RELEASE_EVIDENCE[2], proof_class="fixture")

    decision = evaluate_release_evidence(ReleaseEvidencePacket(
        contract_revision="e1-knowledge-ecosystem-v1", evidence=tuple(evidence)
    ))

    assert decision.status == "not_release_ready"
    assert REQUIRED_RELEASE_EVIDENCE[2] in decision.failed_evidence
    assert "fixture_substitution" in decision.blocking_reasons


def test_failed_evidence_is_a_release_blocker():
    evidence = list(_complete_packet().evidence)
    evidence[4] = _evidence(REQUIRED_RELEASE_EVIDENCE[4], state="failed", durable_ids=())

    decision = evaluate_release_evidence(ReleaseEvidencePacket(
        contract_revision="e1-knowledge-ecosystem-v1", evidence=tuple(evidence)
    ))

    assert decision.status == "not_release_ready"
    assert REQUIRED_RELEASE_EVIDENCE[4] in decision.failed_evidence
    assert "failed_evidence" in decision.blocking_reasons


def test_only_complete_real_evidence_packet_can_be_release_ready():
    decision = evaluate_release_evidence(_complete_packet())

    assert decision.status == "release_ready"
    assert decision.missing_evidence == ()
    assert decision.pending_evidence == ()
    assert decision.failed_evidence == ()
    assert len(decision.matrix) == len(REQUIRED_RELEASE_EVIDENCE)
    assert all(row.durable_id_count == 1 for row in decision.matrix)


def test_evidence_contract_rejects_source_body_and_unknown_fields():
    with pytest.raises(ValidationError):
        ReleaseEvidence(
            evidence_id=REQUIRED_RELEASE_EVIDENCE[0],
            state="verified",
            proof_class="real",
            observed_at="2026-07-31T00:00:00+00:00",
            durable_ids=("run:fixture-1",),
            detail_code="verified",
            raw_content="must not enter a release packet",
        )


@pytest.mark.parametrize("forbidden_field", ["vault_path", "source_url", "api_key", "provider_payload", "prompt"])
def test_evidence_contract_rejects_storage_and_provider_details(forbidden_field):
    with pytest.raises(ValidationError):
        ReleaseEvidence(
            evidence_id=REQUIRED_RELEASE_EVIDENCE[0],
            state="pending",
            proof_class="none",
            detail_code="awaiting_observation",
            **{forbidden_field: "must never enter the release ledger"},
        )


def test_evidence_contract_rejects_paths_and_naive_timestamps():
    with pytest.raises(ValidationError):
        ReleaseEvidence(
            evidence_id=REQUIRED_RELEASE_EVIDENCE[0],
            state="verified",
            proof_class="real",
            observed_at="2026-07-31T00:00:00",
            durable_ids=("..\\private\\secret.json",),
            detail_code="verified",
        )


def test_evidence_packet_rejects_duplicate_ids():
    with pytest.raises(ValidationError):
        ReleaseEvidencePacket(
            contract_revision="e1-knowledge-ecosystem-v1",
            evidence=(_evidence(REQUIRED_RELEASE_EVIDENCE[0]), _evidence(REQUIRED_RELEASE_EVIDENCE[0])),
        )
