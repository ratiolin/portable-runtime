"""Typed governance fixtures for legacy workflow tests.

The strict RealityBoundary intentionally rejects the historical implicit
authorization/procedure defaults.  These helpers make the required evidence
explicit in tests without weakening the runtime gate.
"""

from __future__ import annotations

from typing import Any

from portable_runtime.core.models import Checkpoint, Run, Work, new_id
from portable_runtime.records.authorization import create_grant_for_approval
from portable_runtime.records.models import BaseRecord
from portable_runtime.records.relations import RecordRelation


def seed_action_governance(
    work: Work,
    run: Run,
    store: Any,
    *,
    capability: str = "code.edit",
    actor_ref: str | None = None,
    resource_ref: str | None = None,
    subject_version: str | None = None,
    include_grant: bool = False,
) -> None:
    """Attach typed procedure evidence and a matching action grant."""

    actor = actor_ref or f"run:{run.id}"
    resource = resource_ref or str(work.metadata.get("resource_scope") or "repo/test")
    version = subject_version or str(work.metadata.get("patch_hint") or "patch:v1")
    metadata = dict(work.metadata)
    failure_stop = BaseRecord(
        id=new_id("record"),
        record_type="Policy",
        lifecycle_status="candidate",
        metadata={"qualification_kind": "failure-stop", "condition": "provider failure"},
    )
    evidence = BaseRecord(
        id=new_id("record"),
        record_type="EvidenceArtifact",
        lifecycle_status="current",
        metadata={
            "qualification_kind": "evidence",
            "target_refs": [work.id],
            "uri": "evidence:test",
        },
    )
    verification = BaseRecord(
        id=new_id("record"),
        record_type="Assertion",
        lifecycle_status="current",
        epistemic_status="supported",
        metadata={
            "qualification_kind": "verification",
            "result": "pass",
            "target_refs": [work.id],
            "subject_version_refs": [version],
        },
    )
    decision = BaseRecord(
        id=new_id("record"),
        record_type="Decision",
        lifecycle_status="current",
        metadata={"qualification_kind": "decision", "target_refs": [work.id]},
    )
    relation_evidence = RecordRelation(
        id=new_id("relation"),
        relation_type="records",
        subject_ref=work.id,
        object_ref=evidence.id,
    )
    relation_verification = RecordRelation(
        id=new_id("relation"),
        relation_type="validated-under",
        subject_ref=work.id,
        object_ref=verification.id,
    )
    checkpoint = Checkpoint(
        id=new_id("checkpoint"),
        run_id=run.id,
        payload={"condition": "provider failure"},
    )
    for record in (failure_stop, evidence, verification, decision):
        store.save_record(record)
    for relation in (relation_evidence, relation_verification):
        store.save_relation(relation)
    store.save_checkpoint(checkpoint)
    metadata.update(
        {
            "purpose": metadata.get("purpose") or work.description or work.title,
            "execution_boundary": metadata.get("execution_boundary") or "provider",
            "result_confirmed": True,
            "candidate": metadata.get("candidate") or ["repair"],
            "reviewed": True,
            "actor_ref": actor,
            "resource_ref": resource,
            "resource_scope": metadata.get("resource_scope") or resource,
            "subject_version_refs": [version],
            "procedure_profile": "standard",
            "procedure_proof_refs": [failure_stop.id],
            "evidence_artifact_refs": [evidence.id],
            "relation_refs": [relation_evidence.id, relation_verification.id],
            "verification_result_refs": [verification.id],
            "checkpoint_refs": [checkpoint.id],
            "decision_refs": [decision.id],
        }
    )
    work.metadata.clear()
    work.metadata.update(metadata)
    store.save_work(work)
    if include_grant:
        store.save_authorization(
            create_grant_for_approval(
                principal_ref=str(metadata.get("approver") or "human:owner"),
                grantee_ref=actor,
                allowed_capabilities=[capability],
                subject_version_refs=[version],
                resource_scope=[resource],
                ttl_seconds=3600,
            )
        )
