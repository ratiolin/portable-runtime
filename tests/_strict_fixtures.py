"""Typed governance fixtures for legacy workflow tests.

The strict RealityBoundary intentionally rejects the historical implicit
authorization/procedure defaults.  These helpers make the required evidence
explicit in tests without weakening the runtime gate.
"""

from __future__ import annotations

from typing import Any

from portable_runtime.core.models import Evidence, Run, Work
from portable_runtime.records.authorization import create_grant_for_approval
from portable_runtime.records.open_validation import ClosedVerificationResult
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
            "procedure_proofs": {
                "failure_stop_proofs": [{"condition": "provider failure"}],
                "evidence_artifacts": [Evidence(kind="observation", subject_refs=[work.id], source="test")],
                "relations": [
                    RecordRelation(relation_type="records", subject_ref=work.id, object_ref="observation:test"),
                    RecordRelation(relation_type="validated-under", subject_ref=work.id, object_ref="verification:test"),
                ],
                "verification_results": [
                    ClosedVerificationResult(result="pass", message="typed verification fixture")
                ],
                "checkpoints": [{"id": f"checkpoint:{run.id}"}],
                "decisions": [{"id": f"decision:{run.id}"}],
            },
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
