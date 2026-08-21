"""Legacy → Records dual write compatibility."""

from __future__ import annotations

from portable_runtime.core.models import Action, Decision, Evidence, KnowledgeItem, Outcome
from portable_runtime.records.knowledge import KnowledgeProjection
from portable_runtime.records.models import ActionRecord, DecisionRecord, EvidenceArtifact, OutcomeRecord


def legacy_evidence_to_artifact(ev: Evidence) -> EvidenceArtifact:
    return EvidenceArtifact(
        id=f"artifact_{ev.id}",
        created_at=ev.created_at,
        source_refs=ev.subject_refs,
        metadata={"legacy_id": ev.id, "kind": ev.kind, "status": ev.status},
        lifecycle_status="current",
    )


def evidence_artifact_to_legacy(artifact: EvidenceArtifact) -> Evidence:
    """Expose a canonical evidence artifact through the legacy read API."""
    metadata = dict(getattr(artifact, "metadata", {}) or {})
    work_id = metadata.get("work_id")
    subject_refs = [str(work_id)] if isinstance(work_id, str) and work_id else list(artifact.source_refs)
    return Evidence(
        id=f"legacy_{artifact.id}",
        kind=artifact.kind,
        subject_refs=subject_refs,
        artifact_refs=list(artifact.source_refs),
        source=str(metadata.get("provider_id") or metadata.get("source") or "canonical-record"),
        status="unknown",
        metadata={"canonical_record_id": artifact.id, **metadata},
    )


def knowledge_projection_to_legacy(proj: KnowledgeProjection) -> KnowledgeItem:
    """Expose a projection as a read-only legacy view.

    This adapter deliberately never writes the returned ``KnowledgeItem``.
    Canonical workflows persist ``KnowledgeProjection`` and old callers may
    continue to read the familiar shape until they migrate.
    """
    content_ref = (
        next(iter(proj.evidence_summary_refs), None)
        or next(iter(proj.current_assertion_refs), None)
        or proj.id
    )
    metadata = dict(getattr(proj, "metadata", {}) or {})
    metadata.update(
        {
            "canonical_projection_id": proj.id,
            "epistemic_judgment_refs": list(proj.epistemic_judgment_refs),
            "authorization_refs": list(proj.authorization_refs),
            "environment_bindings": dict(proj.environment_bindings),
            "counterexample_refs": list(proj.counterexample_refs),
            "negative_knowledge_refs": list(proj.negative_knowledge_refs),
        }
    )
    return KnowledgeItem(
        id=str(metadata.get("legacy_id") or f"legacy_{proj.id}"),
        kind=proj.kind,
        title=proj.title,
        content_ref=content_ref,
        status=proj.lifecycle_status,
        source_work_refs=list(proj.source_work_refs),
        evidence_refs=list(proj.evidence_summary_refs),
        valid_scope=dict(proj.validity_scope),
        reopen_conditions=list(proj.reopen_conditions),
        metadata=metadata,
        updated_at=proj.updated_at,
    )


def legacy_knowledge_to_projection(item: KnowledgeItem) -> KnowledgeProjection:
    """Map an existing legacy item into canonical read/migration form."""
    metadata = dict(item.metadata or {})
    return KnowledgeProjection(
        id=f"projection_{item.id}",
        kind=item.kind,
        title=item.title,
        source_work_refs=list(item.source_work_refs),
        current_assertion_refs=[item.content_ref] if item.content_ref else [],
        evidence_summary_refs=list(item.evidence_refs),
        validity_scope=dict(item.valid_scope),
        environment_bindings=dict(metadata.get("environment_versions") or metadata.get("environment_bindings") or {}),
        reopen_conditions=list(item.reopen_conditions),
        epistemic_judgment_refs=list(metadata.get("epistemic_judgment_refs") or []),
        authorization_refs=list(metadata.get("authorization_refs") or metadata.get("authorization_grant_ids") or []),
        lifecycle_status=item.status,
        metadata={"legacy_id": item.id, **metadata},
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
