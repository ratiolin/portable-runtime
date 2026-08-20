"""Legacy → Records dual write compatibility."""

from __future__ import annotations

from portable_runtime.core.models import Action, Decision, Evidence, Outcome
from portable_runtime.records.models import ActionRecord, DecisionRecord, EvidenceArtifact, OutcomeRecord


def legacy_evidence_to_artifact(ev: Evidence) -> EvidenceArtifact:
    return EvidenceArtifact(
        id=f"artifact_{ev.id}",
        created_at=ev.created_at,
        source_refs=ev.subject_refs,
        metadata={"legacy_id": ev.id, "kind": ev.kind, "status": ev.status},
        lifecycle_status="current",
    )

def legacy_decision_to_record(d: Decision) -> DecisionRecord:
    return DecisionRecord(
        id=f"record_{d.id}",
        created_at=d.created_at,
        lifecycle_status="draft",
        decision_type=d.decision_type,
        selected_option=d.selected_option,
        rationale_refs=d.rationale_artifact_refs,
        metadata={"legacy_id": d.id},
    )

def legacy_action_to_record(a: Action) -> ActionRecord:
    return ActionRecord(
        id=f"record_{a.id}",
        created_at=a.created_at,
        work_id=a.work_id,
        run_id=a.run_id,
        capability=a.capability,
        provider_id=a.provider_id,
        request_ref=a.request_ref,
        lifecycle_status="recorded",
        metadata={"legacy_id": a.id, "status": a.status},
    )

def legacy_outcome_to_record(o: Outcome) -> OutcomeRecord:
    return OutcomeRecord(
        id=f"record_{o.id}",
        created_at=o.created_at,
        action_ref=o.action_id,
        artifact_refs=o.artifact_refs,
        evidence_refs=o.evidence_refs,
        lifecycle_status="recorded",
        metadata={"legacy_id": o.id, "status": o.status},
    )
